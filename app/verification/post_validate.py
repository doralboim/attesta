"""Enforce invariant 4: verdicts without evidence are downgraded."""

from __future__ import annotations

STRONG_VERDICTS = frozenset({"CORROBORATED", "CONTRADICTED"})
VALID_EVIDENCE_PREFIXES = ("sha256:", "snap:", "sha256:snap-")


def _has_valid_evidence(evidence: list[str]) -> bool:
    return any(e.startswith(VALID_EVIDENCE_PREFIXES) for e in evidence)


def post_validate_verdicts(verdicts: list[dict]) -> list[dict]:
    """Downgrade CORROBORATED/CONTRADICTED lacking evidence hashes to UNVERIFIABLE."""
    validated: list[dict] = []
    for verdict in verdicts:
        v = dict(verdict)
        label = v.get("verdict", "UNVERIFIABLE")
        evidence = v.get("evidence") or []

        if label in STRONG_VERDICTS and not _has_valid_evidence(evidence):
            v["verdict"] = "UNVERIFIABLE"
            note = "Post-validation downgrade: no evidence hash cited."
            v["notes"] = f"{v.get('notes', '')} {note}".strip()

        validated.append(v)
    return validated
