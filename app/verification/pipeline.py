"""Verification pipeline — parse → retrieve → post-validate → sign → persist."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.verification.attest import AttestationSigner
from app.verification.confidence import score_confidence
from app.verification.persist import persist_attestation
from app.verification.post_validate import post_validate_verdicts
from app.verification.retrieve import EvidenceRetriever


class VerificationPipeline:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.retriever = EvidenceRetriever(session)
        self.signer = AttestationSigner()

    async def verify(
        self,
        claim: str,
        depth: str = "corpus",
        *,
        persist: bool = True,
        usage_event_id: int | None = None,
    ) -> dict:
        verdicts, _ = await self.retriever.gather_verdicts(claim, depth=depth)
        verdicts = post_validate_verdicts(verdicts)
        confidence = score_confidence(verdicts)

        payload = {
            "sub_claim": claim,
            "verdicts": verdicts,
            "confidence": confidence,
            "method": "attesta/verify@0.1",
            "coverage": "residential_pt",
        }
        token = self.signer.sign(payload)
        self.signer.verify(token)  # fail fast if signing broken

        result = {
            "attestation": payload,
            "jws": token,
            "verification_mode": depth,
            "attestation_id": None,
        }

        if persist:
            record = await persist_attestation(
                self.session,
                claim=claim,
                payload=payload,
                jws=token,
                usage_event_id=usage_event_id,
            )
            result["attestation_id"] = str(record.id)

        return result
