import base64
import hashlib

import cbor2
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.constant_time import bytes_eq
from django import settings
from pyasn1.codec.der.decoder import decode as pyasn1_decode
from pyasn1.type.univ import Sequence

OID_APPLE = x509.ObjectIdentifier("1.2.840.113635.100.8.2")


def get_apple_root_certificate() -> x509.Certificate:
    with open("/back/management/integrity/Apple_App_Attestation_Root_CA.pem", "r") as f:
        certificate_bytes = f.read().encode("utf-8")
        return x509.load_pem_x509_certificate(certificate_bytes)


def verify_apple_attestation(key_id, challenge_bytes, attestation_raw, is_prod):
    # Step 1: Decode and load attesation
    attestation = cbor2.loads(base64.b64decode(attestation_raw))

    auth_data = attestation["authData"]
    att_statement = attestation["attStmt"]

    # Step 2: Parse certificate chain
    x5c = att_statement["x5c"]
    cert_chain = [x509.load_der_x509_certificate(x) for x in x5c]
    cred_cert: x509.Certificate = cert_chain[0]

    # Step 3: Verify Apple root signs chain
    verify_certificate_chain(cert_chain)

    # Step 4: Verify nonce
    verify_nonce(cred_cert, auth_data, challenge_bytes)

    # Step 5: Verify key identifier
    verify_key_identifier(key_id, cred_cert)

    # Step 6: Verify RP ID
    verify_rp_id(auth_data)

    # Step 7: Verify sign count
    verify_sign_count(auth_data)

    # Step 8: Verify aaguid
    verify_aaguid(auth_data, is_prod)

    # Step 9: Verify credential id
    verify_credential_id(key_id, auth_data)


def verify_certificate_chain(certificate_chain: list[x509.Certificate]):
    cred_cert = certificate_chain[0]

    # Step 3: Verify Apple root signs chain
    issuer_cert = certificate_chain[1]
    issuer_cert.public_key().verify(
        cred_cert.signature, cred_cert.tbs_certificate_bytes, ec.ECDSA(cred_cert.signature_hash_algorithm)
    )

    apple_root_certificate = get_apple_root_certificate()
    apple_root_certificate.public_key().verify(
        issuer_cert.signature, issuer_cert.tbs_certificate_bytes, ec.ECDSA(issuer_cert.signature_hash_algorithm)
    )


def verify_nonce(cred_cert, auth_data, challenge_bytes):
    extension = cred_cert.extensions.get_extension_for_oid(OID_APPLE)

    client_data_hash = hashlib.sha256(challenge_bytes).digest()
    composite = bytearray(auth_data)
    composite.extend(client_data_hash)
    expected_nonce = hashlib.sha256(composite).digest()

    der = extension.value.value
    asn1_obj, _ = pyasn1_decode(der, asn1Spec=Sequence())
    actual_nonce = bytes(asn1_obj[0])

    if not bytes_eq(expected_nonce, actual_nonce):
        raise Exception("Nonce does not equal expected nonce")


def verify_key_identifier(key_id: str, cred_cert: x509.Certificate):
    cert_key_bytes = cred_cert.public_key().public_bytes(
        encoding=serialization.Encoding.X962, format=serialization.PublicFormat.UncompressedPoint
    )
    cert_key_hash = hashlib.sha256(cert_key_bytes).digest()
    expected_hash = base64url_to_bytes(key_id)
    if not bytes_eq(expected_hash, cert_key_hash):
        raise Exception("Key identifier does not equal expected identifier")


def verify_rp_id(auth_data):
    rp_id_hash = auth_data[:32]

    apple_team_id = settings.APPLE_TEAM_ID
    app_bundle_identifier = settings.APP_BUNDLE_IDENTIFIER
    app_id = f"{apple_team_id}.{app_bundle_identifier}".encode("utf-8")
    expected_rp_id_hash = hashlib.sha256(app_id).digest()

    if not bytes_eq(expected_rp_id_hash, rp_id_hash):
        raise Exception("RP ID does not equal expected RP ID")


def verify_sign_count(auth_data):
    counter = auth_data[33:37]
    sign_count = int.from_bytes(counter, "big")
    if sign_count != 0:
        raise Exception("Sign count does not equal 0")


def get_credential_data(auth_data):
    credential_data = auth_data[37:]

    aaguid = credential_data[:16]
    credential_id_len = int.from_bytes(credential_data[16:18], "big")
    credential_id = credential_data[18 : 18 + credential_id_len]

    return {"aaguid": aaguid, "credential_id": credential_id}


def verify_aaguid(auth_data, is_prod):
    aaguid = get_credential_data(auth_data)["aaguid"]

    expected_aaguid_prod = b"appattest\x00\x00\x00\x00\x00\x00\x00"
    expected_aaguid_development = b"appattestdevelop"

    expected_aaguid = expected_aaguid_prod if is_prod else expected_aaguid_development

    if not bytes_eq(aaguid, expected_aaguid):
        raise Exception("Invalid aaguid")


def verify_credential_id(key_id, auth_data):
    credential_id = get_credential_data(auth_data)["credential_id"]
    expected_credential_id = base64url_to_bytes(key_id)
    if not bytes_eq(credential_id, expected_credential_id):
        raise Exception("Credential id does not match key identifier")


def base64url_to_bytes(url):
    return base64.urlsafe_b64decode(f"{url}===")
