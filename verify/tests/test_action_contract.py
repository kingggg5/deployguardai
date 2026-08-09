from __future__ import annotations

from pathlib import Path


ACTION = Path(__file__).parents[2] / "action.yml"


def test_action_publishes_receipt_before_returning_review_or_block() -> None:
    source = ACTION.read_text(encoding="utf-8")
    assert "verify_status=" in source
    assert "always() && inputs.receipt-ingest-url != ''" in source
    assert "Return verification decision" in source
    assert "exit \"${status}\"" in source


def test_action_does_not_make_the_ingest_secret_an_action_input_default() -> None:
    source = ACTION.read_text(encoding="utf-8")
    assert "receipt-ingest-secret:" in source
    assert "default:" not in source[source.index("receipt-ingest-secret:") : source.index("receipt-ingest-secret:") + 300]
