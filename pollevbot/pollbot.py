import logging
import time
from typing import Optional
import json
import random
import requests

from .endpoints import endpoints
from .claude_client import ClaudeClient
from .response_logger import ResponseLogger
from .output_validator import validate_and_retry_response, get_user_confirmation
from .telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)
__all__ = ['PollBot']


class LoginError(RuntimeError):
    """Error indicating that login failed."""


class PollBot:
    """Bot for answering polls on PollEverywhere.
    Responses are randomly selected.

    Usage:
    >>> bot = PollBot(user='username', password='password',
    ...               host='host', login_type='uw')
    >>> bot.run()

    Can also be used as a context manager.
    """

    def __init__(self, user: str,
                 password: str,
                 host: str,
                 login_type: str = 'uw',
                 claude_api_key: Optional[str] = None,
                 telegram_token: Optional[str] = None,
                 telegram_chat_id: Optional[str] = None,
                 min_option: int = 0,
                 max_option: int = None,
                 closed_wait: float = 5,
                 open_wait: float = 60,
                 lifetime: float = float('inf'),
                 log_file: str = "poll_responses.jsonl",
                 status_callback = None):
        """
        Constructor. Creates a PollBot that answers polls on pollev.com.

        :param user: PollEv account username.
        :param password: PollEv account password.
        :param host: PollEv host name, i.e. 'uwpsych'
        :param login_type: Login protocol to use (either 'uw' or 'pollev').
                        If 'uw', uses MyUW (SAML2 SSO) to authenticate.
                        If 'pollev', uses pollev.com.
        :param claude_api_key: API key for Claude. If None, uses random responses.
        :param min_option: Minimum index (0-indexed) of option to select (inclusive).
        :param max_option: Maximum index (0-indexed) of option to select (exclusive).
        :param closed_wait: Time to wait in seconds if no polls are open
                        before checking again.
        :param open_wait: Time to wait in seconds if a poll is open
                        before answering.
        :param lifetime: Lifetime of this PollBot (in seconds).
                        If float('inf'), runs forever.
        :param status_callback: Optional callback function to receive status updates.
                        Called with (message, message_type) where message_type is
                        one of "info", "success", "warning", or "danger".
        :raises ValueError: if login_type is not 'uw' or 'pollev'.
        """
        if login_type not in {'uw', 'pollev'}:
            raise ValueError(f"'{login_type}' is not a supported login type. "
                             f"Use 'uw' or 'pollev'.")
        if login_type == 'pollev' and user.strip().lower().endswith('@uw.edu'):
            logger.warning(f"{user} looks like a UW email. "
                           f"Use login_type='uw' to log in with MyUW.")

        self.user = user
        self.password = password
        self.host = host
        self.login_type = login_type
        # 0-indexed minimum and maximum option
        # indices to select on poll.
        self.min_option = min_option
        self.max_option = max_option
        # Wait time in seconds if poll is
        # closed or open, respectively
        self.closed_wait = closed_wait
        self.open_wait = open_wait

        self.lifetime = lifetime
        self.start_time = time.time()
        
        # Status callback for providing feedback
        self.status_callback = status_callback
        self.last_poll_check_time = None
        self.last_status_time = None

        # Init claude client if API key is provided
        self.claude_client = ClaudeClient(
            claude_api_key) if claude_api_key else None

        self.response_logger = ResponseLogger(log_file)

        self.session = requests.Session()
        self.session.headers = {
            'user-agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36"
        }
        # IDs of all polls we have answered already
        self.answered_polls = set()

        self.last_error = None

        self.telegram_notifier = None
        if telegram_token:
            self.telegram_notifier = TelegramNotifier(
                token=telegram_token,
                admin_chat_id=telegram_chat_id  # This can be None initially
            )
            self.telegram_notifier.start()

            if not telegram_chat_id:
                logger.info(
                    "No Telegram chat ID provided. Please message your bot with /start to get your chat ID")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.session.close()

    @staticmethod
    def timestamp() -> float:
        return round(time.time() * 1000)

    def _get_csrf_token(self) -> str:
        url = endpoints['csrf'].format(timestamp=self.timestamp())
        return self.session.get(url).json()['token']

    def _pollev_login(self) -> bool:
        """
        Logs into PollEv through pollev.com.
        Returns True on success, False otherwise.
        """
        logger.info("Logging into PollEv through pollev.com.")

        r = self.session.post(endpoints['login'],
                              headers={'x-csrf-token': self._get_csrf_token()},
                              data={'login': self.user, 'password': self.password})
        # If login is successful, PollEv sends an empty HTTP response.
        return not r.text

    def _uw_login(self):
        """
        Logs into PollEv through MyUW.
        Returns True on success, False otherwise.
        """
        import bs4 as bs
        import re

        logger.info("Logging into PollEv through MyUW.")

        r = self.session.get(endpoints['uw_saml'])
        soup = bs.BeautifulSoup(r.text, "html.parser")
        data = soup.find('form', id='idplogindiv')['action']
        session_id = re.findall(r'jsessionid=(.*)\.', data)

        r = self.session.post(endpoints['uw_login'].format(id=session_id),
                              data={
                                  'j_username': self.user,
                                  'j_password': self.password,
                                  '_eventId_proceed': 'Sign in'
        })
        soup = bs.BeautifulSoup(r.text, "html.parser")
        saml_response = soup.find('input', type='hidden')

        # When user authentication fails, UW will send an empty SAML response.
        if not saml_response:
            return False

        r = self.session.post(endpoints['uw_callback'],
                              data={'SAMLResponse': saml_response['value']})
        auth_token = re.findall('pe_auth_token=(.*)', r.url)[0]
        self.session.post(endpoints['uw_auth_token'],
                          headers={'x-csrf-token': self._get_csrf_token()},
                          data={'token': auth_token})
        return True

    def login(self):
        """
        Logs into PollEv.

        :raises LoginError: if login failed.
        """
        if self.login_type.lower() == 'uw':
            success = self._uw_login()
        else:
            success = self._pollev_login()
        if not success:
            raise LoginError("Your username or password was incorrect.")
        logger.info("Login successful.")

    def get_firehose_token(self) -> str:
        """
        Given that the user is logged in, retrieve an AWS firehose token.
        If the poll host is not affiliated with UW, PollEv will return
        a firehose token with a null value.

        :raises ValueError: if the specified poll host is not found.
        """
        from uuid import uuid4
        # Before issuing a token, AWS checks for two visitor cookies that
        # PollEverywhere generates using js. They are random uuids.
        self.session.cookies['pollev_visitor'] = str(uuid4())
        self.session.cookies['pollev_visit'] = str(uuid4())
        url = endpoints['firehose_auth'].format(
            host=self.host,
            timestamp=self.timestamp
        )
        r = self.session.get(url)

        if "presenter not found" in r.text.lower():
            raise ValueError(f"'{self.host}' is not a valid poll host.")
        return r.json()['firehose_token']

    def get_new_poll_id(self, firehose_token=None) -> Optional[tuple[str, str]]:
        # import json

        if firehose_token:
            url = endpoints['firehose_with_token'].format(
                host=self.host,
                token=firehose_token,
                timestamp=self.timestamp
            )
        else:
            url = endpoints['firehose_no_token'].format(
                host=self.host,
                timestamp=self.timestamp
            )
        try:
            r = self.session.get(url, timeout=0.3)
            response_data = r.json()

            # Unique id for poll
            print(response_data)

            # Check for subscription expired error
            if isinstance(response_data.get('message'), str):
                try:
                    error_data = json.loads(response_data['message'])
                    if 'error' in error_data:
                        self.last_error = error_data
                        return None, None
                except json.JSONDecodeError:
                    pass

            poll_id = json.loads(response_data['message'])['uid']
            poll_type = json.loads(response_data['message'])['type']
        # Firehose either doesn't respond or responds with no data if no poll is open.
        except (requests.exceptions.ReadTimeout, KeyError):
            return None, None
        if poll_id in self.answered_polls:
            return None, poll_type
        else:
            self.answered_polls.add(poll_id)
            return poll_id, poll_type

    def answer_poll(self, poll_id, poll_type) -> dict:
        # import random

        print(f"Answering poll {poll_id} of type {poll_type}")

        if poll_type == 'free_text_poll':
            url = endpoints['poll_data_free_text'].format(uid=poll_id)
            poll_data = self.session.get(url).json()
            print(poll_data)

        else:  # multiple_choice
            url = endpoints['poll_data'].format(uid=poll_id)
            poll_data = self.session.get(url).json()
            # print(poll_data)
            options = poll_data['options'][self.min_option:self.max_option]
            # print(options)

        try:
            if self.claude_client:
                # Get Claude's response
                if poll_type == 'free_text_poll':
                    # response = self.claude_client.get_free_text_response(
                    #     question=poll_data['title']
                    # )
                    response = validate_and_retry_response(
                        claude_client=self.claude_client,
                        question=poll_data['title']
                    )

                    if response is None:
                        logger.warning(
                            "Could not get valid response from Claude, skipping poll")
                        return {}

                    # Add question to response for context in Telegram
                    response['question'] = poll_data['title']

                    # Get user confirmation and possibly modified text
                    approved, modified_text = get_user_confirmation(
                        response,
                        self.telegram_notifier,
                        timeout=60.0
                    )

                    if not approved:
                        logger.info("Response cancelled by user")
                        return {}

                    answer = modified_text if modified_text is not None else response['answer']

                    logger.info(f"Using response: {answer}")
                    logger.info(
                        f"Original confidence: {response['confidence']:.2f}")
                    logger.info(f"Original reasoning: {response['reasoning']}")

                    self.response_logger.log_response(poll_data, response)
                else:
                    response = self.claude_client.get_poll_response(
                        question=poll_data['title'],
                        options=options
                    )
                    option_id = options[response['selected_option_id']]['id']

                    # Show multiple choice response for confirmation too
                    # if not get_user_confirmation(response, timeout=10.0):
                    #     logger.info("Response cancelled by user")
                    #     return {}

                    logger.info(f"Claude selected option {option_id} "
                                f"with confidence {response['confidence']:.2f}")
                    logger.info(f"Reasoning: {response['reasoning']}")

                    self.response_logger.log_response(poll_data, response)
            else:
                # Fallback to random selection
                option_id = random.choice(options)['id']
        except IndexError:
            # `options` was empty
            logger.error(f'Could not answer poll: poll only has '
                         f'{len(poll_data["options"])} options but '
                         f'self.min_option was {self.min_option} and '
                         f'self.max_option: {self.max_option}')
            return {}
        if poll_type == 'free_text_poll':
            r = self.session.post(
                endpoints['respond_to_poll_free_text'].format(uid=poll_id),
                headers={'x-csrf-token': self._get_csrf_token()},
                data={'value': answer,
                      'isPending': True, 'source': "pollev_page"}
            )
            return r.json()
        else:
            print(f"Posting to {
                  endpoints["respond_to_poll"].format(uid=poll_id)}")
            r = self.session.post(
                endpoints['respond_to_poll'].format(uid=poll_id),
                headers={'x-csrf-token': self._get_csrf_token()},
                data={'option_id': option_id,
                      'isPending': True, 'source': "pollev_page"}
            )
            return r.json()

    def alive(self):
        return time.time() <= self.start_time + self.lifetime

    def send_status(self, message, message_type="info"):
        """Send a status update via the callback if one is registered"""
        if self.status_callback:
            self.status_callback(message, message_type)
        logger.info(message)
        self.last_status_time = time.time()
        
    def run(self):
        """Runs the script."""
        try:
            self.send_status("Bot starting...", "info")
            self.login()
            self.send_status("Successfully logged in to PollEv", "success")
            token = self.get_firehose_token()
            self.send_status("Connected to PollEv firehose", "success")
        except (LoginError, ValueError) as e:
            error_msg = str(e)
            logger.error(error_msg)
            self.send_status(f"Error: {error_msg}", "danger")
            return

        poll_check_count = 0
        while self.alive():
            self.last_poll_check_time = time.time()
            poll_check_count += 1
            
            # Send heartbeat every 10 poll checks
            if poll_check_count % 10 == 0:
                self.send_status("Bot is running and checking for polls", "info")
                
            poll_id, poll_type = self.get_new_poll_id(token)

            if poll_id is None:
                # Check if it was an expired subscription
                if isinstance(getattr(self, 'last_error', None), dict) and \
                   self.last_error.get('error', {}).get('type') == 'ExpiredSubscription':
                    self.send_status("Firehose subscription expired, getting new token", "warning")
                    token = self.get_firehose_token()

                    # Reset last_error
                    self.last_error = None
                    continue

                # Only log occasionally to avoid flooding the status messages
                current_time = time.time()
                if self.last_status_time is None or current_time - self.last_status_time > 60:
                    self.send_status(f'No new polls found. Checking again in {self.closed_wait} seconds', "info")
                
                time.sleep(self.closed_wait)
            else:
                self.send_status(f"New poll detected! Waiting {self.open_wait} seconds before responding", "success")
                time.sleep(self.open_wait)
                r = self.answer_poll(poll_id, poll_type)
                if r:
                    self.send_status(f"Successfully answered poll", "success")
                else:
                    self.send_status(f"No answer submitted for poll", "warning")
                logger.info(f'Received response: {r}')
