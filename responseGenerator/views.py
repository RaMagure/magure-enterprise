from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from responseGenerator.LLM import LLM


class llmInitializer:
    def __init__(self, api_key: str, selected_model: str):
        self.api_key = api_key
        self.selected_model = selected_model

    def initialize(self):
        # Initialize the LLM with the provided API key and model
        llm = LLM(api_key=self.api_key, selected_model=self.selected_model)
        return llm


# Create your views here.
class ResponseGeneratorView(APIView):
    def post(self, request):
        # Logic for generating response
        return Response(
            {"message": "Response generated successfully"}, status=status.HTTP_200_OK
        )
