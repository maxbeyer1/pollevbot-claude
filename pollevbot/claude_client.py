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

    def get_free_text_response(self, question: str) -> dict:
        """
        Gets Claude's concise response for a free text question

        Args:
            question: The question text

        Returns:
            Dict containing Claude's response and confidence
        """
        prompt = f"""Answer the following question in a clear and concise way. Do not use any flowery language or anything unneeded. Your response should generally be one sentence or so, unless the specific question demands a longer one. Your answer must be specific and to the point, avoiding unnecessary elaboration. Even if you don't have complete information, provide your best assessment based on what you know.

        Question: {question}

        Use the get_free_text_answer function to provide your response.
        """

        message = self.client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=1024,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
            tools=[{
                "name": "get_free_text_answer",
                "description": "Provide a concise answer to a free text question",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "answer": {
                            "type": "string",
                            "description": "The concise answer to the question"
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                            "description": "Confidence in the answer on a 0-1 scale"
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Brief explanation for the provided answer"
                        }
                    },
                    "required": ["answer", "confidence", "reasoning"]
                }
            }],
            tool_choice={"type": "tool", "name": "get_free_text_answer"}
        )

        tool_use = message.content[0]
        return tool_use.input
