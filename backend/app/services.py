import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .engines import calculate_blast_radius, calculate_change_risk
from .errors import DomainError
from .models import (
    ChangeRecord,
    FeedbackRecord,
    IncidentRecord,
    Repository,
    Scenario,
)
from .provider_models import ProviderConnection, WebhookDelivery
from .schemas import (
    AnalyzeChangeRequest,
    ChangeDetail,
    DoraMetricsResponse,
    FeedbackRequest,
    GitHubWebhookResponse,
    IncidentDetail,
    LLMSynthesisResponse,
    Overview,
    OverviewStats,
    ScenarioSummary,
    TelemetryIngestRequest,
)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def change_detail(record: ChangeRecord) -> ChangeDetail:
    return ChangeDetail.model_validate(
        {
            "id": record.id,
            "scenario_id": record.scenario_id,
            "data_mode": record.data_mode,
            "title": record.title,
            "repository": record.repository,
            "author": record.author,
            "commit_sha": record.commit_sha,
            "branch": record.branch,
            "created_at": _utc(record.created_at),
            "deployment_status": record.deployment_status,
            "deployment_environment": record.deployment_environment,
            "changed_services": record.changed_services,
            "files_changed": record.files_changed,
            "lines_added": record.lines_added,
            "lines_deleted": record.lines_deleted,
            "flags": record.flags,
            "risk": record.risk,
            "blast_radius": record.blast_radius,
        }
    )


def incident_detail(session: Session, record: IncidentRecord) -> IncidentDetail:
    feedback_records = session.scalars(
        select(FeedbackRecord)
        .where(FeedbackRecord.incident_id == record.id)
        .order_by(FeedbackRecord.submitted_at, FeedbackRecord.id)
    ).all()
    return IncidentDetail.model_validate(
        {
            "id": record.id,
            "scenario_id": record.scenario_id,
            "data_mode": record.data_mode,
            "title": record.title,
            "severity": record.severity,
            "status": record.status,
            "started_at": _utc(record.started_at),
            "resolved_at": _utc(record.resolved_at),
            "affected_services": record.affected_services,
            "correlated_change_id": record.correlated_change_id,
            "summary": record.summary,
            "timeline": record.timeline,
            "evidence": record.evidence,
            "hypotheses": record.hypotheses,
            "feedback": [
                {
                    "verdict": item.verdict,
                    "hypothesis_id": item.hypothesis_id,
                    "note": item.note,
                    "submitted_at": _utc(item.submitted_at),
                }
                for item in feedback_records
            ],
        }
    )


def list_scenarios(
    session: Session,
    workspace_id: str | None = None,
    active_scenario_id: str | None = None,
) -> list[ScenarioSummary]:
    statement = select(Scenario)
    if workspace_id is not None:
        statement = statement.where(Scenario.workspace_id == workspace_id)
    records = session.scalars(
        statement.order_by(Scenario.sort_order, Scenario.id)
    ).all()
    change_ids = [record.active_change_id for record in records]
    changes = session.scalars(
        select(ChangeRecord).where(ChangeRecord.id.in_(change_ids))
    ).all()
    repositories = {change.id: change.repository for change in changes}
    return [
        ScenarioSummary.model_validate(
            {
                "id": record.id,
                "name": record.name,
                "description": record.description,
                "repository": repositories.get(
                    record.active_change_id, "unassigned"
                ),
                "data_mode": record.data_mode,
                "is_active": (
                    record.id == active_scenario_id
                    if active_scenario_id is not None
                    else record.is_active
                ),
                "active_change_id": record.active_change_id,
                "active_incident_id": record.active_incident_id,
            }
        )
        for record in records
    ]


def list_changes(
    session: Session,
    workspace_id: str | None = None,
    repository_id: str | None = None,
) -> list[ChangeDetail]:
    statement = select(ChangeRecord)
    if workspace_id is not None:
        statement = statement.where(ChangeRecord.workspace_id == workspace_id)
    if repository_id is not None:
        statement = statement.where(ChangeRecord.repository_id == repository_id)
    records = session.scalars(
        statement.order_by(ChangeRecord.created_at.desc())
    ).all()
    return [change_detail(record) for record in records]


def get_change(
    session: Session,
    change_id: str,
    workspace_id: str | None = None,
) -> ChangeDetail:
    statement = select(ChangeRecord).where(ChangeRecord.id == change_id)
    if workspace_id is not None:
        statement = statement.where(ChangeRecord.workspace_id == workspace_id)
    record = session.scalar(statement)
    if record is None:
        raise DomainError("Change not found", "change_not_found", 404)
    return change_detail(record)


