from typing import Dict, Optional
import re
import logging
import uuid

logger = logging.getLogger(__name__)


class OutputValidator:
    """
    Validator for checking Claude's outputs before submitting them to polls
    """

    # Common phrases that might indicate AI disclosure
    AI_DISCLOSURE_PATTERNS = [
        r'\b(ai|artificial intelligence|language model|llm|claude|assistant)\b',
        r'\bas an ai\b',
        r'\bi am an\b',
        r'\bi cannot\b',
        r'\bi don\'t experience\b',
        r'\bi apologize\b',
    ]

    # Patterns that might indicate overly formal language
    FORMAL_PATTERNS = [
        r'furthermore',
        r'moreover',
        r'thus',
        r'hence',
        r'wherein',
        r'hereby',
        r'nevertheless',
        r'subsequently',
    ]

    # Maximum response length (in characters) for a typical casual response
    MAX_RESPONSE_LENGTH = 150

    # Minimum confidence threshold
    MIN_CONFIDENCE_THRESHOLD = 0.7

    def __init__(self):
        # Compile regex patterns for efficiency
        self.ai_patterns = [re.compile(pattern, re.IGNORECASE)
                            for pattern in self.AI_DISCLOSURE_PATTERNS]
        self.formal_patterns = [re.compile(
            pattern, re.IGNORECASE) for pattern in self.FORMAL_PATTERNS]

    def check_ai_disclosure(self, text: str) -> bool:
        """Check if text contains any AI disclosure patterns"""
        return any(pattern.search(text) for pattern in self.ai_patterns)

    def check_formality(self, text: str) -> bool:
        """Check if text contains overly formal language patterns"""
        return any(pattern.search(text) for pattern in self.formal_patterns)

    def check_length(self, text: str) -> bool:
        """Check if text is within acceptable length"""
        return len(text) <= self.MAX_RESPONSE_LENGTH

    def check_response_structure(self, text: str) -> bool:
        """Check if response structure looks natural"""
        # Check for markdown or unusual formatting
        if '```' in text or '#' in text or '*' in text:
            return False

        # Check for unusual punctuation patterns
        if text.count('.') > 3 or text.count(';') > 0:
            return False

        return True

    def validate_free_text_response(self, response: Dict) -> Optional[str]:
        """
        Validate a free text response from Claude

        Args:
            response: Dictionary containing Claude's response with 'answer' and 'confidence' keys

        Returns:
            Error message if validation fails, None if passes
        """
        answer = response.get('answer', '')
        confidence = response.get('confidence', 0)

        # List to collect all validation failures
        failures = []

        # Check confidence threshold
        if confidence < self.MIN_CONFIDENCE_THRESHOLD:
            failures.append(f"Confidence too low: {confidence}")

        # Check for AI disclosure
        if self.check_ai_disclosure(answer):
            failures.append("Contains AI disclosure patterns")

        # Check formality
        if self.check_formality(answer):
            failures.append("Contains overly formal language")

        # Check length
        if not self.check_length(answer):
            failures.append(f"Response too long ({len(answer)} chars)")

        # Check structure
        if not self.check_response_structure(answer):
            failures.append("Response structure appears unnatural")

        # Return concatenated failure messages or None if passed
        return '; '.join(failures) if failures else None


def validate_and_retry_response(claude_client, question: str, max_retries: int = 3) -> Optional[Dict]:
    """
    Get a response from Claude with validation and retry logic

    Args:
        claude_client: Instance of ClaudeClient
        question: The question to ask
        max_retries: Maximum number of retry attempts

    Returns:
        Valid response dict or None if all attempts fail
    """
    validator = OutputValidator()

    for attempt in range(max_retries):
        response = claude_client.get_free_text_response(question)
        validation_error = validator.validate_free_text_response(response)

        if not validation_error:
            logger.info(f"Valid response obtained on attempt {attempt + 1}")
            return response

        logger.warning(
            f"Attempt {attempt + 1} failed validation: {validation_error}")

    logger.error(f"Failed to get valid response after {max_retries} attempts")
    return None


def _terminal_confirmation(response: Dict, timeout: float = 60.0) -> bool:
    """
    Present Claude's response to the user and wait for confirmation before proceeding.

    Args:
        response: Dictionary containing Claude's response
        timeout: Number of seconds to wait for user input

    Returns:
        Boolean indicating whether to proceed with the response
    """
    import threading
    import sys
    from queue import Queue

    def get_input(queue):
        while True:
            if sys.stdin.readable():
                char = sys.stdin.read(1)
                if char:
                    queue.put(char)
                    break

    print("\n" + "="*50)
    print("CLAUDE'S RESPONSE:")
    print(f"Answer: {response['answer']}")
    print(f"Confidence: {response['confidence']:.2f}")
    print(f"Reasoning: {response['reasoning']}")
    print("="*50)
    print(f"\nPress 'y' to submit this response, any other key to cancel.")
    print(f"You have {timeout} seconds to respond. No response will be treated as a cancel.")  # noqa

    # Set up input queue
    queue = Queue()
    input_thread = threading.Thread(target=get_input, args=(queue,))
    input_thread.daemon = True
    input_thread.start()

    try:
        char = queue.get(timeout=timeout)
        return char.lower() == 'y'
    except:  # Queue.Empty or other issues
        print("\nTimeout reached - cancelling response")
        return False


def get_user_confirmation(response: Dict, telegram_notifier=None, timeout: float = 60.0) -> tuple[bool, Optional[str]]:
    """
    Get confirmation for Claude's response via Telegram or terminal fallback

    Returns:
        Tuple of (approved boolean, optional modified text)
    """
    if telegram_notifier:
        try:
            # Send for approval and wait for response
            response_id = telegram_notifier.send_for_approval(
                response, response.get('question', 'Unknown question'))
            if response_id:
                result = telegram_notifier.wait_for_response(
                    response_id, timeout)
                if result:
                    return (
                        result['status'] == 'approved',
                        result['modified_text']
                    )
        except Exception as e:
            logger.warning(
                f"Telegram notification failed: {e}, falling back to terminal")

    # Fallback to terminal input
    print("\n" + "="*50)
    print("CLAUDE'S RESPONSE:")
    print(f"Answer: {response['answer']}")
    print(f"Confidence: {response['confidence']:.2f}")
    print(f"Reasoning: {response['reasoning']}")
    print("="*50)
    print(f"\nPress 'y' to submit this response, any other key to cancel.")

    try:
        import sys
        if sys.stdin.readable():
            char = sys.stdin.read(1)
            return char.lower() == 'y', None
    except:
        pass

    return False, None
