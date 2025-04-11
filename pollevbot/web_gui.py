import os
import threading
import logging
import time
from typing import Optional, List, Dict
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, IntegerField, FloatField
from wtforms.validators import DataRequired, Optional as OptionalValidator
import json
from datetime import datetime

from .pollbot import PollBot

# Set up logging
logger = logging.getLogger(__name__)

# Global variables to store bot state
bot_instance = None
bot_thread = None
bot_status = "stopped"
config = {}
status_messages: List[Dict] = []
MAX_STATUS_MESSAGES = 50

class ConfigForm(FlaskForm):
    """Form for configuring the PollBot"""
    pollev_username = StringField('PollEv Username', validators=[DataRequired()])
    pollev_password = PasswordField('PollEv Password', validators=[DataRequired()])
    pollev_host = StringField('PollEv Host', validators=[DataRequired()])
    login_type = SelectField('Login Type', choices=[('pollev', 'PollEv'), ('uw', 'UW SSO')], validators=[DataRequired()])
    claude_api_key = StringField('Claude API Key', validators=[DataRequired()])
    telegram_bot_token = StringField('Telegram Bot Token', validators=[OptionalValidator()])
    telegram_admin_chat_id = StringField('Telegram Admin Chat ID', validators=[OptionalValidator()])
    
    min_option = IntegerField('Min Option Index', default=0, validators=[OptionalValidator()])
    max_option = IntegerField('Max Option Index', validators=[OptionalValidator()])
    closed_wait = FloatField('Closed Wait Time (seconds)', default=5.0, validators=[DataRequired()])
    open_wait = FloatField('Open Wait Time (seconds)', default=60.0, validators=[DataRequired()])
    lifetime = FloatField('Lifetime (seconds, inf for unlimited)', default=float('inf'), validators=[DataRequired()])
    log_file = StringField('Log File Path', default="poll_responses.jsonl", validators=[DataRequired()])

def add_status_message(message: str, message_type: str = "info"):
    """Add a status message to the global list"""
    global status_messages, MAX_STATUS_MESSAGES
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_messages.append({
        "timestamp": timestamp,
        "message": message,
        "type": message_type
    })
    # Keep only the most recent messages
    if len(status_messages) > MAX_STATUS_MESSAGES:
        status_messages = status_messages[-MAX_STATUS_MESSAGES:]

