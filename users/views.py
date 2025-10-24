from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from datetime import timedelta
from users.models import UserProfile, RefreshTokenStore
from users.serializers import UserSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
import uuid
import hashlib
import logging

logger = logging.getLogger(__name__)


class SignUPUserView(APIView):

    def post(self, request):
        user_email = request.data.get("email")
        user_password = request.data.get("password")
        first_name = request.data.get("firstName", "")
        last_name = request.data.get("lastName", "")
        role = request.data.get("role", "Viewer")
        user_name = request.data.get("username", "")

        if not user_email or not user_password:
            return Response(
                {"error": "Email and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ✅ Check if user already exists
        if UserProfile.objects.filter(email=user_email).exists():
            return Response(
                {"error": "Email already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if UserProfile.objects.filter(username=user_name).exists():
            return Response(
                {"error": "Username already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ✅ Create user profile
        user = UserProfile.objects.create_user(
            email=user_email,
            password=user_password,
            user_id=f"user_{str(uuid.uuid4())}",
            role=role,
            username=user_name,
            first_name=first_name,
            last_name=last_name,
        )

        # ✅ Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token_str = str(refresh)

        # ✅ Store refresh token securely (store a SHA256 hash)
        hashed_refresh = hashlib.sha256(refresh_token_str.encode()).hexdigest()

        RefreshTokenStore.objects.create(
            user=user,
            token=hashed_refresh,
            expires_at=timezone.now() + timedelta(days=7),  # Adjust as needed
        )

        response = Response(
            {
                "message": "User created successfully.",
                "user_id": user.user_id,
                "access": access_token,
            },
            status=status.HTTP_201_CREATED,
        )

        response.set_cookie(
            key="refresh_token",
            value=refresh_token_str,
            httponly=True,
            secure=False,  # ⚠️ Use HTTPS in production
            samesite="Lax",  # Changed from None to Lax for development
            max_age=7 * 24 * 60 * 60,
        )

        return response


class LoginUserView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        user_email = request.data.get("email")
        user_password = request.data.get("password")

        if not user_email or not user_password:
            return Response(
                {"error": "Email and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = UserProfile.objects.get(email=user_email)
        except UserProfile.DoesNotExist:
            return Response(
                {"error": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.check_password(user_password):
            return Response(
                {"error": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # ✅ Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token_str = str(refresh)

        # ✅ Store hashed refresh token
        hashed_refresh = hashlib.sha256(refresh_token_str.encode()).hexdigest()
        RefreshTokenStore.objects.update_or_create(
            user=user,
            defaults={
                "token": hashed_refresh,
                "expires_at": timezone.now() + timedelta(days=7),
                "revoked": False,
            },
        )

        # ✅ Build response and set HttpOnly cookie
        response = Response(
            {
                "message": "Login successful.",
                "user_id": user.user_id,
                "access": access_token,
            },
            status=status.HTTP_200_OK,
        )

        response.set_cookie(
            key="refresh_token",
            value=refresh_token_str,
            httponly=True,
            secure=False,  # ⚠️ Use HTTPS in production
            samesite="Lax",  # Changed from None to Lax for development
            max_age=7 * 24 * 60 * 60,
        )

        return response


class LogoutUserView(APIView):

    def post(self, request):
        refresh_token_str = request.data.get("refresh")

        if not refresh_token_str:
            return Response(
                {"error": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        hashed_refresh = hashlib.sha256(refresh_token_str.encode()).hexdigest()

        try:
            token_entry = RefreshTokenStore.objects.get(
                token=hashed_refresh, revoked=False
            )
            # ⚡ Mark as revoked instead of deleting
            token_entry.revoked = True
            token_entry.save()
            return Response(
                {"message": "Logout successful."}, status=status.HTTP_200_OK
            )
        except RefreshTokenStore.DoesNotExist:
            return Response(
                {"error": "Invalid or already revoked refresh token."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class RefreshTokenView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        refresh_token_str = request.COOKIES.get("refresh_token")  # 👈 from cookies

        logger.info(f"Refresh token request. Cookies present: {bool(request.COOKIES)}")
        logger.info(f"Refresh token found in cookies: {bool(refresh_token_str)}")

        if not refresh_token_str:
            logger.warning("No refresh token found in cookies")
            return Response(
                {"error": "Refresh token is missing in cookies."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        hashed_refresh = hashlib.sha256(refresh_token_str.encode()).hexdigest()

        try:
            token_entry = RefreshTokenStore.objects.get(
                token=hashed_refresh, revoked=False
            )

            if token_entry.expires_at < timezone.now():
                # Mark expired token as revoked
                token_entry.revoked = True
                token_entry.save()
                return Response(
                    {"error": "Refresh token has expired."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validate the actual JWT token
            try:
                refresh = RefreshToken(refresh_token_str)
                access_token = str(refresh.access_token)

                return Response({"access": access_token}, status=status.HTTP_200_OK)

            except Exception as jwt_error:
                # If JWT validation fails, mark token as revoked
                token_entry.revoked = True
                token_entry.save()
                return Response(
                    {"error": f"Invalid JWT token: {str(jwt_error)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        except RefreshTokenStore.DoesNotExist:
            logger.warning(
                f"Refresh token not found in database for hash: {hashed_refresh[:10]}..."
            )
            return Response(
                {"error": "Invalid or revoked refresh token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            logger.error(f"Unexpected error in token refresh: {str(e)}")
            return Response(
                {"error": f"Token refresh failed: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class UserProfileView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # ✅ request.user is already the user from the token
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        user = request.user

        # List of fields that can be updated (exclude password)
        updatable_fields = [
            "username",
            "first_name",
            "last_name",
            "profile_picture",
            "role",
            "phone_number",
            "company_name",
            "job_title",
            "date_of_birth",
            "address",
            "description",
        ]

        # Loop through fields and update if present in request
        for field in updatable_fields:
            if field in request.data:
                setattr(user, field, request.data[field])

        user.save()
        serializer = UserSerializer(user)
        return Response(
            {"message": "Profile updated successfully.", "user": serializer.data},
            status=status.HTTP_200_OK,
        )
