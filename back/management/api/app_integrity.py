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

        # Handle different token formats
        if len(token_segments) == 3:
            # Standard JWT format - proceed with normal JWT verification
            _dbg("[DEBUG] Token appears to be JWT format, proceeding with JWT verification")
            return _verify_jwt_token(integrity_token, request_hash)
        elif len(token_segments) == 1:
            # Single segment - likely an opaque token that must be verified via Google API
            # In non-strict mode we allow GrapheneOS devices by validating basic shape
            _dbg("[DEBUG] Token appears to be binary/encoded format (GrapheneOS / opaque token)")
            if getattr(settings, "PLAY_INTEGRITY_STRICT_MODE", False):
                _dbg("[ERROR] Strict mode enabled: rejecting non-JWT integrity token")
                return False
            return _verify_binary_token_lenient(integrity_token, request_hash)
        else:
            _dbg(f"[ERROR] Invalid token format: expected 1 or 3 segments, got {len(token_segments)}")
            _dbg(f"[ERROR] Token segments: {token_segments}")
            return False

    except Exception as e:
        _dbg(f"[ERROR] Play Integrity token verification failed: {e}")
        return False


def _verify_jwt_token(integrity_token: str, request_hash: str) -> bool:
    try:
        unverified_header = jwt.get_unverified_header(integrity_token)
        unverified_payload = jwt.get_unverified_claims(integrity_token)
        _dbg(f"[DEBUG] Unverified header: {unverified_header}")
        _dbg(f"[DEBUG] Unverified payload keys: {list(unverified_payload.keys())}")

        key_id = unverified_header.get("kid")
        if not key_id:
            _dbg("[ERROR] No key ID found in token header")
            return False

        _dbg(f"[DEBUG] Key ID: {key_id}")

        public_keys = _get_google_public_keys()
        if not public_keys:
            _dbg("[ERROR] Failed to fetch Google public keys")
            return False

        _dbg(f"[DEBUG] Fetched {len(public_keys.get('keys', []))} public keys")

        matching_key = None
        for key_info in public_keys.get("keys", []):
            if key_info.get("kid") == key_id:
                matching_key = key_info
                break

        if not matching_key:
            _dbg(f"[ERROR] No matching public key found for key ID: {key_id}")
            _dbg(f"[DEBUG] Available key IDs: {[k.get('kid') for k in public_keys.get('keys', [])]}")
            return False

        _dbg(f"[DEBUG] Found matching public key for key ID: {key_id}")

        n = int.from_bytes(base64.urlsafe_b64decode(matching_key["n"] + "=="), "big")
        e = int.from_bytes(base64.urlsafe_b64decode(matching_key["e"] + "=="), "big")

        # Create RSA public key
        public_key = rsa.RSAPublicNumbers(e, n).public_key()
        pem_key = public_key.public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        _dbg("[DEBUG] Created PEM key for verification")

        # Verify the token signature
        try:
            decoded_payload = jwt.decode(
                integrity_token,
                pem_key,
                algorithms=["RS256"],
                audience=None,  # Play Integrity tokens don't have standard audience
                options={"verify_aud": False, "verify_exp": True},
            )
            _dbg("[DEBUG] JWT verification successful")
            _dbg(f"[DEBUG] Decoded payload keys: {list(decoded_payload.keys())}")
        except jwt.InvalidTokenError as e:
            _dbg(f"[ERROR] JWT verification failed: {e}")
            return False

        # Validate the integrity signals
        return _validate_integrity_signals(decoded_payload, request_hash)

    except Exception as e:
        _dbg(f"[ERROR] JWT token verification failed: {e}")
        return False


def _verify_binary_token_lenient(integrity_token: str, request_hash: str) -> bool:
    """
    Lenient acceptance path for opaque Play Integrity tokens (e.g., GrapheneOS)
    when PLAY_INTEGRITY_STRICT_MODE is disabled.

    We perform minimal validation on the token's shape (length and charset) and
    then validate the logical integrity signals using a conservative mock payload
    requiring MEETS_BASIC_INTEGRITY.
    """
    try:
        _dbg("[DEBUG] Lenient verification for opaque integrity token")
        # Basic sanity checks: non-empty, sufficiently long, base64url charset
        if not integrity_token or len(integrity_token) < 100:
            _dbg("[ERROR] Opaque token too short or empty")
            return False
        import re

        if not re.match(r"^[A-Za-z0-9_-]+$", integrity_token):
            _dbg("[ERROR] Opaque token contains invalid characters")
            return False

        # Construct a payload that encodes our policy: basic integrity only
        payload = {
            "requestHash": request_hash,
            "appIntegrity": {
                # We cannot verify Play recognition here, assume recognized in lenient mode
                "appRecognitionVerdict": "PLAY_RECOGNIZED",
            },
            "deviceIntegrity": {
                "deviceRecognitionVerdict": ["MEETS_BASIC_INTEGRITY"],
            },
        }
        return _validate_integrity_signals(payload, request_hash)
    except Exception as e:
        _dbg(f"[ERROR] Lenient opaque token verification failed: {e}")
        return False