def list_incidents(
    session: Session, workspace_id: str | None = None
) -> list[IncidentDetail]:
    statement = select(IncidentRecord)
    if workspace_id is not None:
        statement = statement.where(IncidentRecord.workspace_id == workspace_id)
    records = session.scalars(
        statement.order_by(IncidentRecord.started_at.desc())
    ).all()
    return [incident_detail(session, record) for record in records]


def get_incident(
    session: Session,
    incident_id: str,
    workspace_id: str | None = None,
) -> IncidentDetail:
    statement = select(IncidentRecord).where(IncidentRecord.id == incident_id)
    if workspace_id is not None:
        statement = statement.where(
            IncidentRecord.workspace_id == workspace_id
        )
    record = session.scalar(statement)
    if record is None:
        raise DomainError("Incident not found", "incident_not_found", 404)
    return incident_detail(session, record)


def active_scenario(
    session: Session,
    *,
    workspace_id: str | None = None,
    repository_id: str | None = None,
    scenario_id: str | None = None,
) -> Scenario:
    statement = select(Scenario)
    if workspace_id is not None:
        statement = statement.where(Scenario.workspace_id == workspace_id)
    if repository_id is not None:
        statement = statement.where(Scenario.repository_id == repository_id)
    if scenario_id is not None:
        statement = statement.where(Scenario.id == scenario_id)
    else:
        statement = statement.where(Scenario.is_active.is_(True))
    scenario = session.scalar(
        statement.order_by(Scenario.sort_order, Scenario.id)
    )
    if scenario is None and scenario_id is None and workspace_id is not None:
        fallback = select(Scenario).where(
            Scenario.workspace_id == workspace_id
        )
        if repository_id is not None:
            fallback = fallback.where(
                Scenario.repository_id == repository_id
            )
        scenario = session.scalar(
            fallback.order_by(Scenario.sort_order, Scenario.id)
        )
    if scenario is None:
        raise DomainError(
            "No active scenario is configured", "active_scenario_not_found", 409
        )
    return scenario


def get_overview(session: Session, scenario: Scenario | None = None) -> Overview:
    selected = scenario or active_scenario(session)
    change = (
        session.get(ChangeRecord, selected.active_change_id)
        if selected.active_change_id
        else None
    )
    incident = (
        session.get(IncidentRecord, selected.active_incident_id)
        if selected.active_incident_id
        else None
    )
    if change is None:
        change = session.scalars(select(ChangeRecord).where(ChangeRecord.scenario_id == selected.id)).first()
    if incident is None:
        incident = session.scalars(select(IncidentRecord).where(IncidentRecord.scenario_id == selected.id)).first()

    if change is None or incident is None:
        raise DomainError(
            "Active scenario data is incomplete",
            "scenario_data_incomplete",
            409,
        )

    scenario_changes = session.scalars(
        select(ChangeRecord).where(ChangeRecord.scenario_id == selected.id)
    ).all()
    scenario_incidents = session.scalars(
        select(IncidentRecord).where(IncidentRecord.scenario_id == selected.id)
    ).all()
    open_statuses = {"open", "investigating", "monitoring", "mitigating"}
    all_evidence = [
        evidence
        for scenario_incident in scenario_incidents
        for evidence in scenario_incident.evidence
    ]
    evidence_quality = (
        sum(float(item.get("quality", 0.0)) for item in all_evidence)
        / len(all_evidence)
        if all_evidence
        else 0.0
    )
    return Overview(
        generated_at=datetime.now(UTC),
        data_mode=selected.data_mode,
        active_scenario_id=selected.id,
        stats=OverviewStats(
            open_incidents=sum(
                incident_item.status.lower() in open_statuses
                for incident_item in scenario_incidents
            ),
            high_risk_changes=sum(
                int(change_item.risk.get("overall_score", 0)) >= 50
                for change_item in scenario_changes
            ),
            services_monitored=len(selected.service_graph.get("nodes", [])),
            evidence_quality=round(evidence_quality, 2),
        ),
        active_change=change_detail(change),
        active_incident=incident_detail(session, incident),
    )


def activate_scenario(
    session: Session,
    scenario_id: str,
    workspace_id: str | None = None,
) -> Overview:
    statement = select(Scenario).where(Scenario.id == scenario_id)
    if workspace_id is not None:
        statement = statement.where(Scenario.workspace_id == workspace_id)
    scenario = session.scalar(statement)
    if scenario is None:
        raise DomainError("Scenario not found", "scenario_not_found", 404)
    return get_overview(session, scenario)


