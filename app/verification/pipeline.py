"""Verification pipeline — parse → retrieve → post-validate → sign → persist."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.factory import llm_is_configured
from app.verification.attest import AttestationSigner
from app.verification.confidence import score_confidence
from app.verification.persist import persist_attestation
from app.verification.post_validate import post_validate_verdicts
from app.verification.retrieve import EvidenceRetriever

METHOD = "attesta/verify@0.2"


def _source_classes_union(verdicts: list[dict]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for verdict in verdicts:
        for cls in verdict.get("source_classes") or []:
            if cls not in seen:
                seen.add(cls)
                out.append(cls)
    return out


class VerificationPipeline:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.retriever = EvidenceRetriever(session)
        self.signer = AttestationSigner()

    def _payload(self, *, subject: str, verdicts: list[dict]) -> dict:
        used_llm = llm_is_configured()
        return {
            "sub_claim": subject,
            "verdicts": verdicts,
            "confidence": score_confidence(verdicts),
            "method": METHOD,
            "coverage": "residential_pt",
            "source_classes": _source_classes_union(verdicts),
            "llm_parse": used_llm,
            "llm_adjudicate": used_llm,
        }

    async def _finish(
        self,
        *,
        subject: str,
        verdicts: list[dict],
        verification_mode: str,
        persist: bool,
        usage_event_id: int | None,
    ) -> dict:
        verdicts = post_validate_verdicts(verdicts)
        payload = self._payload(subject=subject, verdicts=verdicts)
        token = self.signer.sign(payload)
        self.signer.verify(token)

        result = {
            "attestation": payload,
            "jws": token,
            "verification_mode": verification_mode,
            "attestation_id": None,
        }
        if persist:
            record = await persist_attestation(
                self.session,
                claim=subject,
                payload=payload,
                jws=token,
                usage_event_id=usage_event_id,
            )
            result["attestation_id"] = str(record.id)
        return result

    async def verify(
        self,
        claim: str,
        depth: str = "corpus",
        *,
        persist: bool = True,
        usage_event_id: int | None = None,
    ) -> dict:
        verdicts, _ = await self.retriever.gather_verdicts(claim, depth=depth)
        return await self._finish(
            subject=claim,
            verdicts=verdicts,
            verification_mode=depth,
            persist=persist,
            usage_event_id=usage_event_id,
        )

    async def verify_url(
        self,
        url: str,
        *,
        persist: bool = True,
        usage_event_id: int | None = None,
    ) -> dict:
        verdicts, _ = await self.retriever.gather_verdicts_for_url(url)
        return await self._finish(
            subject=url,
            verdicts=verdicts,
            verification_mode="url",
            persist=persist,
            usage_event_id=usage_event_id,
        )