class WebGUI:
    """Web interface for configuring and controlling PollBot"""
    
    def __init__(self, host='0.0.0.0', port=5000, debug=False):
        self.app = Flask(__name__)
        self.app.secret_key = os.urandom(24)
        self.host = host
        self.port = port
        self.debug = debug
        
        self._setup_routes()
        
        # Load configuration from environment variables if available
        self._load_initial_config()
    
    def _setup_routes(self):
        @self.app.route('/', methods=['GET', 'POST'])
        def index():
            global config, bot_status
            
            form = ConfigForm()
            
            if request.method == 'POST' and form.validate_on_submit():
                # Update config with form data
                new_config = {
                    'pollev_username': form.pollev_username.data,
                    'pollev_password': form.pollev_password.data,
                    'pollev_host': form.pollev_host.data,
                    'login_type': form.login_type.data,
                    'claude_api_key': form.claude_api_key.data,
                    'telegram_bot_token': form.telegram_bot_token.data,
                    'telegram_admin_chat_id': form.telegram_admin_chat_id.data,
                    'min_option': form.min_option.data,
                    'max_option': form.max_option.data,
                    'closed_wait': form.closed_wait.data,
                    'open_wait': form.open_wait.data,
                    'lifetime': form.lifetime.data,
                    'log_file': form.log_file.data
                }
                config.update(new_config)
                flash('Configuration updated successfully', 'success')
                return redirect(url_for('index'))
            else:
                # Pre-populate form with current config
                for field in form:
                    field_name = field.name
                    if field_name in config:
                        field.data = config.get(field_name)
            
            # Get recent responses from log file
            recent_responses = self._get_recent_responses(10)
            
            return render_template('index.html', form=form, bot_status=bot_status, 
                                  recent_responses=recent_responses)
        
        @self.app.route('/start', methods=['POST'])
        def start_bot():
            global bot_instance, bot_thread, bot_status, config
            
            if bot_status == "running":
                flash('Bot is already running', 'warning')
                return redirect(url_for('index'))
            
            try:
                # Clear previous status messages when starting a new bot
                global status_messages
                status_messages = []
                
                # Create a new bot instance with status callback
                bot_instance = PollBot(
                    user=config.get('pollev_username'),
                    password=config.get('pollev_password'),
                    host=config.get('pollev_host'),
                    login_type=config.get('login_type', 'pollev'),
                    claude_api_key=config.get('claude_api_key'),
                    telegram_token=config.get('telegram_bot_token'),
                    telegram_chat_id=config.get('telegram_admin_chat_id'),
                    min_option=config.get('min_option', 0),
                    max_option=config.get('max_option'),
                    closed_wait=config.get('closed_wait', 5.0),
                    open_wait=config.get('open_wait', 60.0),
                    lifetime=config.get('lifetime', float('inf')),
                    log_file=config.get('log_file', 'poll_responses.jsonl'),
                    status_callback=add_status_message
                )
                
                # Start bot in a separate thread
                bot_thread = threading.Thread(target=self._run_bot, args=(bot_instance,))
                bot_thread.daemon = True
                bot_thread.start()
                
                bot_status = "running"
                flash('Bot started successfully', 'success')
            except Exception as e:
                logger.exception("Failed to start bot")
                flash(f'Failed to start bot: {str(e)}', 'danger')
            
            return redirect(url_for('index'))
        
        @self.app.route('/stop', methods=['POST'])
        def stop_bot():
            global bot_instance, bot_status
            
            if bot_status != "running" or bot_instance is None:
                flash('Bot is not running', 'warning')
                return redirect(url_for('index'))
            
            try:
                # Signal the bot thread to stop
                bot_instance.__exit__(None, None, None)
                bot_status = "stopped"
                flash('Bot stopped successfully', 'success')
            except Exception as e:
                logger.exception("Failed to stop bot")
                flash(f'Failed to stop bot: {str(e)}', 'danger')
            
            return redirect(url_for('index'))
        
        @self.app.route('/status', methods=['GET'])
        def get_status():
            global bot_status, status_messages
            return jsonify({
                'status': bot_status,
                'messages': status_messages[-10:] if status_messages else []
            })
    
    def _run_bot(self, bot):
        try:
            bot.run()
        except Exception as e:
            logger.exception("Bot encountered an error")
        finally:
            global bot_status
            bot_status = "stopped"
    
    def _load_initial_config(self):
        global config
        
        # Try to load from environment variables first
        env_mapping = {
            'POLLEV_USERNAME': 'pollev_username',
            'POLLEV_PASSWORD': 'pollev_password',
            'POLLEV_HOST': 'pollev_host',
            'LOGIN_TYPE': 'login_type',
            'CLAUDE_API_KEY': 'claude_api_key',
            'TELEGRAM_BOT_TOKEN': 'telegram_bot_token',
            'TELEGRAM_ADMIN_CHAT_ID': 'telegram_admin_chat_id',
            'MIN_OPTION': 'min_option',
            'MAX_OPTION': 'max_option',
            'CLOSED_WAIT': 'closed_wait',
            'OPEN_WAIT': 'open_wait',
            'LIFETIME': 'lifetime',
            'LOG_FILE': 'log_file'
        }
        
        for env_var, config_key in env_mapping.items():
            if os.environ.get(env_var):
                value = os.environ.get(env_var)
                
                # Convert numeric values
                if config_key in ['min_option', 'max_option']:
                    try:
                        value = int(value)
                    except ValueError:
                        pass
                elif config_key in ['closed_wait', 'open_wait', 'lifetime']:
                    try:
                        value = float(value)
                    except ValueError:
                        pass
                
                config[config_key] = value
    
    def _get_recent_responses(self, limit=10):
        """Get recent responses from the log file"""
        log_file = config.get('log_file', 'poll_responses.jsonl')
        responses = []
        
        try:
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    for line in f:
                        try:
                            response = json.loads(line.strip())
                            responses.append(response)
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"Error reading log file: {e}")
        
        # Sort by timestamp and take the most recent
        responses.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return responses[:limit]
    
    def run(self):
        """Run the Flask application"""
        self.app.run(host=self.host, port=self.port, debug=self.debug)

def create_app():
    """Factory function to create and configure the Flask app"""
    gui = WebGUI()
    return gui.app