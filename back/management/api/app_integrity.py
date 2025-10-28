import base64
import logging
import os
import secrets
import time

import jwt
import pyattest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from pyattest.configs.apple import AppleConfig
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


class AppIntegrityChallengeSerializer(serializers.Serializer):
    keyId = serializers.CharField(max_length=255, required=True)

    def validate_keyId(self, value):
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("keyId cannot be empty")
        return value.strip()


class AppIntegrityExchangeSerializer(serializers.Serializer):
    keyId = serializers.CharField(max_length=255, required=True)
    attestationObject = serializers.CharField(required=True)

    def validate_keyId(self, value):
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("keyId cannot be empty")
        return value.strip()

    def validate_attestationObject(self, value):
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("attestationObject cannot be empty")
        return value.strip()


class AppIntegrityAndroidSerializer(serializers.Serializer):
    integrityToken = serializers.CharField(required=True)
    requestHash = serializers.CharField(required=True)

    def validate_integrityToken(self, value):
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("integrityToken cannot be empty")
        return value.strip()

    def validate_requestHash(self, value):
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("requestHash cannot be empty")
        return value.strip()


class AppIntegrityIOSSerializer(serializers.Serializer):
    keyId = serializers.CharField(max_length=255, required=True)
    attestationObject = serializers.CharField(required=True)

    def validate_keyId(self, value):
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("keyId cannot be empty")
        return value.strip()

    def validate_attestationObject(self, value):
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("attestationObject cannot be empty")
        return value.strip()


logger = logging.getLogger("app_integrity")


def _dbg(msg: str):
    try:
        if getattr(settings, "APP_INTEGRITY_DEBUG_LOGS", False):
            # Use WARNING so it shows up in production handlers by default
            logger.warning(msg)
    except Exception:
        # Safe fallback in case settings not loaded yet
        print(msg)