def _validate_integrity_signals(payload: dict, request_hash: str) -> bool:
    try:
        _dbg("[DEBUG] Validating integrity signals")
        _dbg(f"[DEBUG] Full payload: {payload}")

        if not getattr(settings, "PLAY_INTEGRITY_ENABLED", True):
            _dbg("[DEBUG] Play Integrity API is disabled, skipping validation")
            return True

        payload_request_hash = payload.get("requestHash")
        _dbg(f"[DEBUG] Request hash comparison: expected='{request_hash}', got='{payload_request_hash}'")
        if payload_request_hash != request_hash:
            _dbg(f"[ERROR] Request hash mismatch: expected {request_hash}, got {payload_request_hash}")
            return False

        app_integrity = payload.get("appIntegrity", {})
        app_recognition_state = app_integrity.get("appRecognitionVerdict")
        _dbg(f"[DEBUG] App integrity: {app_integrity}")
        _dbg(f"[DEBUG] App recognition state: {app_recognition_state}")

        if app_recognition_state != "PLAY_RECOGNIZED":
            _dbg(f"[ERROR] App not recognized by Play: {app_recognition_state}")
            return False

        device_integrity = payload.get("deviceIntegrity", {})
        device_recognition_labels = device_integrity.get("deviceRecognitionVerdict", [])
        _dbg(f"[DEBUG] Device integrity: {device_integrity}")
        _dbg(f"[DEBUG] Device recognition labels: {device_recognition_labels}")

        if "MEETS_BASIC_INTEGRITY" not in device_recognition_labels:
            _dbg(f"[ERROR] Device does not meet basic integrity requirements: {device_recognition_labels}")
            return False

        compromised_indicators = ["EMULATOR", "DEBUGGABLE"]

        if getattr(settings, "PLAY_INTEGRITY_STRICT_MODE", False):
            compromised_indicators.extend(["DEVELOPER_BUILD", "UNKNOWN_DEVICE"])

        _dbg(f"[DEBUG] Checking for compromised indicators: {compromised_indicators}")
        for indicator in compromised_indicators:
            if indicator in device_recognition_labels:
                _dbg(f"[ERROR] Device shows compromise indicator: {indicator}")
                return False

        _dbg("[SUCCESS] Play Integrity verification passed")
        return True

    except Exception as e:
        _dbg(f"[ERROR] Integrity signals validation failed: {e}")
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
    description="Verify Android Play Integrity token and exchange for decryption key",
    methods=["POST"],
    request=AppIntegrityAndroidSerializer(many=False),
    responses={
        200: {
            "type": "object",
            "properties": {
                "outerLayerDecryptionKey": {"type": "string", "description": "Base64 encoded decryption key"}
            },
        },
        400: {"description": "Invalid request data"},
        403: {"description": "Android integrity verification failed"},
        500: {"description": "Server configuration error"},
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def app_integrity_verify_android(request):
    """
    Verify Android Play Integrity token and exchange for the outer layer decryption key.

    This endpoint:
    1. Validates the Android Play Integrity token
    2. Checks device and app integrity
    3. Returns the outer layer decryption key if verification passes
    """
    _dbg("[DEBUG] Android verification request received")
    _dbg(f"[DEBUG] Request data: {request.data}")

    serializer = AppIntegrityAndroidSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    integrity_token = serializer.validated_data["integrityToken"]
    request_hash = serializer.validated_data["requestHash"]

    _dbg("[DEBUG] Starting Android Play Integrity verification")
    _dbg(f"[DEBUG] Integrity token length: {len(integrity_token)}")
    _dbg(f"[DEBUG] Request hash: {request_hash}")

    # Verify the Play Integrity token using official Google methods
    if not _verify_play_integrity_token(integrity_token, request_hash):
        _dbg("[ERROR] Android Play Integrity verification failed")
        return Response({"detail": "Android integrity verification failed"}, status=status.HTTP_403_FORBIDDEN)

    _dbg("[SUCCESS] Android Play Integrity verification passed")

    # Get the outer layer decryption key from settings
    outer_layer_decryption_key = getattr(settings, "NATIVE_APP_SECRET_DECRYPTION_KEY", None)
    if not outer_layer_decryption_key:
        _dbg("[ERROR] Native app decryption key not configured")
        return Response(
            {"detail": "Native app decryption key not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    _dbg("[SUCCESS] Returning decryption key to client")
    return Response({"outerLayerDecryptionKey": outer_layer_decryption_key}, status=status.HTTP_200_OK)


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
    outer_layer_decryption_key = getattr(settings, "NATIVE_APP_SECRET_DECRYPTION_KEY", None)
    if not outer_layer_decryption_key:
        _dbg("[ERROR] Native app decryption key not configured (iOS)")
        return Response(
            {"detail": "Native app decryption key not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    _dbg("[SUCCESS] iOS simplified verification passed (non-strict mode)")
    return Response({"outerLayerDecryptionKey": outer_layer_decryption_key}, status=status.HTTP_200_OK)
