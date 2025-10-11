import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict
from django.urls import path

import jwt
import requests
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import base64


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


def _get_google_public_keys():
    """
    Get Public Google API keys, required for device integrity verification.
    """
    try:
        response = requests.get('https://www.googleapis.com/oauth2/v3/certs', timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Failed to fetch Google public keys: {e}")
        return None


def _verify_play_integrity_token(integrity_token: str, request_hash: str) -> bool:
    try:
        print(f"[DEBUG] Starting Play Integrity token verification")
        print(f"[DEBUG] Token length: {len(integrity_token)}")
        print(f"[DEBUG] Token preview: {integrity_token[:50]}...")
        print(f"[DEBUG] Request hash: {request_hash}")
        
        # Check if token has the expected JWT format (3 segments separated by dots)
        token_segments = integrity_token.split('.')
        print(f"[DEBUG] Token segments count: {len(token_segments)}")
        
        # Handle different token formats
        if len(token_segments) == 3:
            # Standard JWT format - proceed with normal JWT verification
            print(f"[DEBUG] Token appears to be JWT format, proceeding with JWT verification")
            return _verify_jwt_token(integrity_token, request_hash)
        elif len(token_segments) == 1:
            # Single segment - likely a binary/encoded token from GrapheneOS
            print(f"[DEBUG] Token appears to be binary/encoded format from GrapheneOS")
            return False # TODO: unimplemented!
        else:
            print(f"[ERROR] Invalid token format: expected 1 or 3 segments, got {len(token_segments)}")
            print(f"[ERROR] Token segments: {token_segments}")
            return False
        
    except Exception as e:
        print(f"[ERROR] Play Integrity token verification failed: {e}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return False


def _verify_jwt_token(integrity_token: str, request_hash: str) -> bool:
    try:
        unverified_header = jwt.get_unverified_header(integrity_token)
        unverified_payload = jwt.get_unverified_claims(integrity_token)
        print(f"[DEBUG] Unverified header: {unverified_header}")
        print(f"[DEBUG] Unverified payload keys: {list(unverified_payload.keys())}")
        
        key_id = unverified_header.get('kid')
        if not key_id:
            print("[ERROR] No key ID found in token header")
            return False
        
        print(f"[DEBUG] Key ID: {key_id}")
        
        public_keys = _get_google_public_keys()
        if not public_keys:
            print("[ERROR] Failed to fetch Google public keys")
            return False
        
        print(f"[DEBUG] Fetched {len(public_keys.get('keys', []))} public keys")
        
        matching_key = None
        for key_info in public_keys.get('keys', []):
            if key_info.get('kid') == key_id:
                matching_key = key_info
                break
        
        if not matching_key:
            print(f"[ERROR] No matching public key found for key ID: {key_id}")
            print(f"[DEBUG] Available key IDs: {[k.get('kid') for k in public_keys.get('keys', [])]}")
            return False
        
        print(f"[DEBUG] Found matching public key for key ID: {key_id}")
        
        
        n = int.from_bytes(base64.urlsafe_b64decode(matching_key['n'] + '=='), 'big')
        e = int.from_bytes(base64.urlsafe_b64decode(matching_key['e'] + '=='), 'big')
        
        # Create RSA public key
        public_key = rsa.RSAPublicNumbers(e, n).public_key()
        pem_key = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        print(f"[DEBUG] Created PEM key for verification")
        
        # Verify the token signature
        try:
            decoded_payload = jwt.decode(
                integrity_token,
                pem_key,
                algorithms=['RS256'],
                audience=None,  # Play Integrity tokens don't have standard audience
                options={"verify_aud": False, "verify_exp": True}
            )
            print(f"[DEBUG] JWT verification successful")
            print(f"[DEBUG] Decoded payload keys: {list(decoded_payload.keys())}")
        except jwt.InvalidTokenError as e:
            print(f"[ERROR] JWT verification failed: {e}")
            return False
        
        # Validate the integrity signals
        return _validate_integrity_signals(decoded_payload, request_hash)
        
    except Exception as e:
        print(f"[ERROR] JWT token verification failed: {e}")
        return False


def _validate_integrity_signals(payload: dict, request_hash: str) -> bool:
    try:
        print(f"[DEBUG] Validating integrity signals")
        print(f"[DEBUG] Full payload: {payload}")
        
        if not getattr(settings, 'PLAY_INTEGRITY_ENABLED', True):
            print("[DEBUG] Play Integrity API is disabled, skipping validation")
            return True
        
        payload_request_hash = payload.get('requestHash')
        print(f"[DEBUG] Request hash comparison: expected='{request_hash}', got='{payload_request_hash}'")
        if payload_request_hash != request_hash:
            print(f"[ERROR] Request hash mismatch: expected {request_hash}, got {payload_request_hash}")
            return False
        
        app_integrity = payload.get('appIntegrity', {})
        app_recognition_state = app_integrity.get('appRecognitionVerdict')
        print(f"[DEBUG] App integrity: {app_integrity}")
        print(f"[DEBUG] App recognition state: {app_recognition_state}")
        
        if app_recognition_state != 'PLAY_RECOGNIZED':
            print(f"[ERROR] App not recognized by Play: {app_recognition_state}")
            return False
        
        device_integrity = payload.get('deviceIntegrity', {})
        device_recognition_labels = device_integrity.get('deviceRecognitionVerdict', [])
        print(f"[DEBUG] Device integrity: {device_integrity}")
        print(f"[DEBUG] Device recognition labels: {device_recognition_labels}")
        
        if 'MEETS_BASIC_INTEGRITY' not in device_recognition_labels:
            print(f"[ERROR] Device does not meet basic integrity requirements: {device_recognition_labels}")
            return False
        
        compromised_indicators = [
            'EMULATOR',
            'DEBUGGABLE'
        ]
        
        if getattr(settings, 'PLAY_INTEGRITY_STRICT_MODE', False):
            compromised_indicators.extend([
                'DEVELOPER_BUILD',
                'UNKNOWN_DEVICE'
            ])
        
        print(f"[DEBUG] Checking for compromised indicators: {compromised_indicators}")
        for indicator in compromised_indicators:
            if indicator in device_recognition_labels:
                print(f"[ERROR] Device shows compromise indicator: {indicator}")
                return False
        
        print("[SUCCESS] Play Integrity verification passed")
        return True
        
    except Exception as e:
        print(f"[ERROR] Integrity signals validation failed: {e}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return False


@extend_schema(
    description="Generate app integrity challenge for device verification",
    methods=["POST"],
    request=AppIntegrityChallengeSerializer(many=False),
    responses={
        200: {
            "type": "object",
            "properties": {
                "challenge": {"type": "string", "description": "Base64 encoded challenge string"}
            }
        },
        400: {"description": "Invalid request data"},
        500: {"description": "Server configuration error"}
    }
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
    
    key_id = serializer.validated_data['keyId']
    
    # Generate a random challenge string
    challenge_bytes = secrets.token_bytes(32)
    challenge = challenge_bytes.hex()  # Convert to hex string for easier handling
    
    # Store challenge in cache with expiration (5 minutes)
    cache_key = f"app_integrity_challenge:{key_id}:{challenge}"
    cache.set(cache_key, {
        'keyId': key_id,
        'timestamp': time.time(),
        'challenge': challenge
    }, timeout=300)  # 5 minutes timeout
    
    return Response({
        'challenge': challenge
    }, status=status.HTTP_200_OK)


@extend_schema(
    description="Verify Android Play Integrity token and exchange for decryption key",
    methods=["POST"],
    request=AppIntegrityAndroidSerializer(many=False),
    responses={
        200: {
            "type": "object",
            "properties": {
                "outerLayerDecryptionKey": {"type": "string", "description": "Base64 encoded decryption key"}
            }
        },
        400: {"description": "Invalid request data"},
        403: {"description": "Android integrity verification failed"},
        500: {"description": "Server configuration error"}
    }
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
    print(f"[DEBUG] Android verification request received")
    print(f"[DEBUG] Request data: {request.data}")
    
    serializer = AppIntegrityAndroidSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    integrity_token = serializer.validated_data['integrityToken']
    request_hash = serializer.validated_data['requestHash']
    
    print(f"[DEBUG] Starting Android Play Integrity verification")
    print(f"[DEBUG] Integrity token length: {len(integrity_token)}")
    print(f"[DEBUG] Request hash: {request_hash}")
    
    # Verify the Play Integrity token using official Google methods
    if not _verify_play_integrity_token(integrity_token, request_hash):
        print(f"[ERROR] Android Play Integrity verification failed")
        return Response(
            {"detail": "Android integrity verification failed"}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    print(f"[SUCCESS] Android Play Integrity verification passed")
    
    # Get the outer layer decryption key from settings
    outer_layer_decryption_key = getattr(settings, 'NATIVE_APP_SECRET_DECRYPTION_KEY', None)
    if not outer_layer_decryption_key:
        print(f"[ERROR] Native app decryption key not configured")
        return Response(
            {"detail": "Native app decryption key not configured"}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    print(f"[SUCCESS] Returning decryption key to client")
    return Response({
        'outerLayerDecryptionKey': outer_layer_decryption_key
    }, status=status.HTTP_200_OK)


@extend_schema(
    description="Verify iOS App Attest and exchange for decryption key",
    methods=["POST"],
    request=AppIntegrityIOSSerializer(many=False),
    responses={
        200: {
            "type": "object",
            "properties": {
                "outerLayerDecryptionKey": {"type": "string", "description": "Base64 encoded decryption key"}
            }
        },
        400: {"description": "Invalid request data or expired challenge"},
        403: {"description": "iOS integrity verification failed"},
        500: {"description": "Server configuration error"}
    }
)
@api_view(["POST"])
@permission_classes([AllowAny])
def app_integrity_verify_ios(request):
    # TODO: unimplemented!
    
    return Response({
        'outerLayerDecryptionKey': "" # TODO: unimplemented!
    }, status=status.HTTP_200_OK)


api_urls = [
    path("api/app-integrity/challenge", app_integrity_challenge),
    path("api/app-integrity/verify-android", app_integrity_verify_android),
    # path("api/app-integrity/verify-ios", app_integrity_verify_ios), TODO API Incomplete
]