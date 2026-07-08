#!/usr/bin/env python3
"""Generate production secrets and env template for Railway deploy."""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Attesta production env vars")
    parser.add_argument("--database-url", required=True, help="postgresql+asyncpg://... from Neon")
    parser.add_argument("--public-base-url", default="https://api.attesta.dev")
    parser.add_argument("--output", default=".env.production")
    args = parser.parse_args()

    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    bootstrap_key = f"attesta_demo_{secrets.token_urlsafe(24)}"
    pem_one_line = private_pem.replace("\n", "\\n")

    lines = [
        "ENVIRONMENT=production",
        f"DATABASE_URL={args.database_url}",
        f"PUBLIC_BASE_URL={args.public_base_url.rstrip('/')}",
        f"ISSUER_URL={args.public_base_url.rstrip('/')}",
        "SNAPSHOT_STORE_BACKEND=local",
        "LOCAL_SNAPSHOT_DIR=.snapshots",
        "LLM_ENABLED=false",
        "X402_ENABLED=false",
        f"BOOTSTRAP_API_KEY={bootstrap_key}",
        f'JWS_PRIVATE_KEY_PEM="{pem_one_line}"',
        "JWS_KID=attesta-v1",
        "",
        "# Share this demo key with early users / directory listings:",
        f"# DEMO_API_KEY={bootstrap_key}",
    ]

    out = Path(args.output)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    print(f"\nDemo API key (save this — shown once):\n  {bootstrap_key}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
