from django.contrib.auth import get_user_model
from django.urls import path
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from management.random_test_users import create_test_user

User = get_user_model()


@api_view(["GET"])
@permission_classes([AllowAny])
def get_user_email_auth_pin(request):
    email = request.query_params.get("email", "").strip().lower()
    if email == "":
        return Response({"error": "Missing required query parameter: email"}, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.filter(email__iexact=email).select_related("state").first()
    if user is None:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    return Response(
        {
            "email": user.email,
            "email_auth_pin": user.state.get_email_auth_pin(),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def ensure_user(request):
    email = str(request.data.get("email", "")).strip().lower()
    password = str(request.data.get("password", "")).strip()
    if email == "" or password == "":
        return Response(
            {"error": "Missing required fields: email, password"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = User.objects.filter(email__iexact=email).select_related("state").first()
    if user is None:
        user = create_test_user(
            1,
            None,
            password,
            email,
            pass_if_exists=True,
            send_verification_mail=False,
        )

    user.set_password(password)
    user.is_active = True
    user.save(update_fields=["password", "is_active"])

    if hasattr(user, "state") and user.state is not None:
        user.state.email_authenticated = True
        user.state.save(update_fields=["email_authenticated"])

    return Response({"email": user.email}, status=status.HTTP_200_OK)


api_urls = [
    path(
        "api/dev/e2e_tests/email_auth_pin/",
        get_user_email_auth_pin,
        name="e2e_tests_get_user_email_auth_pin",
    ),
    path(
        "api/dev/e2e_tests/ensure_user/",
        ensure_user,
        name="e2e_tests_ensure_user",
    ),
]
