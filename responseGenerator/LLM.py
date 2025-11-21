from llama_index.llms.openai import OpenAI
from llama_index.llms.gemini import Gemini
from llama_index.core.llms import ChatMessage
from redisvl.extensions.message_history import MessageHistory
from redisvl.extensions.message_history import SemanticMessageHistory


class LLM:
    def __init__(self, api_key: str, selected_model: str):
        self.api_key = api_key
        self.selected_model = selected_model
        self.model = None
        self.semantic_history = SemanticMessageHistory(
            name="tutor",
            redis_url="redis://:redis123@localhost:6379/0",
            distance_threshold=0.8,
            device="cuda:0",
        )
        self.__initialize_llm__()

    def __initialize_llm__(self):
        """Initialize the appropriate LLM based on the selected model name."""
        if self.selected_model.lower().startswith("gpt"):
            self.model = OpenAI(
                api_key=self.api_key,
                model="gpt-4o-mini",  # Changed from o1-mini to gpt-4o-mini for better compatibility
                system_prompt="You are a helpful assistant. Reason step by step. read the past messages carefully for more personalized responses.",
            )
        elif self.selected_model.lower().startswith("gemini"):
            self.model = Gemini(
                api_key=self.api_key,
                model="models/gemini-1.5-flash",
                system_prompt="You are a helpful assistant. Reason step by step. read the past messages carefully for more personalized responses.",
            )
        else:
            raise ValueError(f"Unsupported model: {self.selected_model}")
        return self.model

    def change_model(self, new_model: str):
        """Change the LLM model dynamically."""
        self.selected_model = new_model
        self.model = self.__initialize_llm__()
        return self.model

    def _get_chat_messages(self, prompt: str):
        """Convert Redis message history into ChatMessage objects."""
        messages = []
        context = self.semantic_history.get_relevant(
            prompt, top_k=10, role=["system", "llm", "tool", "user"]
        )

        for msg in context:
            role = msg["role"]
            if role == "llm":
                role = "assistant"
            content = msg["content"]
            if role and content:
                messages.append(ChatMessage(role=role, content=content))
        return messages

    def chat(self, prompt: str) -> str:
        """Generate a response from the LLM and maintain conversation context."""
        if not self.model:
            raise ValueError("LLM model is not initialized.")

        # Convert stored messages to LlamaIndex chat format
        chat_messages = self._get_chat_messages(prompt)
        chat_messages.append(ChatMessage(role="user", content=prompt))
        print("======================================>", chat_messages)

        self.semantic_history.add_message({"role": "user", "content": prompt})
        # Get model response
        response = self.model.chat(chat_messages)
        reply = (
            response.message.content.strip()
            if response.message and response.message.content
            else ""
        )

        # Store assistant response back into Redis history
        self.semantic_history.add_message({"role": "llm", "content": reply})
        return reply

    def reset_chat(self):

        self.semantic_history.clear()
