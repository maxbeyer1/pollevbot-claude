import logging
from typing import Optional, Dict
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
import telebot
from telebot.handler_backends import State, StatesGroup
from telebot import types

logger = logging.getLogger(__name__)


@dataclass
class PendingResponse:
    """Class to hold response data and approval status"""
    response_id: str
    original_response: Dict
    question: str
    timestamp: datetime
    status: str = 'pending'  # pending, approved, rejected
    modified_text: Optional[str] = None


class ResponseStates(StatesGroup):
    awaiting_edit = State()


class TelegramNotifier:
    """Handles Telegram notifications and response approval"""

    def __init__(self, token: str, admin_chat_id: Optional[str] = None):
        self.bot = telebot.TeleBot(token)
        self.admin_chat_id = admin_chat_id

        # Dictionary to store pending responses
        self.pending_responses = {}

        # Lock for thread-safe access to pending_responses
        self.responses_lock = threading.Lock()

        self._setup_handlers()

    def _setup_handlers(self):
        @self.bot.message_handler(commands=['start'])
        def start(message):
            chat_id = message.chat.id
            self.bot.reply_to(
                message,
                f"Welcome! Your chat ID is: {chat_id}\n"
                f"Set this as TELEGRAM_ADMIN_CHAT_ID in your environment variables."
            )

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'reject_', 'edit_')))
        def handle_response(call):
            action, response_id = call.data.split('_')

            with self.responses_lock:
                if response_id not in self.pending_responses:
                    self.bot.answer_callback_query(
                        call.id, "Response expired or not found!")
                    return

                pending = self.pending_responses[response_id]

                if action in ['approve', 'reject']:
                    pending.status = 'approved' if action == 'approve' else 'rejected'

                    # Update message
                    self.bot.answer_callback_query(
                        call.id, f"Response {action}ed!")
                    self.bot.edit_message_reply_markup(
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=None
                    )
                    self.bot.edit_message_text(
                        f"{call.message.text}\n\n✅ {action.title()}d",
                        call.message.chat.id,
                        call.message.message_id
                    )

                elif action == 'edit':
                    self.bot.answer_callback_query(call.id)
                    msg = self.bot.send_message(
                        call.message.chat.id,
                        "Please send the modified answer:",
                        reply_to_message_id=call.message.message_id
                    )
                    self.bot.set_state(
                        call.from_user.id,
                        ResponseStates.awaiting_edit,
                        call.message.chat.id
                    )
                    with self.bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
                        data['response_id'] = response_id

        @self.bot.message_handler(state=ResponseStates.awaiting_edit)
        def handle_edited_response(message):
            with self.bot.retrieve_data(message.from_user.id, message.chat.id) as data:
                response_id = data['response_id']

            with self.responses_lock:
                if response_id in self.pending_responses:
                    pending = self.pending_responses[response_id]
                    pending.status = 'approved'
                    pending.modified_text = message.text

            self.bot.send_message(
                message.chat.id,
                "✅ Response updated and approved!",
                reply_to_message_id=message.message_id
            )
            self.bot.delete_state(message.from_user.id, message.chat.id)

    def start(self):
        """Start the Telegram bot in a separate thread"""
        self.thread = threading.Thread(target=self.bot.polling, daemon=True)
        self.thread.start()
        logger.info("Telegram bot started")

        # Start cleanup thread for expired responses
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_expired_responses, daemon=True)
        self.cleanup_thread.start()

    def stop(self):
        """Stop the Telegram bot"""
        self.bot.stop_polling()
        if hasattr(self, 'thread'):
            self.thread.join()
        logger.info("Telegram bot stopped")

    def _cleanup_expired_responses(self):
        """Periodically clean up expired responses"""
        while True:
            time.sleep(60)  # Check every minute
            with self.responses_lock:
                now = datetime.now()
                expired = [
                    response_id for response_id, pending in self.pending_responses.items()
                    # Expire after 10 minutes
                    if (now - pending.timestamp) > timedelta(minutes=10)
                    and pending.status == 'pending'
                ]
                for response_id in expired:
                    self.pending_responses[response_id].status = 'rejected'
                    logger.info(
                        f"Response {response_id} expired and auto-rejected")

    def send_for_approval(self, response: Dict, question: str) -> str:
        """Send a response for approval via Telegram"""
        if not self.admin_chat_id:
            logger.warning(
                "No admin chat ID set, skipping Telegram notification")
            return None

        # Create a new pending response
        response_id = str(int(time.time() * 1000))  # Timestamp as ID
        pending = PendingResponse(
            response_id=response_id,
            original_response=response,
            question=question,
            timestamp=datetime.now()
        )

        with self.responses_lock:
            self.pending_responses[response_id] = pending

        # Create inline keyboard
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton(
                "✅ Approve", callback_data=f"approve_{response_id}"),
            types.InlineKeyboardButton(
                "❌ Reject", callback_data=f"reject_{response_id}"),
            types.InlineKeyboardButton(
                "✏️ Edit", callback_data=f"edit_{response_id}")
        )

        # Format message
        message = (
            f"🔔 New Response Needs Review:\n\n"
            f"Question:\n{question}\n\n"
            f"Proposed Answer:\n{response['answer']}\n\n"
            f"Confidence: {response['confidence']:.2f}\n"
            f"Reasoning: {response['reasoning']}"
        )

        try:
            self.bot.send_message(
                self.admin_chat_id,
                message,
                reply_markup=markup
            )
            logger.info(f"Sent response {response_id} for approval")
            return response_id
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            with self.responses_lock:
                if response_id in self.pending_responses:
                    del self.pending_responses[response_id]
            return None

    def wait_for_response(self, response_id: str, timeout: float = 60.0) -> Optional[Dict]:
        """
        Wait for a response to be approved/rejected

        Args:
            response_id: ID of the pending response
            timeout: How long to wait for response in seconds

        Returns:
            Dict with status and possibly modified text, or None if timeout
        """
        end_time = time.time() + timeout

        while time.time() < end_time:
            with self.responses_lock:
                if response_id not in self.pending_responses:
                    return None

                pending = self.pending_responses[response_id]
                if pending.status != 'pending':
                    # Clean up and return result
                    result = {
                        'status': pending.status,
                        'modified_text': pending.modified_text
                    }
                    del self.pending_responses[response_id]
                    return result

            time.sleep(0.5)  # Prevent busy waiting

        # Timeout reached
        with self.responses_lock:
            if response_id in self.pending_responses:
                self.pending_responses[response_id].status = 'rejected'
                del self.pending_responses[response_id]

        return {'status': 'rejected', 'modified_text': None}
