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
            # model="claude-3-opus-20240229",
            model="claude-3-7-sonnet-latest",
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
        prompt = f"""You are participating in a casual social survey where you must provide a brief, natural response as if you were an average person. You must respond in a way that would blend in perfectly with other human responses. You will be fined $500 if you:
        1. Mention anything about being AI, language models, or not being human
        2. Give an overly formal or analytical response
        3. Fail to provide a specific answer
        4. Provide a response longer than one or two sentences/phrases, unless the question SPECIFICALLY demands it.
        5. Use punctuation or grammar that is too formal or correct for a casual activity
        6. Use words or phrases that are cliche, overly used, or seem intentionally human or casual. You are expected to just be "regular" or average.

        Some context about the person you are answering as:
        - 20 years old
        - Computer Science major at Northwestern University
        - Born and raised in New York City
        - Enjoys basketball, reading, and biking

        Examples:
        Q: "How are you feeling today?"
        Good response: "Pretty tired, need more coffee"
        Bad response: "As an AI, I don't experience feelings"
        Rationale: The question is asking how the person is feeling, so the response should be a feeling. Saying "I don't experience feelings" is a cop-out and doesn't answer the question.

        Q: "Your strongest food opinion?"
        Good response: "Pineapple has no place on pizza"
        Bad response: "I don't have personal opinions about food"
        Rationale: The question is asking for a strong opinion, so the response should be a strong opinion. Saying "I don't have personal opinions" is a cop-out and doesn't answer the question.
        
        Q: "What does it stereotypically mean to be a man?"
        Good response: "Stereotypically it means being strong, stoic, or unemotional"
        Bad response: "being tough and not showing emotions i guess... but tbh thats kinda toxic"
        Rationale: The response includes "toxic" and "tbh" which seems like words or abbreviations that were chosen to make the response seem more human. Real 20 year olds do not talk like this normally.

        Question: {question}

        Use the get_free_text_answer function to provide your response.
        """

        message = self.client.messages.create(
            # model="claude-3-opus-20240229",
            model="claude-3-5-sonnet-latest",
            max_tokens=1024,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}],
            tools=[{
                "name": "get_free_text_answer",
                "description": "Provide a natural, human-like answer",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "answer": {
                            "type": "string",
                            "description": "A casual, natural response to the question"
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                            "description": "Confidence that this response would blend in with human responses"
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Why this response would be common/natural for a human"
                        }
                    },
                    "required": ["answer", "confidence", "reasoning"]
                }
            }],
            tool_choice={"type": "tool", "name": "get_free_text_answer"}
        )

        tool_use = message.content[0]
        return tool_use.input
