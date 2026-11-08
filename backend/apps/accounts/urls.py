"""Routes d'authentification de la feature 02 : ``/api/v1/auth/``."""

from django.urls import path

from apps.accounts import views

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="auth_register"),
    path("login/", views.LoginView.as_view(), name="auth_login"),
    path("refresh/", views.RefreshView.as_view(), name="auth_refresh"),
    path("logout/", views.LogoutView.as_view(), name="auth_logout"),
    path("password/forgot/", views.PasswordForgotView.as_view(), name="auth_password_forgot"),
    path("password/reset/", views.PasswordResetView.as_view(), name="auth_password_reset"),
    path("password/change/", views.PasswordChangeView.as_view(), name="auth_password_change"),
    path("email/verify/", views.EmailVerifyView.as_view(), name="auth_email_verify"),
    path("email/resend/", views.EmailResendView.as_view(), name="auth_email_resend"),
    path("device/code/", views.DeviceCodeView.as_view(), name="auth_device_code"),
    path("device/token/", views.DeviceTokenView.as_view(), name="auth_device_token"),
    path("device/approve/", views.DeviceApproveView.as_view(), name="auth_device_approve"),
    path("clients/", views.DeviceClientListView.as_view(), name="auth_clients_list"),
    path(
        "clients/<uuid:authorization_id>/",
        views.DeviceClientDetailView.as_view(),
        name="auth_clients_revoke",
    ),
]
