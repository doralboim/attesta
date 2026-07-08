from app.ingestion.pii_strip import contains_pii, strip_pii_from_record, strip_pii_from_text


def test_strip_pii_from_text() -> None:
    text = "Contact agent at joao@agency.pt or +351 912 345 678"
    cleaned = strip_pii_from_text(text)
    assert "joao@agency.pt" not in cleaned
    assert "+351" not in cleaned
    assert "[REDACTED_EMAIL]" in cleaned


def test_strip_pii_from_record_removes_agent_fields() -> None:
    record = {
        "title": "Nice flat",
        "agent_name": "João Silva",
        "phone": "+351 912 345 678",
        "email": "joao@agency.pt",
        "attrs": {"city": "Faro"},
    }
    cleaned = strip_pii_from_record(record)
    assert "agent_name" not in cleaned
    assert "phone" not in cleaned
    assert "email" not in cleaned
    assert cleaned["attrs"]["city"] == "Faro"


def test_contains_pii_detects_leaks() -> None:
    assert contains_pii("call me at test@example.com")
    assert not contains_pii("Faro T2 apartment 78m2")