def analyze_change(
    session: Session,
    request: AnalyzeChangeRequest,
    *,
    workspace_id: str | None = None,
    repository_id: str | None = None,
    scenario_id: str | None = None,
) -> ChangeDetail:
    scenario = active_scenario(
        session,
        workspace_id=workspace_id,
        repository_id=repository_id,
        scenario_id=scenario_id,
    )
    canonical = json.dumps(
        {
            "workspace_id": workspace_id,
            "repository_id": repository_id,
            "request": request.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    change_id = f"chg-analysis-{digest[:12]}"
    existing = session.get(ChangeRecord, change_id)
    if existing is not None:
        return change_detail(existing)

    graph = scenario.service_graph
    tiers = {
        str(node["id"]): node.get("tier", "tier-3")
        for node in graph.get("nodes", [])
    }
    risk = calculate_change_risk(
        files_changed=request.files_changed,
        lines_added=request.lines_added,
        lines_deleted=request.lines_deleted,
        changed_services=request.changed_services,
        flags=request.flags,
        test_coverage=request.test_coverage,
        rollback_ready=request.rollback_ready,
        observability_score=request.observability_score,
        previous_failures=request.previous_failures,
        service_tiers=tiers,
        evidence_prefix=change_id,
    )
    blast_radius = calculate_blast_radius(
        nodes=graph.get("nodes", []),
        edges=graph.get("edges", []),
        changed_services=request.changed_services,
        evidence_prefix=change_id,
    )
    record = ChangeRecord(
        id=change_id,
        workspace_id=scenario.workspace_id,
        repository_id=scenario.repository_id,
        scenario_id=scenario.id,
        data_mode=scenario.data_mode,
        title=request.title,
        repository=request.repository,
        author=request.author,
        commit_sha=digest[:12],
        branch="analysis/manual",
        created_at=datetime.now(UTC),
        deployment_status="not_deployed",
        deployment_environment="staging",
        changed_services=request.changed_services,
        files_changed=request.files_changed,
        lines_added=request.lines_added,
        lines_deleted=request.lines_deleted,
        flags=request.flags,
        test_coverage=request.test_coverage,
        rollback_ready=request.rollback_ready,
        observability_score=request.observability_score,
        previous_failures=request.previous_failures,
        risk=risk,
        blast_radius=blast_radius,
    )
    session.add(record)
    session.commit()
    return change_detail(record)


def submit_feedback(
    session: Session,
    incident_id: str,
    request: FeedbackRequest,
    workspace_id: str | None = None,
) -> IncidentDetail:
    statement = select(IncidentRecord).where(IncidentRecord.id == incident_id)
    if workspace_id is not None:
        statement = statement.where(
            IncidentRecord.workspace_id == workspace_id
        )
    incident = session.scalar(statement)
    if incident is None:
        raise DomainError("Incident not found", "incident_not_found", 404)
    if not any(
        hypothesis["id"] == request.hypothesis_id
        for hypothesis in incident.hypotheses
    ):
        raise DomainError(
            "Hypothesis not found for this incident",
            "hypothesis_not_found",
            404,
        )

    hypotheses = [dict(item) for item in incident.hypotheses]
    for hypothesis in hypotheses:
        if hypothesis["id"] == request.hypothesis_id:
            hypothesis["status"] = request.verdict
    incident.hypotheses = hypotheses
    session.add(
        FeedbackRecord(
            incident_id=incident.id,
            hypothesis_id=request.hypothesis_id,
            verdict=request.verdict,
            note=request.note,
            submitted_at=datetime.now(UTC),
        )
    )
    session.commit()
    return incident_detail(session, incident)


def get_dora_metrics(
    session: Session, workspace_id: str | None = None
) -> DoraMetricsResponse:
    window_days = 30
    deployed_statuses = {"deployed", "rolled_back"}
    changes_statement = select(ChangeRecord)
    incidents_statement = select(IncidentRecord)
    if workspace_id is not None:
        changes_statement = changes_statement.where(
            ChangeRecord.workspace_id == workspace_id
        )
        incidents_statement = incidents_statement.where(
            IncidentRecord.workspace_id == workspace_id
        )
    all_changes = session.scalars(changes_statement).all()
    all_incidents = session.scalars(incidents_statement).all()
    records = [*all_changes, *all_incidents]
    observed_timestamps = [
        timestamp
        for timestamp in (
            *(_utc(change.created_at) for change in all_changes),
            *(_utc(incident.started_at) for incident in all_incidents),
        )
        if timestamp is not None
    ]
    is_synthetic_dataset = bool(records) and all(
        record.data_mode == "synthetic" for record in records
    )
    window_end = (
        max(observed_timestamps)
        if is_synthetic_dataset and observed_timestamps
        else datetime.now(UTC)
    )
    cutoff = window_end - timedelta(days=window_days)

    changes = [
        change
        for change in all_changes
        if change.deployment_status.lower() in deployed_statuses
        and (_utc(change.created_at) or cutoff) >= cutoff
    ]
    incidents = [
        incident
        for incident in all_incidents
        if (_utc(incident.started_at) or cutoff) >= cutoff
    ]

    deployed_change_ids = {change.id for change in changes}
    failed_deployments = {
        incident.correlated_change_id
        for incident in incidents
        if incident.correlated_change_id in deployed_change_ids
    }
    total_deployments = len(changes)
    change_failure_rate = (
        len(failed_deployments) / total_deployments if total_deployments else 0.0
    )

    lead_times: list[float] = []
    for change in changes:
        change_created = _utc(change.created_at)
        if change_created is None:
            continue
        deployment_markers = [
            _timeline_timestamp(event.get("timestamp"))
            for incident in incidents
            if incident.correlated_change_id == change.id
            for event in (incident.timeline or [])
            if str(event.get("type", "")).lower() in {"deploy", "deployment"}
        ]
        valid_markers = [
            marker
            for marker in deployment_markers
            if marker is not None and marker >= change_created
        ]
        if valid_markers:
            lead_times.append(
                (min(valid_markers) - change_created).total_seconds() / 60
            )

    restore_times: list[float] = []
    for incident in incidents:
        started_at = _utc(incident.started_at)
        if started_at is None:
            continue
        restored_at = _utc(incident.resolved_at)
        if restored_at is None:
            recovery_markers = [
                _timeline_timestamp(event.get("timestamp"))
                for event in (incident.timeline or [])
                if str(event.get("type", "")).lower() == "recovery"
            ]
            recovery_markers = [
                marker
                for marker in recovery_markers
                if marker is not None and marker >= started_at
            ]
            restored_at = max(recovery_markers) if recovery_markers else None
        if restored_at is not None and restored_at >= started_at:
            restore_times.append((restored_at - started_at).total_seconds() / 60)

    rollback_count = sum(
        change.deployment_status.lower() == "rolled_back" for change in changes
    )

    return DoraMetricsResponse(
        period="Last 30 Days",
        deployment_frequency_per_week=round(
            total_deployments / (window_days / 7), 1
        ),
        change_lead_time_minutes=round(_mean_or_zero(lead_times), 1),
        change_failure_rate=round(change_failure_rate, 3),
        mean_time_to_restore_minutes=round(_mean_or_zero(restore_times), 1),
        deployment_rework_rate=round(
            rollback_count / total_deployments if total_deployments else 0.0,
            3,
        ),
        total_deployments=total_deployments,
        total_incidents=len(incidents),
    )


def _timeline_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _utc(value)
    if isinstance(value, str):
        try:
            return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _mean_or_zero(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


import hmac


def verify_github_signature(secret: str, raw_body: bytes, signature_header: str) -> bool:
    if not signature_header or not secret:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), msg=raw_body, digestmod=hashlib.sha256).hexdigest()
    actual = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, actual)


