from django.urls import path
from users.views import (
    SignUPUserView,
    LoginUserView,
    LogoutUserView,
    RefreshTokenView,
    UserProfileView,
)


urlpatterns = [
    path("signup-user/", SignUPUserView.as_view(), name="signup"),
    path("login-user/", LoginUserView.as_view(), name="login"),
    path("logout-user/", LogoutUserView.as_view(), name="logout"),
    path("refresh-token/", RefreshTokenView.as_view(), name="refresh"),
    path("user-info/", UserProfileView.as_view(), name="user-info"),
]
