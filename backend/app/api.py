from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .auth.dependencies import get_session
from .errors import DomainError
from .models import Scenario
from .schemas import (
    AnalyzeChangeRequest,
    ChangeDetail,
    DoraMetricsResponse,
    FeedbackRequest,
    GitHubWebhookResponse,
    HealthResponse,
    IncidentDetail,
    LLMSynthesisResponse,
    Overview,
    ScenarioSummary,
    TelemetryIngestRequest,
)
from .services import (
    active_scenario,
    activate_scenario,
    analyze_change,
    export_incident_postmortem,
    get_change,
    get_dora_metrics,
    get_incident,
    get_overview,
    ingest_telemetry_event,
    list_changes,
    list_incidents,
    list_scenarios,
    process_github_webhook,
    reset_database,
    submit_feedback,
    synthesize_llm_hypotheses,
)
from .tenant import (
    TenantScope,
    activate_context_scenario,
    get_legacy_scope,
    require_responder_scope,
)


router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse)
def health(
    session: Session = Depends(get_session),
) -> HealthResponse:
    session.execute(text("SELECT 1"))
    has_synthetic_records = session.scalar(
        select(Scenario.id)
        .where(Scenario.data_mode == "synthetic")
        .limit(1)
    ) is not None
    return HealthResponse(
        status="ok",
        database="ready",
        service="deployguard-ai",
        data_mode="synthetic" if has_synthetic_records else "connected",
    )


@router.get("/overview", response_model=Overview)
def overview(
    session: Session = Depends(get_session),
    scope: TenantScope = Depends(get_legacy_scope),
) -> Overview:
    return get_overview(
        session,
        scenario=active_scenario(
            session,
            workspace_id=scope.workspace_id,
            repository_id=scope.repository_id,
            scenario_id=scope.scenario_id,
        ),
    )


@router.get("/metrics/dora", response_model=DoraMetricsResponse)
def dora_metrics(
    session: Session = Depends(get_session),
    scope: TenantScope = Depends(get_legacy_scope),
) -> DoraMetricsResponse:
    return get_dora_metrics(session, scope.workspace_id)


@router.post("/webhooks/github", response_model=GitHubWebhookResponse)
async def github_webhook(
    request: Request, session: Session = Depends(get_session)
) -> GitHubWebhookResponse:
    settings = request.app.state.settings
    secret = getattr(settings, "github_webhook_secret", "")
    if not secret:
        raise DomainError(
            "GitHub webhook ingestion is not configured",
            "github_webhook_not_configured",
            503,
        )
    event_type = request.headers.get("X-GitHub-Event", "").strip()
    delivery_id = request.headers.get("X-GitHub-Delivery", "").strip()
    if not event_type or len(event_type) > 100:
        raise DomainError(
            "GitHub event header is missing or invalid",
            "invalid_github_event_header",
            400,
        )
    if not delivery_id or len(delivery_id) > 120:
        raise DomainError(
            "GitHub delivery header is missing or invalid",
            "invalid_github_delivery_header",
            400,
        )
    signature = request.headers.get("X-Hub-Signature-256", "")
    raw_body = await request.body()
    if len(raw_body) > settings.github_webhook_max_body_bytes:
        raise DomainError(
            "GitHub webhook body exceeds the configured limit",
            "github_webhook_body_too_large",
            413,
        )
    try:
        payload = await request.json()
    except ValueError as error:
        raise DomainError(
            "GitHub webhook body is not valid JSON",
            "invalid_github_webhook_json",
            400,
        ) from error
    if not isinstance(payload, dict):
        raise DomainError(
            "GitHub webhook body must be a JSON object",
            "invalid_github_webhook_payload",
            400,
        )
    return process_github_webhook(
        session,
        event_type,
        delivery_id,
        payload,
        signature=signature,
        raw_body=raw_body,
        secret=secret,
        allow_synthetic_fallback=(
            settings.environment.lower() != "production"
        ),
        settings=settings,
    )


@router.post("/telemetry/events", status_code=status.HTTP_201_CREATED)
def telemetry_ingest(
    request: Request,
    payload: TelemetryIngestRequest,
    session: Session = Depends(get_session),
) -> dict:
    configured_token = request.app.state.settings.telemetry_ingest_token
    if not configured_token:
        raise DomainError(
            "Telemetry ingestion is not configured",
            "telemetry_ingest_not_configured",
            503,
        )
    authorization = request.headers.get("Authorization", "")
    scheme, separator, presented_token = authorization.partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not presented_token.strip()
    ):
        raise DomainError(
            "Invalid telemetry ingestion token",
            "invalid_telemetry_token",
            401,
        )
    workspace_id = request.headers.get("X-DeployGuard-Workspace", "").strip()
    repository_id = request.headers.get(
        "X-DeployGuard-Repository", ""
    ).strip()
    provider_event_id = request.headers.get(
        "X-DeployGuard-Event-ID", ""
    ).strip()
    if len(workspace_id) > 36 or len(repository_id) > 36:
        raise DomainError(
            "Telemetry scope header is invalid",
            "invalid_telemetry_scope",
            400,
        )
    return ingest_telemetry_event(
        session,
        payload,
        master_token=configured_token,
        presented_token=presented_token.strip(),
        workspace_id=workspace_id or None,
        repository_id=repository_id or None,
        provider_event_id=provider_event_id or None,
        environment=request.app.state.settings.environment,
    )


