from collections.abc import Generator

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

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


router = APIRouter(prefix="/api/v1")


def get_session(request: Request) -> Generator[Session, None, None]:
    yield from request.app.state.database.session()


@router.get("/health", response_model=HealthResponse)
def health(session: Session = Depends(get_session)) -> HealthResponse:
    session.execute(text("SELECT 1"))
    return HealthResponse(
        status="ok",
        database="ready",
        service="deployguard-ai",
        data_mode="synthetic",
    )


@router.get("/overview", response_model=Overview)
def overview(session: Session = Depends(get_session)) -> Overview:
    return get_overview(session)


@router.get("/metrics/dora", response_model=DoraMetricsResponse)
def dora_metrics(session: Session = Depends(get_session)) -> DoraMetricsResponse:
    return get_dora_metrics(session)


@router.post("/webhooks/github", response_model=GitHubWebhookResponse)
async def github_webhook(
    request: Request, session: Session = Depends(get_session)
) -> GitHubWebhookResponse:
    event_type = request.headers.get("X-GitHub-Event", "pull_request")
    delivery_id = request.headers.get("X-GitHub-Delivery", "del-12345")
    signature = request.headers.get("X-Hub-Signature-256", "")
    raw_body = await request.body()
    payload = await request.json()
    secret = getattr(request.app.state.settings, "github_webhook_secret", "")
    return process_github_webhook(
        session,
        event_type,
        delivery_id,
        payload,
        signature=signature,
        raw_body=raw_body,
        secret=secret,
    )


@router.post("/telemetry/events", status_code=status.HTTP_201_CREATED)
def telemetry_ingest(
    payload: TelemetryIngestRequest, session: Session = Depends(get_session)
) -> dict:
    return ingest_telemetry_event(session, payload)


@router.get("/scenarios", response_model=list[ScenarioSummary])
def scenarios(session: Session = Depends(get_session)) -> list[ScenarioSummary]:
    return list_scenarios(session)


@router.post("/scenarios/{scenario_id}/activate", response_model=Overview)
def scenario_activate(
    scenario_id: str, session: Session = Depends(get_session)
) -> Overview:
    return activate_scenario(session, scenario_id)


@router.get("/changes", response_model=list[ChangeDetail])
def changes(session: Session = Depends(get_session)) -> list[ChangeDetail]:
    return list_changes(session)


@router.get("/changes/{change_id}", response_model=ChangeDetail)
def change(
    change_id: str, session: Session = Depends(get_session)
) -> ChangeDetail:
    return get_change(session, change_id)


@router.post(
    "/changes/analyze",
    response_model=ChangeDetail,
    status_code=status.HTTP_201_CREATED,
)
def change_analyze(
    payload: AnalyzeChangeRequest, session: Session = Depends(get_session)
) -> ChangeDetail:
    return analyze_change(session, payload)


@router.get("/incidents", response_model=list[IncidentDetail])
def incidents(session: Session = Depends(get_session)) -> list[IncidentDetail]:
    return list_incidents(session)


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
def incident(
    incident_id: str, session: Session = Depends(get_session)
) -> IncidentDetail:
    return get_incident(session, incident_id)


@router.post("/incidents/{incident_id}/synthesize-llm", response_model=LLMSynthesisResponse)
def incident_synthesize_llm(
    incident_id: str, session: Session = Depends(get_session)
) -> LLMSynthesisResponse:
    return synthesize_llm_hypotheses(session, incident_id)


@router.get("/incidents/{incident_id}/export-markdown")
def incident_export_markdown(
    incident_id: str, session: Session = Depends(get_session)
) -> Response:
    content = export_incident_postmortem(session, incident_id)
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
) -> IncidentDetail:
    return submit_feedback(session, incident_id, payload)


@router.post("/reset-database")
def reset_db(session: Session = Depends(get_session)) -> dict[str, str]:
    return reset_database(session)

