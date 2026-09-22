# Attesta issuer architecture

**Status:** Proposed (2026-09-17) — implement only after chat approval.  
**Mission:** `docs/MISSION.md`  
**ADR:** `docs/decisions/009-issuer-vision.md`  
**MVP code reference (until migrated):** `attesta-architecture.md`

Research date: 2026-09-17. Specs cited below move; re-check before locking an implementation ADR.

---

## 1. End state

Attesta is a **Transparency Service for real-property observations**.

```
sources (portals, official APIs, later registries)
        │
        ▼
   ingest → PII strip → hash → append-only snapshot
        │
        ▼
   resolve → dwelling identity (price path, presence, delist)
        │
        ▼
   verify(claim | url) → evidence-only adjudicate → sign receipt
        │
        ├── consumer verifies JWS against JWKS (offline, free)
        └── paid resolve of sha256:* → snapshot metadata
```

Verification **writes** snapshots (deep / URL fetch). Demand thickens memory. Memory makes the next receipt harder to fake and cheaper to issue. That flywheel *is* the architecture.

Coverage tags on the receipt (`residential_pt`, later `cadastral_pt`, `residential_es`, …) are the only geographic product. The issuer is one.

---

## 2. What we keep from the MVP

Do not rebuild. These already match the vision:

| Layer | Keep | Why |
|---|---|---|
| Append-only `snapshots` | Invariant 1 | The memory |
| PII strip before write | Invariant 2 | GDPR at the door |
| `MeteringService.authorize` | Invariant 3 | Every priced check |
| Evidence-only adjudicator + post-validate | Invariant 4 | Receipt is not a vibe |
| ES256 JWS + JWKS | ADR-005 | Agents already verify this |
| `BaseCollector` | ADR-008 | New sources are subclasses |
| FastAPI + MCP on one process | ADR-002 | One serving surface |
| LiteLLM behind flags | ADR-006 | Judge is swappable |
| Postgres + pgvector | ADR-004 | Identity + concurrent reads |

Current production gap: memory is five fixtures; deep mode re-ingests those fixtures; official sources are unused. The stack is an issuer with an empty log.

---

## 3. Research (2026-09-17) — what we adopt vs ignore

### 3.1 Receipt envelope — stay on JWS; watch SCITT

- **JWS compact / ES256 / JWKS** (RFC 7515) is what we ship. Agents, MCP, and Apify already carry it. Offline verify needs no new library.
- **SCITT** (IETF; architecture draft-22, SCRAPI draft-11; RFC 9943 noted in adjacent work June 2026) is a Transparency Service for signed statements + inclusion receipts (COSE_Sign1). That is the *category* we are in. We do **not** migrate the agent-facing envelope to COSE — the draft is still moving and agents already verify JWS. We **do** keep snapshot identity as content-hash so a log can include `sha256:*` without rewriting history, if we ever need one.
- **C2PA 2.4** (COSE + JUMBF) is for media files (listing photos, floorplans), not API attestations. Hold until we decide we store photo binaries as first-class evidence.
- **in-toto / DSSE / EAT** are supply-chain / caller attestation. Out of scope. We attest observations, not the calling agent.

**Rule:** Agent-facing receipt is JWS with `source_classes`, `coverage`, and `llm_*` flags from the start. Internal snapshot identity stays content-hash. A transparency log, if we ever add one, wraps hashes; it does not replace JWS.

### 3.2 Payments — x402 v2 exists; isolate it

