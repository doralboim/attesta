# Attesta — Mission and goals

**Status:** Proposed (2026-09-17). Approve in chat before treating as binding.

## Mission

Attesta is the issuer of **machine-verifiable observations of real property**.

Agents can scrape the present. They cannot remember, merge two ads into one dwelling, or prove they checked. We keep an append-only memory of what sources showed, resolve those observations to dwellings, and sign receipts that anyone can verify without trusting us at read time.

We do not claim the world is true. We claim: **this is what the sources showed, with lineage.**

## Vision

Portugal residential is the first coverage tag (`residential_pt`). The end state is Attesta as the citation layer for claims about physical property in the EU — the way a payment network is the citation layer for a transfer.

Three things, one system:

1. **Memory** — every listing and official record we observed, hashed, PII-stripped, never mutated.
2. **Identity** — one dwelling across portals and years (price path, presence, delist, return).
3. **Receipt** — a claim in, evidence-only adjudication, a portable signature out. Verification writes new snapshots. Demand thickens memory.

Success is not “a nicer Idealista.” Success is when an agent, a platform, or a desk says **“show me the Attesta”** before it acts on a home.

## Goals (in order)

1. **Be an issuer, not a scraper.** The product is the receipt and the log. Portals and official APIs are inputs.
2. **Grow memory that cannot be rebuilt cheaply.** Time in the snapshot log is the moat.
3. **Make the receipt a standard others check.** JWKS, attestation spec, evidence hashes — protocol that outlives any one portal.
4. **Charge for checks and for evidence, not for “access to Portugal.”** Per observation, per verify, per evidence resolve.
5. **Stay EU-native.** GDPR at the door (PII strip before write). Receipts attest corroboration, not title.

## Non-goals

- Ground truth of ownership, encumbrance, or legal title (Conservatória / notary).
- Replacing Idealista, Imovirtual, or licensed feeds as a search UX.
- Custody of funds or user wallets.
- Selling contact PII. We strip it.
- Admin dashboards, white-label, or multi-product UI as the company.

## How this updates earlier copy

Previous one-liner: “provenance-grade EU property data and signed verification receipts for AI agents.”

That is a channel description. The company is the **issuer**. Agents are the first consumers of the receipt. Humans and institutions consume it through them, or by verifying the JWS offline.
