from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid
from django.utils import timezone


class UserRole(models.TextChoices):
    ADMIN = "admin", "Admin"
    OPERATOR = "operator", "Operator"
    VIEWER = "viewer", "Viewer"


class UserProfile(AbstractUser):
    user_id = models.CharField(max_length=255, default=uuid.uuid4, primary_key=True)
    username = models.CharField(max_length=150, unique=True, null=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    profile_picture = models.URLField(blank=True, null=True)
    role = models.CharField(
        max_length=50, choices=UserRole.choices, default=UserRole.ADMIN
    )
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    company_name = models.CharField(max_length=255, blank=True, null=True)
    job_title = models.CharField(max_length=255, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"{self.username} ({str(self.user_id)})"


class RefreshTokenStore(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    token = models.CharField(max_length=512)  # ⚠️ Prefer storing a SHA256 hash here
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked = models.BooleanField(default=False)

    def __str__(self):
        return f"RefreshToken for {self.user.username} (revoked={self.revoked})"
