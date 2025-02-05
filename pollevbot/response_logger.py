import json
from datetime import datetime
from pathlib import Path


class ResponseLogger:
    """Simple logger for tracking all poll responses"""

    def __init__(self, log_file="poll_responses.jsonl"):
        self.log_file = Path(log_file)

        # Ensure log directory exists
        self.log_file.parent.mkdir(exist_ok=True)

    def log_response(self, poll_data: dict, claude_response: dict):
        """Log a single response with all relevant details"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "poll_id": poll_data.get("id"),
            "poll_type": poll_data.get("type"),
            "question": poll_data.get("title"),
            "options": poll_data.get("options"),  # Will be None for free text
            "claude_response": claude_response.get("answer") if claude_response else None,
            "confidence": claude_response.get("confidence") if claude_response else None,
            "reasoning": claude_response.get("reasoning") if claude_response else None,
        }

        # Append to log file
        with self.log_file.open("a") as f:
            f.write(json.dumps(log_entry) + "\n")
