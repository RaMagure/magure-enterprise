from django.urls import path
from responseGenerator.views import ResponseGeneratorView


urlpatterns = [
    path(
        "generate-response/", ResponseGeneratorView.as_view(), name="generate-response"
    ),
]