def process_github_webhook(
    session: Session,
    event_type: str,
    delivery_id: str,
    payload: dict,
    signature: str = "",
    raw_body: bytes = b"",
    secret: str = "",
    allow_synthetic_fallback: bool = False,
) -> GitHubWebhookResponse:
    if not secret:
        raise DomainError(
            "GitHub webhook ingestion is not configured",
            "github_webhook_not_configured",
            503,
        )
    if not signature or not verify_github_signature(
        secret, raw_body, signature
    ):
        raise DomainError(
            "Invalid GitHub Webhook HMAC Signature",
            "invalid_signature",
            401,
        )

    existing_delivery = session.scalar(
        select(WebhookDelivery).where(
            WebhookDelivery.provider == "github",
            WebhookDelivery.delivery_id == delivery_id,
        )
    )
    if existing_delivery is not None:
        return GitHubWebhookResponse(
            status="accepted",
            event=event_type,
            delivery_id=delivery_id,
            detail="Duplicate delivery was already recorded.",
        )

    installation_id = str((payload.get("installation") or {}).get("id") or "")
    provider_repository_id = str(
        (payload.get("repository") or {}).get("id") or ""
    )
    connection = (
        session.scalar(
            select(ProviderConnection).where(
                ProviderConnection.provider == "github",
                ProviderConnection.installation_id == installation_id,
            )
        )
        if installation_id
        else None
    )
    repository = (
        session.scalar(
            select(Repository).where(
                Repository.workspace_id == connection.workspace_id,
                Repository.provider == "github",
                Repository.provider_repository_id == provider_repository_id,
                Repository.selected.is_(True),
            )
        )
        if connection is not None and provider_repository_id
        else None
    )
    installation_event = event_type in {
        "installation",
        "installation_repositories",
    }
    if installation_event:
        if connection is not None:
            action = str(payload.get("action") or "")
            connection.connection_state = (
                "revoked"
                if action in {"deleted", "suspend"}
                else "connected"
            )
            connection.updated_at = datetime.now(UTC)
        session.add(
            WebhookDelivery(
                id=str(uuid4()),
                provider="github",
                delivery_id=delivery_id,
                event_type=event_type,
                installation_id=installation_id or None,
                workspace_id=(
                    connection.workspace_id if connection is not None else None
                ),
                repository_id=None,
                status=(
                    "verified" if connection is not None else "verified_unmapped"
                ),
                created_at=datetime.now(UTC),
            )
        )
        session.commit()
        return GitHubWebhookResponse(
            status="accepted",
            event=event_type,
            delivery_id=delivery_id,
            detail="Signed GitHub installation state was recorded.",
        )
    if connection is not None:
        session.add(
            WebhookDelivery(
                id=str(uuid4()),
                provider="github",
                delivery_id=delivery_id,
                event_type=event_type,
                installation_id=installation_id or None,
                workspace_id=connection.workspace_id,
                repository_id=repository.id if repository is not None else None,
                status="verified" if repository is not None else "ignored",
                created_at=datetime.now(UTC),
            )
        )
        session.commit()
        if repository is None:
            return GitHubWebhookResponse(
                status="ignored",
                event=event_type,
                delivery_id=delivery_id,
                detail="Repository is not selected for this workspace.",
            )
        if event_type == "pull_request" and str(
            payload.get("action") or ""
        ) in {"opened", "reopened", "synchronize", "ready_for_review"}:
            pr_data = payload.get("pull_request") or {}
            labels = [
                str(label.get("name"))
                for label in pr_data.get("labels", [])
                if isinstance(label, dict) and label.get("name")
            ]
            detail = analyze_change(
                session,
                AnalyzeChangeRequest(
                    title=str(pr_data.get("title") or "Untitled pull request")[
                        :240
                    ],
                    repository=repository.full_name,
                    author=str(
                        (pr_data.get("user") or {}).get("login") or "unknown"
                    )[:160],
                    files_changed=int(pr_data.get("changed_files") or 0),
                    lines_added=int(pr_data.get("additions") or 0),
                    lines_deleted=int(pr_data.get("deletions") or 0),
                    changed_services=[repository.full_name],
                    flags=labels[:100],
                    test_coverage=0.0,
                    rollback_ready=False,
                    observability_score=0.0,
                    previous_failures=0,
                ),
                workspace_id=connection.workspace_id,
                repository_id=repository.id,
            )
            scenario = active_scenario(
                session,
                workspace_id=connection.workspace_id,
                repository_id=repository.id,
            )
            scenario.active_change_id = detail.id
            session.commit()
            return GitHubWebhookResponse(
                status="accepted",
                event=event_type,
                delivery_id=delivery_id,
                change_id=detail.id,
                detail=(
                    "Verified pull request evidence was analyzed in its "
                    "connected repository context."
                ),
            )
        return GitHubWebhookResponse(
            status="accepted",
            event=event_type,
            delivery_id=delivery_id,
            detail="Verified provider event was durably recorded.",
        )

    if not allow_synthetic_fallback:
        raise DomainError(
            "GitHub installation is not linked to a workspace",
            "github_installation_not_linked",
            404,
        )

    if event_type not in ["pull_request", "workflow_run", "deployment_status"]:
        return GitHubWebhookResponse(
            status="ignored",
            event=event_type,
            delivery_id=delivery_id,
            detail=f"Event type '{event_type}' is not monitored.",
        )

    scenario = active_scenario(session)
    pr_data = payload.get("pull_request", payload)
    title = pr_data.get("title", "GitHub Webhook Event")
    repo = payload.get("repository", {}).get("full_name", "acme/checkout-platform")
    author = pr_data.get("user", {}).get("login", "github-app")

    req = AnalyzeChangeRequest(
        title=title[:240],
        repository=repo[:240],
        author=author[:160],
        files_changed=int(pr_data.get("changed_files", 5)),
        lines_added=int(pr_data.get("additions", 120)),
        lines_deleted=int(pr_data.get("deletions", 30)),
        changed_services=["checkout-api", "payment-adapter"],
        flags=["config-change", "retry-policy"],
        test_coverage=0.75,
        rollback_ready=True,
        observability_score=0.90,
        previous_failures=1,
    )

    detail = analyze_change(session, req)
    return GitHubWebhookResponse(
        status="accepted",
        event=event_type,
        delivery_id=delivery_id,
        change_id=detail.id,
        detail=f"Webhook processed and change risk analyzed (Score: {detail.risk.overall_score}/100).",
    )


