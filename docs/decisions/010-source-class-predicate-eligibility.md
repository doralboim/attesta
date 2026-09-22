# ADR-010: Source-class predicate eligibility

**Status:** Accepted (2026-09-21)

**Context:** The issuer must never treat cadastral (or later registry) observations as legal title. Prose in the design doc is not enough — Invariant 4 already post-validates verdict citations, but only checked that a hash existed.

**Decision:** Every verdict carries `source_classes` computed from stored observations, never from the adjudicator. `post_validate_verdicts` downgrades a strong verdict to `UNVERIFIABLE` when the only cited class is `cadastral` and the predicate is not geometry-shaped (`location` / `parcel` / `geometry`).

When a cadastral collector is added later:

- Do not put `cadastral_nic` on `properties` as a silent inherit-on-merge flag.
- Bind NIC on the observation / a dedicated parcel-link row with its own confidence, separate from `PropertyObservation.match_confidence`.

**Consequences:** Fixture-only production still always emits `source_classes: ["portal"]`. The guardrail is proven before official sources exist. Title-shaped predicates cannot be corroborated by cadastre alone even if an LLM tries.