x402 v2 ([spec](https://github.com/x402-foundation/x402/blob/main/specs/x402-specification-v2.md), [HTTP transport](https://github.com/x402-foundation/x402/blob/main/specs/transports-v2/http.md)):

- 402 + `PAYMENT-REQUIRED` (base64 `PaymentRequired`)
- Client retries with `PAYMENT-SIGNATURE`
- Server returns `PAYMENT-RESPONSE`
- Facilitator: `POST /verify`, `POST /settle`, `GET /supported`
- Networks via CAIP-2 (`eip155:8453` Base mainnet; we still have `eip155:84532` sepolia in config)
- Schemes: `exact`, plus `upto` / `batch-settlement` in the foundation spec
- Transports called out: HTTP, MCP, A2A

Our `app/payments/x402.py` interface stays the choke-point (ADR-003). Implementation must track **v2 header names** (`PAYMENT-*`, not a one-off `X-PAYMENT` forever). Stripe remains the human rail. Neither rail is the product.

### 3.3 Serving — MCP 2026-07-28

[Streamable HTTP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http):

- Single POST endpoint; **GET stream removed**; **protocol sessions removed**
- Required `MCP-Protocol-Version` header matching `_meta`
- Long-lived notify via `subscriptions/listen`, not GET
- Official registry: `https://registry.modelcontextprotocol.io/v0.1/servers` (preview)

FastMCP on our process is still the right host. Pin and test protocol version; do not invent a second MCP server. Registry publish is distribution, not architecture.

### 3.4 Official Portugal sources — DGT Cadastro Predial

[DGT OGC API](https://ogcapi.dgterritorio.gov.pt/) publishes **Cadastro Predial (Continente)** as OGC API Features (~1.79M items, GeoJSON, `bbox` / `limit` up to 2000). High-value dataset under the Open Data Directive; **CC BY 4.0**; NIC as cadastral id ([dados.gov.pt](https://dados.gov.pt/datasets/cadastro-predial/), regime DL 72/2023).

This is the first **official** `source_class`: `cadastral`. It does not replace portals. It lets identity bind an ad to a parcel when geometry and admin units agree. Do not treat the OGC parcel as title. Energy cert / CIMI / Conservatória stay out until we are sure we can cite them as observations without implying legal status.

### 3.5 Entity resolution

Keep the versioned deterministic matcher (geohash + typology + area + embedding). Do not LLM-merge dwellings: a bad merge corrupts the moat (architecture §5). pgvector stays. Official geometry (DGT) becomes a blocking key when present.

### 3.6 Store and compute

- Snapshots: R2 (or compatible S3) remains correct — cheap, no egress tax, EU bucket when we set it. Production is still `local`; that is a deploy gap, not a design change.
- Postgres/Neon: pool pre-ping + recycle (already in `app/db/session.py`) is mandatory for serverless Postgres.
- Ingest compute: existing Apify actor plugins (`dz_omar/idealista-scraper-api`, `automation-lab/imovirtual-scraper`) stay optional collectors. Official APIs are first-party HTTP. Licensed feeds are just another `BaseCollector`.

### 3.7 EU AI Act Article 50 (in force 2026-08-02)

Art. 50 is about **synthetic content marking** and human disclosure of deepfakes / some public-interest text — not about property receipts.

We are not a generative-media provider. We **are** in the evidence path of agents that generate recommendations. Design rules:

- Receipt `method` always names the pipeline (`attesta/verify@0.1`).
- If an LLM touched parse or adjudicate, the payload says so (`llm_parse`, `llm_adjudicate`).
- Terms stay: corroboration across sources, not ground truth (architecture §6).
- Do not market Attesta as “AI Act compliance.” Offer a file a deployer *can* keep.

---

## 4. Target architecture (layers)

```
┌─ source adapters ─────────────────────────────────────────┐
│  PortalCollector (Idealista, Imovirtual, …)               │
│  OfficialCollector (DGT OGC cadastro)                     │
│  UrlCollector (one listing URL → one observation)         │
│  FeedCollector (licensed / CSV)                           │
└───────────────┬───────────────────────────────────────────┘
                ▼
┌─ observation kernel ──────────────────────────────────────┐
│  PII strip → canonicalize → sha256 → snapshot store       │
│  snapshots (append-only) + observations                   │
└───────────────┬───────────────────────────────────────────┘
                ▼
┌─ identity ────────────────────────────────────────────────┐
│  matcher vN (blocking keys + embeddings + optional NIC)   │
│  properties, property_observations, price_events          │
└───────────────┬───────────────────────────────────────────┘
                ▼
┌─ issuer ──────────────────────────────────────────────────┐
│  parse claim | accept URL                                 │
│  retrieve only stored (+ optional live fetch → kernel)    │
│  adjudicate (deterministic and/or LiteLLM)                │
│  post-validate citations                                  │
│  sign JWS · persist attestation                           │
└───────────────┬───────────────────────────────────────────┘
                ▼
┌─ edges ───────────────────────────────────────────────────┐
│  REST /v1  ·  MCP POST /mcp  ·  Apify wrapper             │
│  JWKS  ·  attestation-spec  ·  metering (key / x402 / $)  │
└───────────────────────────────────────────────────────────┘
```

New first-class input: **URL**. A listing URL is an address into a source adapter. That is how verification feeds the corpus without a full-country crawl.

---

## 5. Build now vs hold

No product phases. Building is cheap; the only reason to leave something out is **we are not sure it belongs**. Crawl width, paid-rail *enable*, and Apify spend are **config knobs**, not architecture slices.

### Build now — slice A (in implementation 2026-09-21)

Approved as one issuer slice, **excluding** scheduled live crawl and the DGT collector:

| Piece | What it is |
|---|---|
| Honest copy | Mission, this design, coverage language that matches actual memory |
| URL-addressed observation | `POST /v1/verify` + MCP accept a listing `url`. Detect source → `fetch_listing_by_url` → ingest → resolve → groundable predicates → JWS. Deep mode on a claim re-fetches the matched property's last-known source URL (fail soft). Fixture `_live_refresh` is gone. |
| Receipt payload | `source_classes`, `coverage`, `llm_parse` / `llm_adjudicate`, `method=attesta/verify@0.2`. Spec in `public/attestation-spec.md`. |
| Source-class guardrail | ADR-010. Cadastral-alone evidence cannot corroborate a non-geometry predicate. Enforced before any cadastral collector exists. |
| MCP pin | Streamable HTTP 2026-07-28 (`MCP-Protocol-Version`, POST-only). |
| Payment rails | x402 v2 headers (`PAYMENT-REQUIRED` / `PAYMENT-SIGNATURE` / `PAYMENT-RESPONSE`) behind `app/payments/x402.py`. `X-Payment` still accepted as a read alias. Stripe rail unchanged. |
| Dynamic pricing | DB `tool_prices` + `GET/PATCH /internal/pricing` (ADR-011). Not a dashboard. `verify_url` is its own SKU. |

### Separate decisions (not in this slice)

| Piece | Why it waits |
|---|---|
| Scheduled portal memory | ToS / third-party actor risk. Path exists as `--source`; enabling the worker is a config + legal call. |
| Official overlay (DGT) | Ship storage-only and disabled-by-default when we take this on. Do **not** put `properties.cadastral_nic` as an inherit-on-merge flag — parcel binding needs its own confidence (ADR-010). |
| NIC / geometry as matcher blocking key | After live portal volume exists. A bad merge corrupts the moat. |

Invariants stay intact. New collectors are `BaseCollector` subclasses.

### Hold — uncertainty, not sequencing

| Hold | Why we are not sure |
|---|---|
| SCITT / COSE envelope or a transparency log | Draft still moving; agents already verify JWS. Hashes stay log-ready. |
| C2PA on listing media | Right standard for photos, wrong artifact for the API receipt. Hold until photo binaries are first-class evidence. |
| Energy cert / CIMI / Conservatória collectors | We are not sure we can cite them as observations without implying legal status. Cadastre is the official source we *are* sure about. |
| Next country (`residential_es`, …) | Architecture already accepts another portal collector. We are not sure which geography is next. |
| LLM-merge of dwellings | Not a later feature. Never: a bad merge corrupts the moat. |
| Consumer web app / admin UI | Non-goal. |
| in-toto / DSSE / EAT | Wrong problem: we attest observations, not the calling agent. |

---

## 6. Data-model deltas

Additive only. No UPDATE/DELETE on `snapshots`.

- `observations.source_class` TEXT (`portal` | `cadastral` | `registry` | `feed`) — default `portal`.
- Snapshot `url` remains the external address.
- `tool_prices` — runtime overrides of per-tool EUR prices.
- Receipt fields above live in attestation JSON (`verdicts` stays flexible).
- Deferred (not this slice): parcel binding with its own confidence. Do not add `properties.cadastral_nic` as a silent inherit-on-merge column.

---

## 7. Edges

| Edge | Role in the vision |
|---|---|
| REST | Canonical issuer API |
| MCP | How agents call the issuer (pin 2026-07-28) |
| Apify Store | How some agents pay today (PPE). Wrapper only |
| JWKS + spec | How *others* check us without an account |
| Stripe / x402 | Rails. Not the product |

No consumer web app in this design.

---

## 8. Risks

- **Portal ToS / scraping.** Collectors are plugins; licensed feed or official API can replace Apify without changing the kernel.
- **Bad merges.** Matcher versioned; never silent LLM merge.
- **Empty-log charging.** Build both rails. Leave them disabled until a check can cite live evidence. That is a switch, not a hold.
- **Spec churn.** x402 v2 and MCP 2026-07-28 will move; keep adapters thin.
- **Legal overclaim.** Cadastre ≠ Conservatória. Receipt language stays observational.

---

## 9. Approval

Approve this document and `docs/MISSION.md` in chat to make them binding. After approval, implement the **Build now** table as one issuer — not a sliced ladder.

---

## 10. Glossary (plain language)

Attesta terms first, then Portugal property sources, then protocols. Nothing here is legal advice.

### What we do

| Term | Meaning |
|---|---|
| **Issuer** | We are the party that *creates* a signed statement. A bank issues a card statement; we issue a property receipt. We are not a listings website. |
| **Observation** | “On this date, this source showed this about a home.” Not “this is legally true.” |
| **Snapshot** | The frozen copy we stored of that observation, plus a fingerprint (`sha256` hash). **Append-only** means we never edit or delete it; a later change is a new row. |
| **Memory / the log** | The pile of snapshots over time. That history is what a one-off scrape cannot fake. |
| **Identity / dwelling** | One real home, even if Idealista and Imovirtual show it as two ads, or it is relisted next year. |
| **Resolve / matcher** | The code that decides “these ads are the same home.” We do that with rules (location, size, type), not by asking an LLM to guess. |
| **Receipt / attestation** | The signed answer we give after a check: what we concluded, which snapshots we used, our signature. |
| **Adjudicate** | Compare the claim (or URL) only to retrieved snapshots and decide supported / contradicted / unverifiable. |
| **Coverage tag** | A label for *what memory we actually have*, e.g. `residential_pt` = Portuguese homes we have watched. Not a product SKU. |
| **Lineage** | Who said it, when we saw it, and the hash of the stored copy. |
| **PII** | Personal data (phone, email, name). We strip it before we write anything. |

### Portugal property sources

These are different government/private systems. Mixing them is how you accidentally claim “we proved ownership.”

| Term | What it actually is |
|---|---|
| **Portal** (Idealista, Imovirtual) | A classifieds site. An *ad*. Price and “for sale” can be wrong or stale. |
| **DGT** | Direção-Geral do Território — the national mapping/cadastre authority. |
| **Cadastro / cadastral map** | The official **map of parcels**: where a plot is, its shape, a parcel id. “This polygon exists.” Not “Dor owns it.” |
| **Parcel** | A piece of land (or building unit) on that map. |
| **NIC** | Número de Identificação Cadastral — the parcel’s official id in that map. |
| **OGC API** | A standard web API for maps/features. How we download DGT parcels as data (GeoJSON), not a new product. |
| **Title / legal title** | Who **owns** the property in law. In Portugal that lives at the land registry, not on the cadastral map. |
| **Conservatória** (Conservatória do Registo Predial) | The **land registry** office. Deeds, owners, mortgages. We do **not** read this today. Saying we checked cadastre is not saying we checked the Conservatória. |
| **Encumbrance** | A legal burden on the home (mortgage, lien, seizure). Only the registry knows this reliably. |
| **Energy cert / SCE** | Certificate of how efficient the building is (A–F class). A different government system. Useful later; easy to over-claim if we bolt it on without care. |
| **CIMI** | Municipal property tax (IMI) context. Tax value ≠ asking price ≠ legal owner. Easy to over-claim. |
| **Notary** | The official who executes the sale deed. We are not in that loop. |

**One sentence:** cadastre = *where the plot is*; Conservatória = *who owns it and what debts sit on it*; portal = *what someone is asking for it today*.

### Protocols we mentioned (and why most are on hold)

| Term | Meaning | Our stance |
|---|---|---|
| **JWS** | A JSON document plus a cryptographic signature. Anyone can check it with our public key. This *is* our receipt format. | Build now |
| **JWKS** | The public-key file we publish so others can check JWS without calling us. | Build now |
| **ES256** | The specific signature algorithm we use (standard, widely supported). | Build now |
| **SCITT** | An IETF project for a public “transparency log” of signed statements (like a notary bulletin board). Still a moving draft. | Hold |
| **COSE** | A binary cousin of JWS. SCITT uses it. Agents already speak JWS. | Hold (do not switch) |
| **Transparency log** | An append-only public list that proves “this receipt was published and not silently rewritten.” | Hold until someone needs to prove inclusion *without asking us* |
| **C2PA** | A standard that signs **photos/videos** (“this image was captured/edited by…”). For listing photos, not for our JSON receipt. | Hold |
| **MCP** | Model Context Protocol — how AI agents call tools. We already expose Attesta this way. | Build now (pin current spec) |
| **x402** | HTTP payment protocol: the server answers “pay first” (status 402), the agent pays in crypto, retries. | Build the code; leave *enabled* off until checks cite live evidence |
| **Stripe rail** | Normal card/invoice billing for humans. Same idea: build it, enable when we want to charge. | Build now |
| **in-toto / DSSE / EAT** | Standards that prove *which software or which agent* produced something. Wrong problem: we sign *what the listing said*, not who called us. | Never (wrong product) |

### Other words in this doc

| Term | Meaning |
|---|---|
| **Hash / sha256** | Fingerprint of a file. Change one byte, the fingerprint changes. We store `sha256:…` so evidence can be checked later. |
| **Fixture** | A fake/sample listing file we shipped for tests. Production must not pretend fixtures are the live market. |
| **Collector** | A plugin that fetches one kind of source (Idealista, Imovirtual, DGT). |
| **Apify** | A scraping marketplace. We use other people’s Idealista/Imovirtual actors; our Store listing is a wrapper around our API. |
| **R2** | Cloudflare object storage (like S3). Where snapshot files should live in production. |
| **Alembic** | Database migration tool. How we add columns safely. |
| **pgvector** | Postgres extension for similarity search. Helps the matcher find “same home,” not a chatbot. |
