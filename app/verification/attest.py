"""JWS attestation signing, verification, and JWKS with key rotation."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jose import jws
from jose.exceptions import JWSError
from jose.utils import base64url_encode

from app.config import get_settings


def _pem_to_jwk(public_pem: bytes, kid: str) -> dict[str, str]:
    public_key = serialization.load_pem_public_key(public_pem)
    numbers = public_key.public_numbers()  # type: ignore[union-attr]
    x = base64url_encode(numbers.x.to_bytes(32, "big")).decode()
    y = base64url_encode(numbers.y.to_bytes(32, "big")).decode()
    return {
        "kty": "EC",
        "crv": "P-256",
        "kid": kid,
        "use": "sig",
        "alg": "ES256",
        "x": x,
        "y": y,
    }


def _load_private_pem() -> bytes:
    settings = get_settings()
    if settings.jws_private_key_pem:
        return settings.jws_private_key_pem.encode()
    key_path = Path("keys/attestation.pem")
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        return key_path.read_bytes()
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path.write_bytes(private_pem)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    (key_path.parent / "attestation.pub.pem").write_bytes(public_pem)
    return private_pem


class AttestationSigner:
    def __init__(self) -> None:
        settings = get_settings()
        self._private_pem = _load_private_pem()
        self.kid = settings.jws_kid
        self.issuer = settings.issuer_url
        self._retired_jwks = self._load_retired_jwks(settings.jws_retired_public_keys_json)

    @staticmethod
    def _load_retired_jwks(raw: str) -> list[dict[str, Any]]:
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, dict) and "keys" in data:
            return list(data["keys"])
        if isinstance(data, list):
            return data
        return []

    def sign(self, payload: dict) -> str:
        body = {
            "iss": self.issuer,
            "iat": int(datetime.now(UTC).timestamp()),
            "jti": f"att_{uuid.uuid4().hex[:8]}",
            **payload,
        }
        return jws.sign(body, self._private_pem, algorithm="ES256", headers={"kid": self.kid})

    def public_jwks(self) -> dict:
        private_key = serialization.load_pem_private_key(self._private_pem, password=None)
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        keys = [_pem_to_jwk(public_pem, self.kid)]
        for retired in self._retired_jwks:
            if retired.get("kid") != self.kid:
                keys.append(retired)
        return {"keys": keys}

    def verify(self, token: str) -> dict:
        """Verify JWS and return payload. Raises JWSError on failure."""
        header = jws.get_unverified_header(token)
        kid = header.get("kid", self.kid)

        public_pem = self._public_pem_for_kid(kid)
        payload_bytes = jws.verify(token, public_pem, algorithms=["ES256"])
        if isinstance(payload_bytes, bytes):
            return json.loads(payload_bytes.decode())
        return json.loads(payload_bytes)

    def _public_pem_for_kid(self, kid: str) -> bytes:
        if kid == self.kid:
            private_key = serialization.load_pem_private_key(self._private_pem, password=None)
            return private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        for retired in self._retired_jwks:
            if retired.get("kid") == kid and "pem" in retired:
                return retired["pem"].encode()
        msg = f"Unknown kid: {kid}"
        raise JWSError(msg)
