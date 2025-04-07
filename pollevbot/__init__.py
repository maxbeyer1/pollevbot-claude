from sys import version_info

assert version_info >= (3, 7), "pollevbot requires python 3.7 or later"

import logging

# Log all messages as white text
WHITE = "\033[1m"
logging.basicConfig(level=logging.INFO,
                    format=WHITE + "%(asctime)s.%(msecs)03d [%(name)s] "
                                   "%(levelname)s: %(message)s",
                    datefmt='%Y-%m-%d %H:%M:%S')

# Import main components for easier access
from .pollbot import PollBot
from .claude_client import ClaudeClient
from .output_validator import validate_and_retry_response, get_user_confirmation
from .response_logger import ResponseLogger
from .telegram_notifier import TelegramNotifier
from .web_gui import WebGUI, create_app

__all__ = [
    'PollBot', 
    'ClaudeClient', 
    'validate_and_retry_response',
    'get_user_confirmation',
    'ResponseLogger',
    'TelegramNotifier',
    'WebGUI',
    'create_app'
]
