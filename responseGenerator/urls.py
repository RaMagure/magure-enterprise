from django.urls import path
from responseGenerator.views import ResponseGeneratorView, InitializeLLMView


urlpatterns = [
    path("initialize-llm/", InitializeLLMView.as_view(), name="initialize-llm"),
    path(
        "generate-response/", ResponseGeneratorView.as_view(), name="generate-response"
    ),
]
