"""Enforce invariant 4: verdicts without evidence are downgraded.

Also enforce source_class eligibility (ADR-010): cadastral evidence alone
cannot corroborate a non-geometry predicate. Cadastre is a map of parcels,
not legal title.
"""

from __future__ import annotations

STRONG_VERDICTS = frozenset({"CORROBORATED", "CONTRADICTED"})
VALID_EVIDENCE_PREFIXES = ("sha256:", "snap:", "sha256:snap-")
GEOMETRY_PREDICATE_PREFIXES = ("location", "parcel", "geometry")


def _has_valid_evidence(evidence: list[str]) -> bool:
    return any(e.startswith(VALID_EVIDENCE_PREFIXES) for e in evidence)


def _is_geometry_predicate(predicate: str) -> bool:
    name = predicate.split("=", 1)[0].strip().lower()
    return name.startswith(GEOMETRY_PREDICATE_PREFIXES)


def _cadastral_alone_ineligible(verdict: dict) -> bool:
    classes = {str(c) for c in (verdict.get("source_classes") or [])}
    if classes != {"cadastral"}:
        return False
    return not _is_geometry_predicate(str(verdict.get("predicate", "")))


def post_validate_verdicts(verdicts: list[dict]) -> list[dict]:
    """Downgrade strong verdicts that lack hashes or misuse cadastral evidence."""
    validated: list[dict] = []
    for verdict in verdicts:
        v = dict(verdict)
        label = v.get("verdict", "UNVERIFIABLE")
        evidence = v.get("evidence") or []

        if label in STRONG_VERDICTS and not _has_valid_evidence(evidence):
            v["verdict"] = "UNVERIFIABLE"
            note = "Post-validation downgrade: no evidence hash cited."
            v["notes"] = f"{v.get('notes', '')} {note}".strip()
        elif label in STRONG_VERDICTS and _cadastral_alone_ineligible(v):
            v["verdict"] = "UNVERIFIABLE"
            note = "Post-validation downgrade: cadastral evidence alone cannot corroborate a non-geometry predicate."
            v["notes"] = f"{v.get('notes', '')} {note}".strip()

        validated.append(v)
    return validated
