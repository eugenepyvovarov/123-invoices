from django.urls import path

from accounts.views import EmailLoginView, EmailLogoutView, OTPVerifyView, user_settings

app_name = "accounts"

urlpatterns = [
    path("login/", EmailLoginView.as_view(), name="login"),
    path("logout/", EmailLogoutView.as_view(), name="logout"),
    path("login/verify/", OTPVerifyView.as_view(), name="otp_verify"),
    path("user-settings/", user_settings, name="user_settings"),
]
