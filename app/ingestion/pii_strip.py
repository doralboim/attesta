import hashlib
import re

# Patterns for PII that must never enter the corpus (GDPR at the door).
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# Agent name fields commonly found in portal payloads
AGENT_NAME_KEYS = frozenset(
    {
        "agent_name",
        "agentName",
        "contact_name",
        "contactName",
        "owner_name",
        "phone",
        "telephone",
        "email",
    }
)


def strip_pii_from_text(text: str) -> str:
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    return text


def strip_pii_from_record(record: dict) -> dict:
    """Remove PII fields and redact patterns in string values before any DB/R2 write."""
    cleaned: dict = {}
    for key, value in record.items():
        if key in AGENT_NAME_KEYS:
            continue
        if isinstance(value, str):
            cleaned[key] = strip_pii_from_text(value)
        elif isinstance(value, dict):
            cleaned[key] = strip_pii_from_record(value)
        elif isinstance(value, list):
            cleaned[key] = [
                strip_pii_from_record(v) if isinstance(v, dict) else strip_pii_from_text(v) if isinstance(v, str) else v
                for v in value
            ]
        else:
            cleaned[key] = value
    return cleaned


def contains_pii(text: str) -> bool:
    return bool(PHONE_RE.search(text) or EMAIL_RE.search(text))


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()
