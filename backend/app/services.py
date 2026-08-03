import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .deployment_services import upsert_github_deployment
from .engines import (
    ANALYSIS_SCHEMA_VERSION,
    ENGINE_VERSION,
    GRAPH_VERSION,
    RISK_SCORING_POLICY_VERSION,
    calculate_blast_radius,
    calculate_change_risk,
)
from .errors import DomainError
from .models import (
    ChangeRecord,
    FeedbackRecord,
    IncidentRecord,
    LEGACY_REPOSITORY_ID,
    LEGACY_WORKSPACE_ID,
    Repository,
    Scenario,
    Workspace,
)
from .operations_models import ServiceCatalogEntry
from .operations_schemas import (
    OperationalEventCreate,
    OperationalEventResponse,
)
from .operations_services import record_trusted_operational_event
from .provider_models import ProviderConnection, WebhookDelivery
from .provider_services import publish_github_change_check_from_webhook
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
            "workspace_id": record.workspace_id,
            "repository_id": record.repository_id,
            "scenario_id": record.scenario_id,
            "data_mode": record.data_mode,
            "analysis_schema_version": record.analysis_schema_version,
            "engine_version": record.engine_version,
            "scoring_policy_version": record.scoring_policy_version,
            "graph_version": record.graph_version,
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
            "analysis_schema_version": record.analysis_schema_version,
            "engine_version": record.engine_version,
            "scoring_policy_version": record.scoring_policy_version,
            "graph_version": record.graph_version,
            "title": record.title,
            "severity": record.severity,
            "status": record.status,
            "assignee_user_id": record.assignee_user_id,
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

    if change is None:
        raise DomainError(
            "Active scenario has no connected change evidence yet",
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
        active_incident=incident_detail(session, incident) if incident else None,
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


def _analysis_graph(
    session: Session,
    *,
    scenario: Scenario,
    repository_id: str | None,
    requested_services: list[str],
) -> tuple[dict, list[str]]:
    """Overlay the workspace catalog onto provider topology deterministically."""
    catalog = session.scalars(
        select(ServiceCatalogEntry)
        .where(ServiceCatalogEntry.workspace_id == scenario.workspace_id)
        .order_by(ServiceCatalogEntry.id)
    ).all()
    if not catalog:
        return scenario.service_graph, list(requested_services)

    base_graph = scenario.service_graph or {}
    nodes_by_id = {
        str(node["id"]): dict(node)
        for node in base_graph.get("nodes", [])
        if isinstance(node, dict) and node.get("id")
    }
    edges_by_identity = {
        (
            str(edge.get("source")),
            str(edge.get("target")),
            str(edge.get("relation") or "runtime-dependency"),
        ): dict(edge)
        for edge in base_graph.get("edges", [])
        if isinstance(edge, dict) and edge.get("source") and edge.get("target")
    }
    service_by_reference: dict[str, ServiceCatalogEntry] = {}
    repository_roots: list[str] = []
    for service in catalog:
        nodes_by_id[service.id] = {
            "id": service.id,
            "label": service.name,
            "kind": "service",
            "team": service.owner_team,
            "tier": service.tier.replace("_", "-"),
            "health": "unknown",
        }
        for reference in (service.id, service.slug, service.name):
            service_by_reference[reference.casefold()] = service
        if repository_id is not None and service.repository_id == repository_id:
            repository_roots.append(service.id)
        for dependency_id in sorted(set(service.dependencies or [])):
            edges_by_identity[
                (dependency_id, service.id, "catalog-dependency")
            ] = {
                "source": dependency_id,
                "target": service.id,
                "relation": "catalog-dependency",
                "confidence": 1.0,
                "active": True,
            }

    resolved_roots = {
        service.id
        for reference in requested_services
        if (service := service_by_reference.get(reference.casefold())) is not None
    }
    resolved_roots.update(repository_roots)
    effective_roots = (
        sorted(resolved_roots)
        if resolved_roots
        else list(dict.fromkeys(requested_services))
    )
    if len(effective_roots) > 100:
        raise DomainError(
            "Repository maps to more than 100 changed services",
            "analysis_service_limit",
            422,
        )
    graph = {
        "nodes": [nodes_by_id[key] for key in sorted(nodes_by_id)],
        "edges": [
            edges_by_identity[key]
            for key in sorted(edges_by_identity)
        ],
        "updated_at": base_graph.get("updated_at"),
    }
    return graph, effective_roots


def _canonical_topology(graph: dict) -> dict[str, list[dict]]:
    """Keep the analysis digest stable while topology evidence is unchanged."""
    nodes = [
        {
            key: node.get(key)
            for key in ("id", "label", "kind", "team", "tier", "health")
        }
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and node.get("id")
    ]
    edges = [
        {
            key: edge.get(key)
            for key in ("source", "target", "relation", "confidence", "active")
        }
        for edge in graph.get("edges", [])
        if isinstance(edge, dict) and edge.get("source") and edge.get("target")
    ]
    return {
        "nodes": sorted(nodes, key=lambda item: str(item["id"])),
        "edges": sorted(
            edges,
            key=lambda item: (
                str(item["source"]),
                str(item["target"]),
                str(item["relation"]),
            ),
        ),
    }


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
    graph, effective_changed_services = _analysis_graph(
        session,
        scenario=scenario,
        repository_id=repository_id,
        requested_services=request.changed_services,
    )
    analysis_versions = {
        "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "scoring_policy_version": RISK_SCORING_POLICY_VERSION,
        "graph_version": GRAPH_VERSION,
    }
    canonical = json.dumps(
        {
            "workspace_id": scenario.workspace_id,
            "repository_id": scenario.repository_id,
            "request": request.model_dump(mode="json"),
            "effective_changed_services": effective_changed_services,
            "topology": _canonical_topology(graph),
            "analysis_versions": analysis_versions,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    change_id = f"chg-analysis-{digest[:12]}"
    existing = session.get(ChangeRecord, change_id)
    if existing is not None:
        return change_detail(existing)

    tiers = {
        str(node["id"]): node.get("tier", "tier-3")
        for node in graph.get("nodes", [])
    }
    risk = calculate_change_risk(
        files_changed=request.files_changed,
        lines_added=request.lines_added,
        lines_deleted=request.lines_deleted,
        changed_services=effective_changed_services,
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
        changed_services=effective_changed_services,
        evidence_prefix=change_id,
    )
    record = ChangeRecord(
        id=change_id,
        workspace_id=scenario.workspace_id,
        repository_id=scenario.repository_id,
        scenario_id=scenario.id,
        data_mode=scenario.data_mode,
        **analysis_versions,
        title=request.title,
        repository=request.repository,
        author=request.author,
        commit_sha=request.commit_sha or digest[:12],
        branch=request.branch or "analysis/manual",
        created_at=datetime.now(UTC),
        deployment_status="not_deployed",
        deployment_environment=request.deployment_environment,
        changed_services=effective_changed_services,
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


def _github_operational_event(
    session: Session,
    *,
    event_type: str,
    delivery_id: str,
    payload: dict,
    connection: ProviderConnection,
    repository: Repository,
) -> OperationalEventResponse:
    action = str(payload.get("action") or "")
    workflow = payload.get("workflow_run") or {}
    deployment = payload.get("deployment") or {}
    deployment_status = payload.get("deployment_status") or {}
    pull_request = payload.get("pull_request") or {}
    timestamp = next(
        (
            parsed
            for value in (
                workflow.get("updated_at"),
                workflow.get("run_started_at"),
                deployment_status.get("created_at"),
                deployment.get("created_at"),
                pull_request.get("updated_at"),
            )
            if (parsed := _timeline_timestamp(value)) is not None
        ),
        datetime.now(UTC),
    )
    now = datetime.now(UTC)
    if timestamp > now + timedelta(minutes=5):
        timestamp = now

    status_value = str(
        workflow.get("conclusion")
        or workflow.get("status")
        or deployment_status.get("state")
        or action
        or "received"
    ).lower()
    if status_value in {"failure", "failed", "error", "timed_out"}:
        severity = "error"
    elif status_value in {"cancelled", "stale", "inactive"}:
        severity = "warning"
    else:
        severity = "info"
    display_name = str(
        workflow.get("name")
        or deployment.get("environment")
        or (payload.get("repository") or {}).get("full_name")
        or repository.full_name
    )[:240]
    summary = (
        f"GitHub {event_type.replace('_', ' ')}"
        f"{f' {action}' if action else ''}: {display_name} ({status_value})."
    )[:1_000]
    head = pull_request.get("head") or {}
    attributes = {
        key: value
        for key, value in {
            "action": action or None,
            "status": status_value,
            "workflow_id": workflow.get("id"),
            "workflow_name": workflow.get("name"),
            "workflow_url": workflow.get("html_url"),
            "deployment_id": deployment.get("id"),
            "environment": deployment.get("environment"),
            "commit_sha": (
                workflow.get("head_sha")
                or deployment.get("sha")
                or head.get("sha")
            ),
            "branch": workflow.get("head_branch") or head.get("ref"),
        }.items()
        if value not in {None, ""}
    }
    return record_trusted_operational_event(
        session,
        connection.workspace_id,
        OperationalEventCreate(
            provider_event_id=delivery_id,
            repository_id=repository.id,
            service_id=None,
            incident_id=None,
            source="github",
            event_type=event_type,
            occurred_at=timestamp,
            severity=severity,
            summary=summary,
            attributes=attributes,
            provenance={
                "provider": "github",
                "delivery_id": delivery_id,
                "installation_id": connection.installation_id,
                "signature_verified": True,
                "provider_repository_id": repository.provider_repository_id,
            },
        ),
        request_id=f"github:{delivery_id}",
    )


def process_github_webhook(
    session: Session,
    event_type: str,
    delivery_id: str,
    payload: dict,
    signature: str = "",
    raw_body: bytes = b"",
    secret: str = "",
    allow_synthetic_fallback: bool = False,
    settings=None,
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
    reconcilable_events = {
        "pull_request",
        "workflow_run",
        "deployment",
        "deployment_status",
    }
    if (
        existing_delivery is not None
        and event_type not in reconcilable_events
    ):
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
        monitored_pull_request = (
            event_type == "pull_request"
            and str(payload.get("action") or "")
            in {"opened", "reopened", "synchronize", "ready_for_review"}
        )
        monitored_event = (
            monitored_pull_request
            or event_type in {"workflow_run", "deployment", "deployment_status"}
        )
        delivery = existing_delivery
        if delivery is not None:
            if (
                delivery.installation_id != (installation_id or None)
                or (
                    delivery.repository_id is not None
                    and repository is not None
                    and delivery.repository_id != repository.id
                )
            ):
                raise DomainError(
                    "GitHub delivery identity does not match the recorded event",
                    "github_delivery_identity_mismatch",
                    409,
                )
            if (
                monitored_pull_request
                and delivery.status == "processed"
            ):
                return GitHubWebhookResponse(
                    status="accepted",
                    event=event_type,
                    delivery_id=delivery_id,
                    detail="Duplicate delivery was already processed.",
                )
        else:
            delivery = WebhookDelivery(
                id=str(uuid4()),
                provider="github",
                delivery_id=delivery_id,
                event_type=event_type,
                installation_id=installation_id or None,
                workspace_id=connection.workspace_id,
                repository_id=repository.id if repository is not None else None,
                status=(
                    "processing"
                    if repository is not None and monitored_event
                    else "verified"
                    if repository is not None
                    else "ignored"
                ),
                created_at=datetime.now(UTC),
            )
            session.add(delivery)
        session.commit()
        if repository is None:
            return GitHubWebhookResponse(
                status="ignored",
                event=event_type,
                delivery_id=delivery_id,
                detail="Repository is not selected for this workspace.",
            )
        if monitored_pull_request:
            delivery.status = "processing"
            session.commit()
            try:
                pr_data = payload.get("pull_request") or {}
                head_data = pr_data.get("head") or {}
                labels = [
                    str(label.get("name"))
                    for label in pr_data.get("labels", [])
                    if isinstance(label, dict) and label.get("name")
                ]
                detail = analyze_change(
                    session,
                    AnalyzeChangeRequest(
                        title=str(
                            pr_data.get("title") or "Untitled pull request"
                        )[:240],
                        repository=repository.full_name,
                        author=str(
                            (pr_data.get("user") or {}).get("login")
                            or "unknown"
                        )[:160],
                        commit_sha=(
                            str(head_data.get("sha"))[:64]
                            if head_data.get("sha")
                            else None
                        ),
                        branch=(
                            str(head_data.get("ref"))[:160]
                            if head_data.get("ref")
                            else None
                        ),
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
                _github_operational_event(
                    session,
                    event_type=event_type,
                    delivery_id=delivery_id,
                    payload=payload,
                    connection=connection,
                    repository=repository,
                )
                if settings is not None:
                    change_record = session.get(ChangeRecord, detail.id)
                    if change_record is not None:
                        publish_github_change_check_from_webhook(
                            session,
                            connection=connection,
                            repository=repository,
                            change=change_record,
                            request_id=f"github:{delivery_id}",
                            settings=settings,
                        )
                persisted_delivery = session.get(WebhookDelivery, delivery.id)
                if persisted_delivery is not None:
                    persisted_delivery.status = "processed"
                    session.commit()
            except Exception:
                session.rollback()
                failed_delivery = session.get(WebhookDelivery, delivery.id)
                if failed_delivery is not None:
                    failed_delivery.status = "failed"
                    session.commit()
                raise
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
        if event_type in {"workflow_run", "deployment", "deployment_status"}:
            operational_event = _github_operational_event(
                session,
                event_type=event_type,
                delivery_id=delivery_id,
                payload=payload,
                connection=connection,
                repository=repository,
            )
            if event_type in {"deployment", "deployment_status"}:
                upsert_github_deployment(
                    session,
                    payload=payload,
                    workspace_id=connection.workspace_id,
                    repository=repository,
                    operational_event=operational_event,
                    delivery_id=delivery_id,
                )
            persisted_delivery = session.get(WebhookDelivery, delivery.id)
            if persisted_delivery is not None:
                persisted_delivery.status = "processed"
                session.commit()
            duplicate_detail = (
                "Duplicate delivery was reconciled with the event ledger."
                if existing_delivery is not None
                else "Verified provider event was durably recorded."
            )
            return GitHubWebhookResponse(
                status="accepted",
                event=event_type,
                delivery_id=delivery_id,
                detail=duplicate_detail,
            )
        if existing_delivery is not None:
            return GitHubWebhookResponse(
                status="accepted",
                event=event_type,
                delivery_id=delivery_id,
                detail="Duplicate delivery was already recorded.",
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


def derive_telemetry_collector_token(
    master_token: str, workspace_id: str
) -> str:
    """Derive a tenant-bound collector credential from the server secret."""
    signature = hmac.new(
        master_token.encode("utf-8"),
        f"deployguard-telemetry:{workspace_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"dgct_{signature}"


def ingest_telemetry_event(
    session: Session,
    request: TelemetryIngestRequest,
    *,
    master_token: str,
    presented_token: str,
    workspace_id: str | None,
    repository_id: str | None,
    provider_event_id: str | None,
    environment: str,
) -> dict:
    """Persist collector data in an authenticated tenant event ledger."""
    legacy_credential = hmac.compare_digest(presented_token, master_token)
    if legacy_credential:
        if environment.strip().lower() == "production":
            raise DomainError(
                "Use a workspace-scoped telemetry collector credential",
                "workspace_telemetry_credential_required",
                401,
            )
        if workspace_id not in {None, "", LEGACY_WORKSPACE_ID}:
            raise DomainError(
                "Telemetry credential does not match the requested workspace",
                "invalid_telemetry_token",
                401,
            )
        scoped_workspace_id = LEGACY_WORKSPACE_ID
        credential_mode = "legacy_workspace"
    else:
        if not workspace_id:
            raise DomainError(
                "X-DeployGuard-Workspace is required",
                "telemetry_workspace_required",
                400,
            )
        expected = derive_telemetry_collector_token(
            master_token, workspace_id
        )
        if not hmac.compare_digest(presented_token, expected):
            raise DomainError(
                "Invalid telemetry ingestion token",
                "invalid_telemetry_token",
                401,
            )
        scoped_workspace_id = workspace_id
        credential_mode = "workspace_derived"

    if session.get(Workspace, scoped_workspace_id) is None:
        raise DomainError("Workspace not found", "workspace_not_found", 404)

    repository: Repository | None = None
    if repository_id:
        repository = session.scalar(
            select(Repository).where(
                Repository.id == repository_id,
                Repository.workspace_id == scoped_workspace_id,
                Repository.selected.is_(True),
            )
        )
        if repository is None:
            raise DomainError(
                "Repository not found", "repository_not_found", 404
            )

    service = session.scalar(
        select(ServiceCatalogEntry).where(
            ServiceCatalogEntry.workspace_id == scoped_workspace_id,
            or_(
                ServiceCatalogEntry.id == request.service_id,
                ServiceCatalogEntry.slug == request.service_id,
            ),
        )
    )
    if service is None and scoped_workspace_id != LEGACY_WORKSPACE_ID:
        raise DomainError("Service not found", "service_not_found", 404)
    if (
        service is not None
        and repository is not None
        and service.repository_id is not None
        and service.repository_id != repository.id
    ):
        raise DomainError(
            "Telemetry service and repository scopes do not match",
            "telemetry_scope_mismatch",
            422,
        )
    if repository is None and service is not None and service.repository_id:
        repository = session.scalar(
            select(Repository).where(
                Repository.id == service.repository_id,
                Repository.workspace_id == scoped_workspace_id,
                Repository.selected.is_(True),
            )
        )
        if repository is None:
            raise DomainError(
                "Service repository is not selected",
                "repository_not_found",
                404,
            )
    if repository is None and scoped_workspace_id == LEGACY_WORKSPACE_ID:
        repository = session.scalar(
            select(Repository).where(
                Repository.id == LEGACY_REPOSITORY_ID,
                Repository.workspace_id == LEGACY_WORKSPACE_ID,
            )
        )

    event_key = (
        provider_event_id.strip()
        if provider_event_id and provider_event_id.strip()
        else f"telemetry-{uuid4()}"
    )
    if len(event_key) > 160:
        raise DomainError(
            "Telemetry event identity is too long",
            "invalid_telemetry_event_id",
            400,
        )
    timestamp = datetime.now(UTC)
    event = record_trusted_operational_event(
        session,
        scoped_workspace_id,
        OperationalEventCreate(
            provider_event_id=event_key,
            repository_id=repository.id if repository is not None else None,
            service_id=service.id if service is not None else None,
            incident_id=None,
            # Collector-controlled labels stay in provenance. The first-class
            # source namespace is server-owned so a scoped telemetry credential
            # cannot pre-claim GitHub or another trusted adapter's idempotency key.
            source="telemetry",
            event_type=f"telemetry.{request.type}",
            occurred_at=timestamp,
            severity="info",
            summary=request.summary,
            attributes={
                "value": request.value,
                "supports_hypothesis_ids": request.supports_hypothesis_ids,
                "contradicts_hypothesis_ids": (
                    request.contradicts_hypothesis_ids
                ),
                "service_reference": request.service_id,
            },
            provenance={
                "provider": request.source,
                "collector_authenticated": True,
                "credential_mode": credential_mode,
                "workspace_id": scoped_workspace_id,
            },
        ),
        request_id=f"telemetry:{event_key}",
    )
    return {
        "status": "ok",
        "evidence_id": event.id,
        "workspace_id": scoped_workspace_id,
        "repository_id": event.repository_id,
        "service_id": event.service_id,
        "detail": "Telemetry event was accepted into the workspace ledger.",
    }


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


def reset_database(
    session: Session, *, seed_synthetic_data: bool = False
) -> dict[str, str]:
    if not seed_synthetic_data:
        raise DomainError(
            "Database reset is only available in explicit synthetic mode",
            "database_reset_requires_synthetic_mode",
            409,
        )
    from .seed import seed_database

    session.query(FeedbackRecord).delete()
    session.query(IncidentRecord).delete()
    session.query(ChangeRecord).delete()
    session.query(Scenario).delete()
    session.commit()
    seed_database(session)
    return {"status": "ok", "detail": "Database reset and re-seeded successfully."}
