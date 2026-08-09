from app.dataset_safety import leakage_findings, redact_payload


def test_redaction_is_recursive_and_reports_paths() -> None:
    sanitized, findings = redact_payload(
        {
            "message": "Contact alice@example.com",
            "nested": {"api_token": "secret-value"},
            "items": ["Bearer abcdefghijklmnop"],
        }
    )

    assert sanitized["message"] == "Contact [REDACTED:email]"
    assert sanitized["nested"]["api_token"] == "[REDACTED:sensitive-field]"
    assert sanitized["items"][0] == "[REDACTED:bearer_token]"
    assert {finding.category for finding in findings} == {
        "email",
        "sensitive-field",
        "bearer_token",
    }


def test_leakage_detects_duplicate_content_across_splits() -> None:
    findings = leakage_findings(
        [
            {"example_id": "a", "split": "train", "content": {"x": 1}},
            {"example_id": "b", "split": "test", "content": {"x": 1}},
        ]
    )

    assert findings[0]["kind"] == "duplicate-across-splits"
    assert findings[0]["first_example"] == "a"


def test_same_split_duplicate_is_not_cross_split_leakage() -> None:
    assert leakage_findings(
        [
            {"example_id": "a", "split": "train", "content": {"x": 1}},
            {"example_id": "b", "split": "train", "content": {"x": 1}},
        ]
    ) == ()
