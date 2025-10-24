from django.db import models
from django.utils import timezone


class LLMModel(models.Model):
    id = models.CharField(max_length=255, primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField()


# Create your models here.
class ResponseGenerator(models.Model):
    id = models.CharField(max_length=255, primary_key=True)
    llmModel = models.ForeignKey(LLMModel, on_delete=models.CASCADE)
    user_id = models.CharField(max_length=255, null=False)
    chat_history = models.JSONField(default=list)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