def _get_google_public_keys():
    """
    Get Public Google API keys, required for device integrity verification.
    """
    try:
        response = requests.get("https://www.googleapis.com/oauth2/v3/certs", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        _dbg(f"[ERROR] Failed to fetch Google public keys: {e}")
        return None


def _verify_play_integrity_token(integrity_token: str, request_hash: str) -> bool:
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
            # TODO: implement fallback for graphene devices!
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
            _dbg("[ERROR] Google API client libraries not installed. Install with: pip install google-api-python-client google-auth")
            return False
        
        # Get Google Cloud credentials from settings (same as Google Translate)
        google_cloud_credentials = getattr(settings, "GOOGLE_CLOUD_CREDENTIALS_ANDROID_INTEGRITY", None)
        if not google_cloud_credentials:
            _dbg("[ERROR] GOOGLE_CLOUD_CREDENTIALS not configured in settings")
            return False
        
        # Load service account credentials from settings
        credentials = service_account.Credentials.from_service_account_info(
            google_cloud_credentials,
            scopes=['https://www.googleapis.com/auth/playintegrity']
        )
        
        # Build the Play Integrity API service
        service = build('playintegrity', 'v1', credentials=credentials)
        
        # Call the Play Integrity API to verify the token
        request_body = {
            'integrityToken': integrity_token
        }
        
        _dbg(f"[DEBUG] Undecoded token: {integrity_token}")
        _dbg(f"[DEBUG] Calling Play Integrity API for package: {package_name}")
        response = service.v1().decodeIntegrityToken(
            packageName=package_name,
            body=request_body
        ).execute()
        
        _dbg(f"[DEBUG] Play Integrity API response: {response}")
        
        # Extract the token payload
        token_payload = response.get('tokenPayloadExternal', {})
        
        # Validate the request details
        request_details = token_payload.get('requestDetails', {})
        if request_details.get('requestHash') != request_hash:
            _dbg(f"[ERROR] Request hash mismatch: expected {request_hash}, got {request_details.get('requestHash')}")
            return False
        
        # Validate app integrity
        app_integrity = token_payload.get('appIntegrity', {})
        app_recognition_verdict = app_integrity.get('appRecognitionVerdict')
        
        # Handle UNEVALUATED case (e.g., graphene devices)
        if app_recognition_verdict == 'UNEVALUATED':
            # Check if fallback to device attestation is allowed
            if not getattr(settings, "ALLOW_UNEVALUATED_DEVICES_USING_DEVICE_ATTESTATION", False):
                _dbg(f"[ERROR] App integrity UNEVALUATED and fallback not enabled")
                return False
            
            # TODO: in the future, implement actual device attestation verification here ( allows devices like grapheneOS to also log-in )
            _dbg("[INFO] App integrity UNEVALUATED - using device attestation fallback (request hash already verified)")
            _dbg("[SUCCESS] UNEVALUATED device verification passed via device attestation fallback")
            return True
        
        # Normal path: require PLAY_RECOGNIZED
        if app_recognition_verdict != 'PLAY_RECOGNIZED':
            _dbg(f"[ERROR] App not recognized by Play: {app_recognition_verdict}")
            return False
        
        # Validate device integrity
        # TODO: add a simple fallback for graphene! Here integrity will not pass!
        device_integrity = token_payload.get('deviceIntegrity', {})
        device_recognition_verdicts = device_integrity.get('deviceRecognitionVerdict', [])
        
        # Check for device integrity - accept both MEETS_BASIC_INTEGRITY and MEETS_DEVICE_INTEGRITY
        if not any(verdict in device_recognition_verdicts for verdict in ['MEETS_BASIC_INTEGRITY', 'MEETS_DEVICE_INTEGRITY']):
            _dbg(f"[ERROR] Device does not meet integrity requirements: {device_recognition_verdicts}")
            return False
        
        # Check for compromised indicators
        compromised_indicators = ['EMULATOR', 'DEBUGGABLE']
        if getattr(settings, "PLAY_INTEGRITY_STRICT_MODE", False):
            compromised_indicators.extend(['DEVELOPER_BUILD', 'UNKNOWN_DEVICE'])
        
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
    request=AppIntegrityChallengeSerializer(many=False),
    responses={
        200: {
            "type": "object",
            "properties": {"challenge": {"type": "string", "description": "Base64 encoded challenge string"}},
        },
        400: {"description": "Invalid request data"},
        500: {"description": "Server configuration error"},
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def app_integrity_challenge(request):
    """
    Generate a challenge for app integrity verification.

    The challenge is a random string that will be signed by the client's app integrity key.
    We store the challenge temporarily in cache for verification in the exchange step.
    """
    serializer = AppIntegrityChallengeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    key_id = serializer.validated_data["keyId"]

    # Generate a random challenge string
    challenge_bytes = secrets.token_bytes(32)

    challenge = challenge_bytes.hex().encode("utf-8").decode("utf-8")
    # challenge = base64.b64encode(challenge_bytes).decode("utf-8")
    # challenge = challenge_bytes.encode("utf-8")  # Convert to hex string for easier handling
    # challenge = hashlib.sha256(challenge_bytes).hexdigest()

    # Store challenge in cache with expiration (5 minutes)
    cache_key = f"app_integrity_challenge:{key_id}:{challenge}"
    cache.set(
        cache_key, {"keyId": key_id, "timestamp": time.time(), "challenge": challenge}, timeout=300
    )  # 5 minutes timeout
    cache.set(key_id, challenge_bytes, timeout=300)

    return Response({"challenge": challenge}, status=status.HTTP_200_OK)

@extend_schema(
    description="Verify iOS App Attest (simplified staging flow) and exchange for decryption key",
    methods=["POST"],
    request=AppIntegrityIOSSerializer(many=False),
    responses={
        200: {
            "type": "object",
            "properties": {
                "outerLayerDecryptionKey": {"type": "string", "description": "Base64 encoded decryption key"}
            },
        },
        400: {"description": "Invalid request data or expired challenge"},
        403: {"description": "iOS integrity verification failed"},
        500: {"description": "Server configuration error"},
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def app_integrity_verify_ios(request):
    """
    Staging-safe iOS verification flow:
    - Validates presence of keyId and attestationObject
    - Attempts to parse JSON attestation to extract challenge
    - Verifies that challenge exists in cache (created by /challenge) and not expired
    - In non-strict mode, accepts and returns key (we do not yet perform full App Attest statement verification)
    - In strict mode (future), we would implement full Apple App Attest verification
    """
    _dbg("[DEBUG] iOS verification request received")
    _dbg(f"[DEBUG] Request data: {request.data}")

    serializer = AppIntegrityIOSSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    key_id = serializer.validated_data["keyId"]
    attestation_object = serializer.validated_data["attestationObject"]

    challenge = cache.get(key=key_id)

    apple_team_id = os.environ.get("APPLE_TEAM_ID")
    app_bundle_identifier = os.environ.get("APP_BUNDLE_IDENTIFIER")

    config = AppleConfig(key_id=key_id, app_id=f"{apple_team_id}.{app_bundle_identifier}", production=settings.IS_PROD)
    attestation = pyattest.attestation.Attestation(raw=attestation_object, nonce=challenge, config=config)

    # Extract challenge from attestation object (expect JSON with field 'challenge')
    try:
        attestation.verify()
        # attestation_object_decoded = base64.b64decode(attestation_object)
        # attestation = cbor2.loads(attestation_object_decoded)

        # fmt = attestation.get("fmt")
        # att_stmt = attestation.get("attStmt", {})
        # auth_data = attestation.get("authData")

        # attestation_cert_chain = att_stmt.get("x5c")
        # signature = att_stmt.get("sig")
        # attestation_data = json.loads(base64.b64decode(attestation_object))
        # challenge = attestation_data.get("challenge")
    except Exception as e:
        _dbg(f"[ERROR] Invalid iOS attestationObject format: {e}")
        return Response({"detail": "Invalid attestation object format"}, status=status.HTTP_400_BAD_REQUEST)

    # if not challenge:
    #     _dbg("[ERROR] Missing challenge in iOS attestationObject")
    #     return Response({"detail": "Missing challenge in attestation"}, status=status.HTTP_400_BAD_REQUEST)

    # cache_key = f"app_integrity_challenge:{key_id}:{challenge}"
    # cached_data = cache.get(cache_key)
    # if not cached_data:
    #     _dbg("[ERROR] iOS challenge not found or expired")
    #     return Response({"detail": "Invalid or expired challenge"}, status=status.HTTP_400_BAD_REQUEST)

    # # Expiry check (5 minutes)
    # if abs(time.time() - cached_data["timestamp"]) > 300:
    #     cache.delete(cache_key)
    #     _dbg("[ERROR] iOS challenge expired")
    #     return Response({"detail": "Challenge expired"}, status=status.HTTP_400_BAD_REQUEST)

    # # For now: accept in non-strict mode (staging), reject in strict mode until full verification is implemented
    # if getattr(settings, "PLAY_INTEGRITY_STRICT_MODE", False):
    #     cache.delete(cache_key)
    #     _dbg("[ERROR] iOS verification requires strict mode attestation (not implemented)")
    #     return Response(
    #         {"detail": "iOS attestation strict verification not implemented"}, status=status.HTTP_403_FORBIDDEN
    #     )

    cache.delete(key=key_id)
    outer_layer_decryption_key = getattr(settings, "ANDROID_DECRYPTION_KEY", None)
    if not outer_layer_decryption_key:
        _dbg("[ERROR] Native app decryption key not configured (iOS)")
        return Response(
            {"detail": "Native app decryption key not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    _dbg("[SUCCESS] iOS simplified verification passed (non-strict mode)")
    return Response({"outerLayerDecryptionKey": outer_layer_decryption_key}, status=status.HTTP_200_OK)
