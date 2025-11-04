import redis
import json
import uuid
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from responseGenerator.LLM import LLM
from responseGenerator.utils import get_user_chat
from django.conf import settings
from .tasks import generate_response
from main.celery import app


class InitializeLLMView(APIView):
    def post(self, request):
        api_key = request.data.get("api_key", settings.OPENAI_API_KEY)
        selected_model = request.data.get("selected_model", "gpt-4.1")
        user_id = request.data.get("user_id")

        if not api_key or not selected_model or not user_id:
            return Response(
                {"error": "user_id, API key, and model are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Connect to Redis
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)

        # Create a unique chat_id
        chat_id = f"chat_{uuid.uuid4()}"
        key = f"llmChat:{user_id}:{chat_id}"

        # Store chat record
        data = {
            "llm_id": f"model_{uuid.uuid4()}",
            "llm_object": json.dumps(
                {
                    "selected_model": selected_model,
                    "api_key": api_key,
                    "chat_id": chat_id,
                }
            ),
        }
        r.hset(key, mapping=data)

        # Also maintain a list of chat IDs for this user
        r.rpush(f"userChats:{user_id}", chat_id)

        return Response(
            {"message": "LLM chat initialized successfully", "chat_id": chat_id},
            status=status.HTTP_200_OK,
        )


class ResponseGeneratorView(APIView):
    def post(self, request):
        # Logic for generating response
        user_id = request.data.get("user_id")
        chat_id = request.data.get("chat_id")
        prompt = request.data.get("prompt")
        if not user_id or not chat_id or not prompt:
            return Response(
                {"error": "user_id, chat_id, and prompt are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        llm = get_user_chat(user_id, chat_id)
        if not llm:
            return Response(
                {"error": "Chat not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        response = app.send_task(
            "responseGenerator.tasks.generate_response",
            args=[prompt, llm, chat_id, user_id],
        )
        return Response(
            {"message": "Response generated successfully", "response": response},
            status=status.HTTP_200_OK,
        )
