# Attesta Attestation Spec v0.1

Third-party consumers: verify receipts issued by `POST /v1/verify` or MCP `verify_claim`.

## Format

- **Serialization:** JWS compact (three base64url segments)
- **Algorithm:** `ES256` (ECDSA P-256 SHA-256)
- **Header:** `{"alg":"ES256","kid":"<key-id>"}`

## Payload fields

| Field | Type | Description |
|-------|------|-------------|
| `iss` | string | Issuer URL (`https://api.attesta.dev`) |
| `iat` | int | Unix timestamp at issuance |
| `jti` | string | Unique attestation id (`att_<hex>`) |
| `sub_claim` | string | Original natural-language claim |
| `verdicts` | array | Per-predicate adjudication |
| `confidence` | float | 0..1 aggregate score |
| `method` | string | `attesta/verify@0.1` |
| `coverage` | string | Domain coverage (`residential_pt`) |

## Verdict object

```json
{
  "predicate": "price=240000",
  "verdict": "CORROBORATED",
  "evidence": ["sha256:abc123..."],
  "sources": 2,
  "notes": "optional"
}
```

**Verdict values:** `CORROBORATED` | `CONTRADICTED` | `UNVERIFIABLE`

Post-validation rule: strong verdicts without `sha256:` or `snap:` evidence are downgraded to `UNVERIFIABLE`.

## Verification steps

1. `GET /.well-known/jwks.json`
2. Select JWK where `kid` matches JWS header
3. Verify ES256 signature over `base64url(header).base64url(payload)`
4. Optionally resolve evidence: `GET /v1/evidence/{ref}` (metered)

## Key rotation

Active key signs new attestations (`kid: attesta-v1`). Retired public keys remain in JWKS via `JWS_RETIRED_PUBLIC_KEYS_JSON` until audit windows expire.

## Liability framing

Attestations prove **corroboration across Attesta sources at issuance time**, not absolute ground truth.

## CLI

```bash
python scripts/verify_jws.py "<jws>" --local
python scripts/demo.py --base-url http://localhost:8000
```
