from backend.capability_governance_test.redaction import REDACTED, redact


def test_redactor_removes_urls_tokens_passwords_and_business_payloads_recursively():
    result = redact({
        "db_url": "mysql://u:p@host/db",
        "token": "secret",
        "summary": "safe",
        "nested": [{"password": "p@ss", "url": "https://example.test/a"}],
        "business_payload": {"order": "customer-private"},
    })

    assert result == {
        "db_url": REDACTED,
        "token": REDACTED,
        "summary": "safe",
        "nested": [{"password": REDACTED, "url": REDACTED}],
        "business_payload": REDACTED,
    }


def test_redactor_removes_secret_bearing_strings_without_sensitive_keys():
    result = redact({"note": "call https://user:pass@example.test/private", "safe": "summary"})

    assert result == {"note": REDACTED, "safe": "summary"}
