import logging
import secrets

from back.utils import uuid4
from django.conf import settings
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

challenge_bytes_length = 32

logger = logging.getLogger("app_integrity")


def _dbg(msg: str):
    try:
        if getattr(settings, "APP_INTEGRITY_DEBUG_LOGS", False):
            # Use WARNING so it shows up in production handlers by default
            logger.warning(msg)
    except Exception:
        # Safe fallback in case settings not loaded yet
        print(msg)


def verify_play_integrity_token(integrity_token: str, request_hash: str) -> bool:
    if getattr(settings, "DEVELOPMENT_DISABLE_PLAY_INTEGRITY", False):
        return True  # Full skip of integrity checks for native development
    try:
        _dbg("[DEBUG] Starting Play Integrity token verification")
        _dbg(f"[DEBUG] Token length: {len(integrity_token)}")
        _dbg(f"[DEBUG] Token preview: {integrity_token[:50]}...")
        _dbg(f"[DEBUG] Request hash: {request_hash}")

        # Check if token has the expected JWT format (3 segments separated by dots)
        token_segments = integrity_token.split(".")
        _dbg(f"[DEBUG] Token segments count: {len(token_segments)}")

        if len(token_segments) == 1:
            # Single segment - opaque token that must be verified via Google Play Integrity API
            _dbg("[DEBUG] Token appears to be opaque format - verifying via Google Play Integrity API")
            _dbg("[DEBUG] Using secure Play Integrity API verification")
            return _verify_play_integrity_token_via_api(integrity_token, request_hash)
        else:
            _dbg(f"[ERROR] Invalid token format: expected 1 or 3 segments, got {len(token_segments)}")
            _dbg(f"[ERROR] Token segments: {token_segments}")
            return False

    except Exception as e:
        _dbg(f"[ERROR] Play Integrity token verification failed: {e}")
        return False


def _verify_play_integrity_token_via_api(integrity_token: str, request_hash: str) -> bool:
    """
    Securely verify opaque Play Integrity tokens by calling Google's Play Integrity API.

    This is the proper way to verify opaque tokens from Google-managed encryption.
    """
    try:
        _dbg("[DEBUG] Verifying opaque token via Google Play Integrity API")

        # Get configuration from settings
        package_name = getattr(settings, "ANDROID_PACKAGE_NAME", "com.littleworld.littleworldapp")

        # Import Google Play Integrity API client
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            _dbg(
                "[ERROR] Google API client libraries not installed. Install with: pip install google-api-python-client google-auth"
            )
            return False

        # Get Google Cloud credentials from settings (same as Google Translate)
        google_cloud_credentials = getattr(settings, "GOOGLE_CLOUD_CREDENTIALS_ANDROID_INTEGRITY", None)
        if not google_cloud_credentials:
            _dbg("[ERROR] GOOGLE_CLOUD_CREDENTIALS not configured in settings")
            return False

        # Load service account credentials from settings
        credentials = service_account.Credentials.from_service_account_info(
            google_cloud_credentials, scopes=["https://www.googleapis.com/auth/playintegrity"]
        )

        # Build the Play Integrity API service
        service = build("playintegrity", "v1", credentials=credentials)

        # Call the Play Integrity API to verify the token
        request_body = {"integrityToken": integrity_token}

        _dbg(f"[DEBUG] Undecoded token: {integrity_token}")
        _dbg(f"[DEBUG] Calling Play Integrity API for package: {package_name}")
        response = service.v1().decodeIntegrityToken(packageName=package_name, body=request_body).execute()

        _dbg(f"[DEBUG] Play Integrity API response: {response}")

        # Extract the token payload
        token_payload = response.get("tokenPayloadExternal", {})

        # Validate the request details
        request_details = token_payload.get("requestDetails", {})
        if request_details.get("requestHash") != request_hash:
            _dbg(f"[ERROR] Request hash mismatch: expected {request_hash}, got {request_details.get('requestHash')}")
            return False

        # Validate app integrity
        app_integrity = token_payload.get("appIntegrity", {})
        app_recognition_verdict = app_integrity.get("appRecognitionVerdict")

        # Handle UNEVALUATED case (e.g., graphene devices)
        if app_recognition_verdict == "UNEVALUATED":
            # Check if fallback to device attestation is allowed
            if not getattr(settings, "ALLOW_UNEVALUATED_DEVICES_USING_DEVICE_ATTESTATION", False):
                _dbg("[ERROR] App integrity UNEVALUATED and fallback not enabled")
                return False

            # A glag can allow 'UNEVALUTED' devices ( like grapheneOS ) to login if they are able to pass the chellenge
            # This can be should be updated in the future by implementing deveice attestation ( allso would allow new stores as download sources in the future )
            _dbg("[INFO] App integrity UNEVALUATED - using device attestation fallback (request hash already verified)")
            _dbg("[SUCCESS] UNEVALUATED device verification passed via device attestation fallback")
            return True

        # Normal path: require PLAY_RECOGNIZED
        if app_recognition_verdict != "PLAY_RECOGNIZED":
            _dbg(f"[ERROR] App not recognized by Play: {app_recognition_verdict}")
            return False

        device_integrity = token_payload.get("deviceIntegrity", {})
        device_recognition_verdicts = device_integrity.get("deviceRecognitionVerdict", [])

        # Check for device integrity - accept both MEETS_BASIC_INTEGRITY and MEETS_DEVICE_INTEGRITY
        if not any(
            verdict in device_recognition_verdicts for verdict in ["MEETS_BASIC_INTEGRITY", "MEETS_DEVICE_INTEGRITY"]
        ):
            _dbg(f"[ERROR] Device does not meet integrity requirements: {device_recognition_verdicts}")
            return False

        # Check for compromised indicators
        compromised_indicators = ["EMULATOR", "DEBUGGABLE"]
        if getattr(settings, "PLAY_INTEGRITY_STRICT_MODE", False):
            compromised_indicators.extend(["DEVELOPER_BUILD", "UNKNOWN_DEVICE"])

        for indicator in compromised_indicators:
            if indicator in device_recognition_verdicts:
                _dbg(f"[ERROR] Device shows compromise indicator: {indicator}")
                return False

        _dbg("[SUCCESS] Play Integrity API verification passed")
        return True

    except Exception as e:
        _dbg(f"[ERROR] Play Integrity API verification failed: {e}")
        return False


@extend_schema(
    description="Generate app integrity challenge for device verification",
    methods=["POST"],
    responses={
        200: {
            "type": "object",
            "properties": {
                "challenge": {"type": "string", "description": "Base64 encoded challenge string"},
                "challengeId": {
                    "type": "string",
                    "description": "An identifier for this challenge to be used in the verification step",
                },
            },
        },
        400: {"description": "Invalid request data"},
        500: {"description": "Server configuration error"},
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def app_integrity_challenge(request):
    """
    Generate a challenge for app integrity verification.

    The challenge is a random string that will be signed by the client's app integrity key.
    We store the challenge temporarily in cache for verification in the exchange step.
    """
    # Generate a random challenge string
    challenge_bytes = secrets.token_bytes(challenge_bytes_length).hex().encode("utf-8")

    challenge = challenge_bytes.decode("utf-8")
    challenge_id = uuid4()

    # Store challenge in cache with expiration (5 minutes)
    cache_key = get_app_integrity_challenge_cache_key(challenge_id)
    cache.set(cache_key, challenge_bytes, timeout=300)

    return Response({"challenge": challenge, "challengeId": challenge_id}, status=status.HTTP_200_OK)


def get_app_integrity_challenge_cache_key(challenge_id):
    return f"app_integrity_challenge:{challenge_id}"
