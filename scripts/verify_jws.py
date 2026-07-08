#!/usr/bin/env python3
"""Verify an Attesta JWS token against local keys or remote JWKS."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

from app.verification.attest import AttestationSigner


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Attesta JWS attestation")
    parser.add_argument("jws", nargs="?", help="Compact JWS string")
    parser.add_argument("--file", help="Read JWS from file")
    parser.add_argument("--jwks-url", default="http://localhost:8000/.well-known/jwks.json")
    parser.add_argument("--local", action="store_true", help="Use local signer keys only")
    args = parser.parse_args()

    token = args.jws
    if args.file:
        token = Path(args.file).read_text().strip()
    if not token:
        token = sys.stdin.read().strip()
    if not token:
        print("No JWS provided", file=sys.stderr)
        return 1

    try:
        if not args.local:
            jwks = httpx.get(args.jwks_url, timeout=10).json()
            print(f"JWKS keys: {[k['kid'] for k in jwks.get('keys', [])]}")
        payload = AttestationSigner().verify(token)
        print(json.dumps({"valid": True, "payload": payload}, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