@router.get("/scenarios", response_model=list[ScenarioSummary])
def scenarios(
    session: Session = Depends(get_session),
    scope: TenantScope = Depends(get_legacy_scope),
) -> list[ScenarioSummary]:
    return list_scenarios(
        session,
        scope.workspace_id,
        scope.scenario_id,
    )


@router.post("/scenarios/{scenario_id}/activate", response_model=Overview)
def scenario_activate(
    scenario_id: str,
    session: Session = Depends(get_session),
    scope: TenantScope = Depends(require_responder_scope),
) -> Overview:
    result = activate_scenario(session, scenario_id, scope.workspace_id)
    scenario = session.scalar(
        select(Scenario).where(
            Scenario.id == scenario_id,
            Scenario.workspace_id == scope.workspace_id,
        )
    )
    if scenario is None:
        raise DomainError("Scenario not found", "scenario_not_found", 404)
    activate_context_scenario(session, scope, scenario)
    return result


@router.get("/changes", response_model=list[ChangeDetail])
def changes(
    session: Session = Depends(get_session),
    scope: TenantScope = Depends(get_legacy_scope),
) -> list[ChangeDetail]:
    return list_changes(session, scope.workspace_id)


@router.get("/changes/{change_id}", response_model=ChangeDetail)
def change(
    change_id: str,
    session: Session = Depends(get_session),
    scope: TenantScope = Depends(get_legacy_scope),
) -> ChangeDetail:
    return get_change(session, change_id, scope.workspace_id)


@router.post(
    "/changes/analyze",
    response_model=ChangeDetail,
    status_code=status.HTTP_201_CREATED,
)
def change_analyze(
    payload: AnalyzeChangeRequest,
    session: Session = Depends(get_session),
    scope: TenantScope = Depends(require_responder_scope),
) -> ChangeDetail:
    return analyze_change(
        session,
        payload,
        workspace_id=scope.workspace_id,
        repository_id=scope.repository_id,
        scenario_id=scope.scenario_id,
    )


@router.get("/incidents", response_model=list[IncidentDetail])
def incidents(
    session: Session = Depends(get_session),
    scope: TenantScope = Depends(get_legacy_scope),
) -> list[IncidentDetail]:
    return list_incidents(session, scope.workspace_id)


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
def incident(
    incident_id: str,
    session: Session = Depends(get_session),
    scope: TenantScope = Depends(get_legacy_scope),
) -> IncidentDetail:
    return get_incident(session, incident_id, scope.workspace_id)


@router.post("/incidents/{incident_id}/synthesize-llm", response_model=LLMSynthesisResponse)
def incident_synthesize_llm(
    incident_id: str,
    session: Session = Depends(get_session),
    scope: TenantScope = Depends(get_legacy_scope),
) -> LLMSynthesisResponse:
    get_incident(session, incident_id, scope.workspace_id)
    return synthesize_llm_hypotheses(session, incident_id)


@router.get("/incidents/{incident_id}/export-markdown")
def incident_export_markdown(
    incident_id: str,
    session: Session = Depends(get_session),
    scope: TenantScope = Depends(get_legacy_scope),
) -> Response:
    content = export_incident_postmortem(
        session, incident_id, scope.workspace_id
    )
    return Response(content=content, media_type="text/markdown")


@router.post(
    "/incidents/{incident_id}/feedback",
    response_model=IncidentDetail,
    status_code=status.HTTP_201_CREATED,
)
def incident_feedback(
    incident_id: str,
    payload: FeedbackRequest,
    session: Session = Depends(get_session),
    scope: TenantScope = Depends(require_responder_scope),
) -> IncidentDetail:
    return submit_feedback(
        session,
        incident_id,
        payload,
        scope.workspace_id,
    )


@router.post("/reset-database")
def reset_db(
    request: Request, session: Session = Depends(get_session)
) -> dict[str, str]:
    if not request.app.state.settings.allow_database_reset:
        raise DomainError(
            "Database reset is disabled",
            "database_reset_disabled",
            403,
        )
    return reset_database(
        session,
        seed_synthetic_data=request.app.state.settings.seed_synthetic_data,
    )
