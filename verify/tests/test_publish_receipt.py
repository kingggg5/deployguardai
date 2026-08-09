from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from deployguard_verify import publish_receipt


class _Response:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int) -> bytes:
        return b'{"status":"accepted"}'


def test_publish_receipt_signs_canonical_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "s" * 32
    receipt = {"receipt_sha256": "a" * 64, "repository": {"head_sha": "b" * 40}}
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        body = request.data
        assert isinstance(body, bytes)
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert request.get_header("X-deployguard-receipt-signature") == f"sha256={expected}"
        assert json.loads(body) == {"receipt": receipt}
        return _Response()

    monkeypatch.setattr(publish_receipt, "urlopen", fake_urlopen)
    result = publish_receipt.publish(
        url="https://deployguard.example/receipts",
        secret=secret,
        receipt_path=receipt_path,
        attestation_path=None,
    )

    assert result == {"status": "accepted"}
    assert captured == {"url": "https://deployguard.example/receipts", "timeout": 15}


def test_publish_receipt_rejects_insecure_remote_url(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="HTTPS"):
        publish_receipt.publish(
            url="http://collector.example/receipts",
            secret="s" * 32,
            receipt_path=receipt_path,
            attestation_path=None,
        )
