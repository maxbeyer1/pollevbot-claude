from anthropic import Anthropic


class ClaudeClient:
    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)

    def get_poll_response(self, question: str, options: list[dict]) -> dict:
        """
        Gets Claude's response for a poll question

        Args:
            question: The poll question text
            options: List of option dictionaries from the poll data

        Returns:
            Dict containing Claude's selected option and confidence
        """
        # Format options for prompt
        formatted_options = "\n".join(
            f"- {opt['humanized_value']}" for opt in options
        )

        # Build the prompt
        prompt = f"""Using the context from the question and the answer choices provided, pick the most likely choice to answer the question. Your pick must be one of the answer choices provided. You may not really have enough context to answer the question, but you must pick what you think is going to be the most likely answer regardless. If you do not pick an answer, you will be fined $100. Focus on picking the answer choice that is most likely as opposed to guaranteeing you are correct.

        Question: {question}

        Answer choices:
        {formatted_options}

        Use the get_poll_answer function to provide your response.
        """

        # Get response using tool schema
        # Get response using tool schema
        message = self.client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=1024,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
            tools=[{
                "name": "get_poll_answer",
                "description": "Select the most likely correct answer for a poll question",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "selected_option_id": {
                            "type": "integer",
                            "description": "The ID of the selected poll option"
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                            "description": "Confidence in the answer on a 0-1 scale"
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Explanation for why this answer was selected"
                        }
                    },
                    "required": ["selected_option_id", "confidence", "reasoning"]
                }
            }],
            tool_choice={"type": "tool", "name": "get_poll_answer"}
        )

        print(message)
        # Extract and return the tool call response
        tool_use = message.content[0]
        return tool_use.input
