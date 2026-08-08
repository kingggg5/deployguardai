"""Publish one receipt envelope to an authenticated DeployGuard ingress."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class _NoRedirect(HTTPRedirectHandler):
    """Never forward a signed receipt and its HMAC to another host."""

    def redirect_request(self, request, *args, **kwargs):  # type: ignore[override]
        return None


def urlopen(request: Request, *, timeout: int = 15):
    """Open the configured endpoint without following a redirect."""

    return build_opener(_NoRedirect).open(request, timeout=timeout)


def _read_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def publish(
    *,
    url: str,
    secret: str,
    receipt_path: Path,
    attestation_path: Path | None,
) -> dict[str, object]:
    if not url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        raise ValueError("receipt ingest URL must use HTTPS outside local development")
    if len(secret) < 32:
        raise ValueError("receipt ingest secret must be at least 32 characters")
    envelope: dict[str, object] = {"receipt": _read_object(receipt_path)}
    if attestation_path is not None:
        envelope["attestation"] = _read_object(attestation_path)
    body = json.dumps(
        envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-DeployGuard-Receipt-Signature": f"sha256={signature}",
            "User-Agent": "DeployGuard-Verify/0.1",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read(2 * 1024 * 1024)
    except (HTTPError, URLError) as error:
        raise RuntimeError(f"receipt ingest failed: {error}") from error
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise RuntimeError("receipt ingest returned a non-object response")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--secret", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--attestation", type=Path)
    args = parser.parse_args()
    result = publish(
        url=args.url,
        secret=args.secret,
        receipt_path=args.receipt,
        attestation_path=args.attestation,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
