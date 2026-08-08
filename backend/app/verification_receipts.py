"""Authenticated ingestion for DeployGuard Verify receipts."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import DomainError
from .models import ChangeRecord, Repository
from .config import Settings
from .job_producers import enqueue_github_check_publication
from .provider_models import ProviderConnection
from .provider_schemas import VerificationReceiptIngestResponse
from .verification_models import VerificationReceiptRecord
from .workspace_services import audit


_SHA_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _receipt_hash(receipt: dict[str, Any]) -> str:
    body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    return hashlib.sha256(_canonical_bytes(body)).hexdigest()


def _verify_signature(raw_body: bytes, signature: str, secret: str) -> None:
    normalized = signature.strip()
    if normalized.startswith("sha256="):
        normalized = normalized.removeprefix("sha256=")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", normalized):
        raise DomainError(
            "Receipt signature is malformed",
            "receipt_signature_invalid",
            401,
        )
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, normalized.lower()):
        raise DomainError(
            "Receipt signature is invalid",
            "receipt_signature_invalid",
            401,
        )


def _attestation_state(
    attestation: object,
    *,
    head_sha: str,
    receipt_sha256: str,
) -> str:
    if attestation is None:
        return "missing"
    if not isinstance(attestation, dict):
        return "invalid"
    subject_sha = str(attestation.get("subject_sha") or "")
    subject_digest = str(attestation.get("receipt_sha256") or "")
    verifier = str(attestation.get("verified_by") or "")
    if (
        subject_sha.lower() == head_sha.lower()
        and subject_digest.lower() == receipt_sha256.lower()
        and verifier in {"github_artifact_attestation", "sigstore"}
    ):
        return "verified"
    return "invalid"


def ingest_receipt(
    session: Session,
    *,
    workspace_id: str,
    repository_id: str,
    raw_body: bytes,
    signature: str,
    secret: str,
    request_id: str,
    settings: Settings | None = None,
) -> VerificationReceiptIngestResponse:
    if not secret.strip() or len(secret) < 32:
        raise DomainError(
            "Receipt ingestion is not configured",
            "receipt_ingest_not_configured",
            503,
        )
    _verify_signature(raw_body, signature, secret)
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise DomainError("Receipt JSON is invalid", "receipt_invalid", 422) from exc
    if not isinstance(payload, dict):
        raise DomainError("Receipt must be a JSON object", "receipt_invalid", 422)
    # v0.1 remains stable: attestations are detached metadata in an optional
    # envelope so adding provenance never changes the canonical receipt hash.
    if isinstance(payload.get("receipt"), dict):
        receipt = payload["receipt"]
        detached_attestation = payload.get("attestation")
    else:
        receipt = payload
        detached_attestation = receipt.get("attestation")
    repository_payload = receipt.get("repository")
    if not isinstance(repository_payload, dict):
        raise DomainError("Receipt repository identity is missing", "receipt_invalid", 422)
    repository = session.scalar(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.workspace_id == workspace_id,
            Repository.selected.is_(True),
            Repository.data_mode == "connected",
        )
    )
    if repository is None:
        raise DomainError("Repository not found", "repository_not_found", 404)
    if str(repository_payload.get("name") or "") != repository.full_name:
        raise DomainError(
            "Receipt repository does not match the selected repository",
            "receipt_repository_mismatch",
            409,
        )
    head_sha = str(repository_payload.get("head_sha") or "")
    if not _SHA_RE.fullmatch(head_sha):
        raise DomainError("Receipt head SHA is invalid", "receipt_sha_invalid", 422)
    declared_hash = str(receipt.get("receipt_sha256") or "")
    calculated_hash = _receipt_hash(receipt)
    if not hmac.compare_digest(declared_hash.lower(), calculated_hash):
        raise DomainError(
            "Receipt content hash does not match its canonical body",
            "receipt_hash_mismatch",
            422,
        )
    decision = str((receipt.get("decision") or {}).get("status") or "").lower()
    if decision not in {"pass", "review", "block", "error"}:
        raise DomainError("Receipt decision is invalid", "receipt_invalid", 422)
    change = session.scalar(
        select(ChangeRecord).where(
            ChangeRecord.workspace_id == workspace_id,
            ChangeRecord.repository_id == repository_id,
            ChangeRecord.commit_sha.ilike(head_sha),
            ChangeRecord.data_mode == "connected",
        ).order_by(ChangeRecord.created_at.desc())
    )
    if change is None:
        raise DomainError(
            "No connected change exists for this exact head SHA",
            "receipt_change_not_found",
            409,
        )
    attestation = detached_attestation
    attestation_state = _attestation_state(
        attestation,
        head_sha=head_sha,
        receipt_sha256=declared_hash,
    )
    existing = session.scalar(
        select(VerificationReceiptRecord).where(
            VerificationReceiptRecord.repository_id == repository_id,
            VerificationReceiptRecord.head_sha.ilike(head_sha),
        ).order_by(VerificationReceiptRecord.created_at.desc())
    )
    if existing is not None:
        if existing.receipt_sha256 != declared_hash:
            raise DomainError(
                "A different receipt is already recorded for this head SHA",
                "receipt_head_conflict",
                409,
            )
        return VerificationReceiptIngestResponse(
            receipt_id=existing.id,
            change_id=existing.change_id,
            head_sha=existing.head_sha,
            receipt_sha256=existing.receipt_sha256,
            decision=existing.decision,
            attestation_state=existing.attestation_state,
            status="duplicate",
            authenticated_at=existing.authenticated_at,
        )

    now = datetime.now(UTC)
    record = VerificationReceiptRecord(
        id=str(uuid4()),
        workspace_id=workspace_id,
        repository_id=repository_id,
        change_id=change.id,
        receipt_sha256=declared_hash,
        head_sha=head_sha,
        decision=decision,
        attestation_state=attestation_state,
        receipt=receipt,
        attestation=attestation if isinstance(attestation, dict) else None,
        authenticated_at=now,
        source="github_action",
        created_at=now,
    )
    session.add(record)
    change.flags = list(dict.fromkeys([*(change.flags or []), "verified-receipt"]))
    if settings is not None:
        connection = session.scalar(
            select(ProviderConnection).where(
                ProviderConnection.workspace_id == workspace_id,
                ProviderConnection.provider == "github",
                ProviderConnection.connection_state == "connected",
            )
        )
        if connection is not None:
            enqueue_github_check_publication(
                session,
                connection=connection,
                repository=repository,
                change=change,
                request_id=request_id,
                settings=settings,
                commit=False,
            )
    audit(
        session,
        workspace_id=workspace_id,
        actor_user_id=None,
        action="verification.receipt_ingested",
        resource_type="verification_receipt",
        resource_id=record.id,
        request_id=request_id,
        metadata={
            "repository_id": repository_id,
            "head_sha": head_sha,
            "receipt_sha256": declared_hash,
            "decision": decision,
            "attestation_state": attestation_state,
        },
    )
    session.commit()
    return VerificationReceiptIngestResponse(
        receipt_id=record.id,
        change_id=record.change_id,
        head_sha=record.head_sha,
        receipt_sha256=record.receipt_sha256,
        decision=record.decision,
        attestation_state=record.attestation_state,
        status="accepted",
        authenticated_at=record.authenticated_at,
    )