def ingest_telemetry_event(
    session: Session, request: TelemetryIngestRequest
) -> dict:
    scenario = active_scenario(session)
    incident = session.query(IncidentRecord).filter_by(scenario_id=scenario.id).first()
    if incident is None:
        raise DomainError("No active incident record found", "incident_not_found", 404)

    ev_id = f"ev-ingest-{int(datetime.now(UTC).timestamp())}"
    new_ev = {
        "id": ev_id,
        "type": request.type,
        "source": request.source,
        "timestamp": datetime.now(UTC).isoformat(),
        "summary": request.summary,
        "value": request.value,
        "quality": 0.95,
        "service_id": request.service_id,
        "supports": request.supports_hypothesis_ids,
        "contradicts": request.contradicts_hypothesis_ids,
    }

    current_evidence = list(incident.evidence or [])
    current_evidence.append(new_ev)
    incident.evidence = current_evidence
    session.add(incident)
    session.commit()
    return {"status": "ok", "evidence_id": ev_id, "detail": "Telemetry event ingested successfully."}


def export_incident_postmortem(
    session: Session,
    incident_id: str,
    workspace_id: str | None = None,
) -> str:
    inc = get_incident(session, incident_id, workspace_id)
    lines = [
        f"# Incident Post-Mortem: {inc.title}",
        "",
        f"- **Incident ID**: `{inc.id}`",
        f"- **Severity**: `{inc.severity.upper()}`",
        f"- **Status**: `{inc.status.upper()}`",
        f"- **Started At**: `{inc.started_at}`",
        f"- **Resolved At**: `{inc.resolved_at or 'N/A'}`",
        f"- **Correlated PR**: `{inc.correlated_change_id or 'None'}`",
        "",
        "## Executive Summary",
        inc.summary,
        "",
        "## Top RCA Hypotheses",
    ]
    for h in inc.hypotheses:
        lines.append(f"### Rank {h.rank}: {h.cause_service} - {h.cause} (Confidence: {h.confidence * 100:.0f}%)")
        lines.append(f"- **Reasoning**: {h.reasoning}")
        lines.append(f"- **Recommended Next Steps**: {h.next_step}")
        lines.append("")

    lines.extend([
        "## Human Feedback & Verification Log",
    ])
    for f in inc.feedback:
        lines.append(f"- **Verdict**: `{f.verdict.upper()}` | **Submitted At**: `{f.submitted_at}`")
        lines.append(f"  - **Note**: {f.note}")

    return "\n".join(lines)


def synthesize_llm_hypotheses(
    session: Session, incident_id: str
) -> LLMSynthesisResponse:
    incident = session.get(IncidentRecord, incident_id)
    if incident is None:
        raise DomainError("Incident not found", "incident_not_found", 404)

    raise DomainError(
        (
            "LLM synthesis is disabled until an evidence-only contract "
            "and evaluation gate are configured"
        ),
        "llm_synthesis_disabled",
        501,
    )


def reset_database(session: Session) -> dict[str, str]:
    from .seed import seed_database

    session.query(FeedbackRecord).delete()
    session.query(IncidentRecord).delete()
    session.query(ChangeRecord).delete()
    session.query(Scenario).delete()
    session.commit()
    seed_database(session)
    return {"status": "ok", "detail": "Database reset and re-seeded successfully."}
