from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import (
    AuditEvent,
    DatasetConsentDecisionRecord,
    IncidentRecord,
    PostmortemSnapshotRecord,
)


INCIDENT_ID = "inc-checkout-latency"
ATTESTATIONS = [
    "workspace_authorized",
    "secrets_reviewed",
    "privacy_reviewed",
    "license_reviewed",
]


def _promote_fixture_to_resolved_connected(client: TestClient) -> None:
    session = client.app.state.database.session_factory()
    try:
        incident = session.get(IncidentRecord, INCIDENT_ID)
        assert incident is not None
        incident.data_mode = "connected"
        incident.status = "resolved"
        incident.resolved_at = datetime.now(UTC)
        session.commit()
    finally:
        session.close()


def _record_verified_verdict(client: TestClient) -> dict[str, object]:
    response = client.post(
        f"/api/v1/incidents/{INCIDENT_ID}/feedback",
        json={
            "hypothesis_id": "hyp-payment-timeout",
            "verdict": "confirmed",
            "note": "Trace replay reproduced the timeout before retry fan-out.",
            "verification_outcome": {
                "result": "supported",
                "method": "trace replay",
                "summary": "The previous timeout removed the retry fan-out.",
                "evidence_ids": [
                    "ev-payment-trace",
                    "ev-timeout-config",
                ],
            },
        },
    )
    assert response.status_code == 201
    return response.json()["feedback"][-1]


def test_verdict_captures_server_owned_actor_and_structured_verification(
    client: TestClient,
) -> None:
    feedback = _record_verified_verdict(client)

    assert feedback["actor"] == {
        "user_id": feedback["actor"]["user_id"],
        "display_name": "Local workspace owner",
        "auth_provider": "development",
        "recorded_at": feedback["submitted_at"],
    }
    assert feedback["verification_outcome"] == {
        "result": "supported",
        "method": "trace replay",
        "summary": "The previous timeout removed the retry fan-out.",
        "evidence_ids": ["ev-payment-trace", "ev-timeout-config"],
        "recorded_at": feedback["submitted_at"],
    }

    session = client.app.state.database.session_factory()
    try:
        audit_event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "incident.verdict.recorded"
            )
        )
        assert audit_event is not None
        assert audit_event.actor_user_id == feedback["actor"]["user_id"]
        assert audit_event.event_metadata["verification_result"] == "supported"
    finally:
        session.close()


def test_dataset_governance_fails_closed_and_records_append_only_lineage(
    client: TestClient,
) -> None:
    synthetic = client.get(
        f"/api/v1/incidents/{INCIDENT_ID}/dataset-readiness"
    )
    assert synthetic.status_code == 200
    assert synthetic.json()["status"] == "not_applicable"
    assert synthetic.json()["connected_exporter_enabled"] is False

    _promote_fixture_to_resolved_connected(client)
    blocked_snapshot = client.post(
        f"/api/v1/incidents/{INCIDENT_ID}/postmortem-snapshots"
    )
    assert blocked_snapshot.status_code == 409
    assert blocked_snapshot.json()["code"] == "verified_human_verdict_required"

    _record_verified_verdict(client)
    first_snapshot = client.post(
        f"/api/v1/incidents/{INCIDENT_ID}/postmortem-snapshots"
    )
    second_snapshot = client.post(
        f"/api/v1/incidents/{INCIDENT_ID}/postmortem-snapshots"
    )
    assert first_snapshot.status_code == 201
    assert second_snapshot.status_code == 201
    assert second_snapshot.json()["id"] == first_snapshot.json()["id"]
    assert len(first_snapshot.json()["content_sha256"]) == 64

    incomplete = client.post(
        f"/api/v1/incidents/{INCIDENT_ID}/dataset-consent",
        json={
            "purpose": "evaluation",
            "decision": "approved",
            "terms_version": "dataset-consent-v1",
            "reason": "Approved for a privacy-reviewed evaluation release.",
            "attestations": ["workspace_authorized"],
        },
    )
    assert incomplete.status_code == 409
    assert incomplete.json()["code"] == "dataset_consent_attestations_incomplete"

    approved = client.post(
        f"/api/v1/incidents/{INCIDENT_ID}/dataset-consent",
        json={
            "purpose": "evaluation",
            "decision": "approved",
            "terms_version": "dataset-consent-v1",
            "reason": "Approved for a privacy-reviewed evaluation release.",
            "attestations": ATTESTATIONS,
        },
    )
    assert approved.status_code == 201
    assert approved.json()["postmortem_snapshot_id"] == first_snapshot.json()["id"]

    readiness = client.get(
        f"/api/v1/incidents/{INCIDENT_ID}/dataset-readiness"
    )
    assert readiness.status_code == 200
    assert readiness.json()["status"] == "ready_for_review"
    assert readiness.json()["connected_exporter_enabled"] is False
    assert all(item["satisfied"] for item in readiness.json()["requirements"])

    revoked = client.post(
        f"/api/v1/incidents/{INCIDENT_ID}/dataset-consent",
        json={
            "purpose": "evaluation",
            "decision": "revoked",
            "terms_version": "dataset-consent-v1",
            "reason": "Workspace owner withdrew evaluation permission.",
            "attestations": [],
        },
    )
    assert revoked.status_code == 201
    assert revoked.json()["postmortem_snapshot_id"] == first_snapshot.json()["id"]

    revoked_readiness = client.get(
        f"/api/v1/incidents/{INCIDENT_ID}/dataset-readiness"
    )
    assert revoked_readiness.status_code == 200
    assert revoked_readiness.json()["status"] == "blocked"
    assert revoked_readiness.json()["connected_exporter_enabled"] is False
    assert revoked_readiness.json()["requirements"][-1]["satisfied"] is False

    session = client.app.state.database.session_factory()
    try:
        assert session.query(PostmortemSnapshotRecord).count() == 1
        assert session.query(DatasetConsentDecisionRecord).count() == 2
        snapshot_id = first_snapshot.json()["id"]
        try:
            session.execute(
                text(
                    "UPDATE postmortem_snapshots SET content_markdown = "
                    "'tampered' WHERE id = :snapshot_id"
                ),
                {"snapshot_id": snapshot_id},
            )
            session.commit()
            raise AssertionError("immutable snapshot update unexpectedly succeeded")
        except DBAPIError:
            session.rollback()

        try:
            session.execute(
                text(
                    "UPDATE dataset_consent_decisions SET reason = "
                    "'tampered' WHERE id = :decision_id"
                ),
                {"decision_id": revoked.json()["id"]},
            )
            session.commit()
            raise AssertionError("immutable consent update unexpectedly succeeded")
        except DBAPIError:
            session.rollback()

        actions = set(
            session.scalars(
                select(AuditEvent.action).where(
                    AuditEvent.resource_id.in_(
                        [
                            snapshot_id,
                            approved.json()["id"],
                            revoked.json()["id"],
                        ]
                    )
                )
            )
        )
        assert actions == {
            "incident.postmortem.snapshot_created",
            "dataset.consent.approved",
            "dataset.consent.revoked",
        }
    finally:
        session.close()
