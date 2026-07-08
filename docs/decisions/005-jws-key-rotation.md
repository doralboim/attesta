# ADR 005: JWS key rotation via retired JWKS

**Status:** Accepted  
**Date:** 2026-07-05

## Context

Attestations are ES256 JWS tokens. Consumers verify signatures against `/.well-known/jwks.json`. Keys must rotate without invalidating in-flight attestations during an audit window.

## Decision

1. **Active key** signs all new attestations (`kid` from `JWS_KID`, default `attesta-v1`).
2. **Retired public keys** are appended to JWKS via `JWS_RETIRED_PUBLIC_KEYS_JSON` (JSON array of JWK objects with optional `pem` for verification).
3. **`AttestationSigner.verify()`** selects the public key by `kid` header — active PEM locally, retired PEM from config.
4. Private keys never ship in JWKS; only `x`/`y` coordinates for retired keys when PEM is omitted (verify uses local PEM store).

## Consequences

- Rotation is config-only: deploy new active key, move old public key to retired list.
- CLI `scripts/verify_jws.py` and `POST /v1/verify/jws/validate` both use the same signer.
- Spec documented in `public/attestation-spec.md`.

## Alternatives considered

- Single long-lived key: rejected — no rotation path for compromise or compliance.
- Per-tenant keys: deferred to enterprise tier.
