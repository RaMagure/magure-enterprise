from rest_framework import serializers
from .models import UserProfile as User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "user_id",
            "username",
            "email",
            "profile_picture",
            "first_name",
            "last_name",
            "role",
            "phone_number",
            "company_name",
            "job_title",
            "date_of_birth",
            "address",
            "description",
            "created_at",
            "updated_at",
        ]
