"""Public API contract tests for the bounded content-checksum tool."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi.testclient import TestClient

os.environ.setdefault("AUTH_SESSION_HMAC_SECRET", secrets.token_urlsafe(48))

from main import app


EXPECTED_SHA256_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def _base64url_encode(raw: bytes) -> str:
    """Encode one JWT segment without padding."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _signed_session_token() -> str:
    """Create a real short-lived HMAC session accepted by the private tools API."""
    now = int(time.time())
    header_segment = _base64url_encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    payload_segment = _base64url_encode(
        json.dumps(
            {
                "ver": 1,
                "iss": "naruon-control-plane",
                "aud": "naruon-api",
                "sub": "checksum-contract-user",
                "role": "member",
                "org": "checksum-contract-org",
                "groups": [],
                "workspace": "workspace-checksum-contract-org",
                "iat": now,
                "exp": now + 300,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    signing_input = f"{header_segment}.{payload_segment}"
    signature = hmac.new(
        os.environ["AUTH_SESSION_HMAC_SECRET"].encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_base64url_encode(signature)}"


def _tampered_session_token() -> str:
    """Return a structurally valid session token with a deliberately forged signature."""
    token = _signed_session_token()
    header_segment, payload_segment, signature_segment = token.split(".")
    signature_padding = "=" * (-len(signature_segment) % 4)
    signature = bytearray(
        base64.urlsafe_b64decode(signature_segment + signature_padding)
    )
    signature[0] ^= 0x01
    return f"{header_segment}.{payload_segment}.{_base64url_encode(bytes(signature))}"


def test_content_checksum_api_executes_authenticated_request() -> None:
    """Startup registration and the authenticated execute route must work together."""
    with TestClient(app) as client:
        response = client.post(
            "/api/tools/content_checksum_generator/execute",
            headers={"Authorization": f"Bearer {_signed_session_token()}"},
            json={"parameters": {"text": "abc", "algorithm": "sha256"}},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["result"]["digest_hex"] == EXPECTED_SHA256_ABC
    assert payload["result"]["byte_length"] == 3
    assert payload["message"] == "Execution successful"


def test_content_checksum_api_rejects_unauthenticated_request() -> None:
    """The checksum execute route must retain the generic tools auth boundary."""
    with TestClient(app) as client:
        response = client.post(
            "/api/tools/content_checksum_generator/execute",
            json={"parameters": {"text": "abc", "algorithm": "sha256"}},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_content_checksum_api_rejects_forged_signed_session() -> None:
    """The checksum route must reject a structurally valid token with a forged signature."""
    with TestClient(app) as client:
        response = client.post(
            "/api/tools/content_checksum_generator/execute",
            headers={"Authorization": f"Bearer {_tampered_session_token()}"},
            json={"parameters": {"text": "abc", "algorithm": "sha256"}},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_content_checksum_api_maps_invalid_algorithm_to_execute_failure() -> None:
    """Invalid tool input must expose a stable machine-readable failure code."""
    with TestClient(app) as client:
        response = client.post(
            "/api/tools/content_checksum_generator/execute",
            headers={"Authorization": f"Bearer {_signed_session_token()}"},
            json={"parameters": {"text": "abc", "algorithm": "md5"}},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["result"] is None
    assert payload["error_code"] == "unsupported_checksum_algorithm"
    assert "Unsupported checksum algorithm" in payload["message"]


def test_content_checksum_api_maps_invalid_utf8_to_execute_failure() -> None:
    """Escaped lone surrogates must reach the handler and fail with a stable code."""
    raw_body = b'{"parameters":{"text":"\\ud800","algorithm":"sha256"}}'
    with TestClient(app) as client:
        response = client.post(
            "/api/tools/content_checksum_generator/execute",
            headers={
                "Authorization": f"Bearer {_signed_session_token()}",
                "Content-Type": "application/json",
            },
            content=raw_body,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["result"] is None
    assert payload["error_code"] == "content_checksum_invalid_utf8"
