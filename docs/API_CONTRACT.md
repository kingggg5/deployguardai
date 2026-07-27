# MVP API Contract

Base URL: `/api/v1`

All timestamps are ISO 8601 UTC strings. Scores use `0–100`; confidence and quality use `0–1`. Seed records include `data_mode: "synthetic"`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness and database readiness |
| `GET` | `/overview` | Active scenario, summary counts, current change, and current incident |
| `GET` | `/scenarios` | List reproducible demo scenarios |
| `POST` | `/scenarios/{scenario_id}/activate` | Select the active scenario and return its overview |
| `GET` | `/changes` | List analyzed changes |
| `GET` | `/changes/{change_id}` | Change, risk ledger, and blast-radius graph |
| `POST` | `/changes/analyze` | Analyze and persist a GitHub-style change |
| `GET` | `/incidents` | List incidents |
| `GET` | `/incidents/{incident_id}` | Incident, timeline, evidence, hypotheses, and feedback |
| `POST` | `/incidents/{incident_id}/feedback` | Record a human verdict for a hypothesis |

## Core response shapes

```text
Overview
  generated_at: timestamp
  data_mode: "synthetic" | "connected"
  active_scenario_id: string
  stats:
    open_incidents: integer
    high_risk_changes: integer
    services_monitored: integer
    evidence_quality: number
  active_change: ChangeDetail
  active_incident: IncidentDetail
```

```text
ChangeDetail
  id, title, repository, author, commit_sha, branch, created_at
  deployment_status, deployment_environment
  changed_services: string[]
  files_changed, lines_added, lines_deleted
  flags: string[]
  risk:
    overall_score: integer
    level: "low" | "moderate" | "high" | "critical"
    data_quality: number
    dimensions:
      - key, label, score, weight, reason, evidence_ids[]
    recommendations: string[]
  blast_radius:
    nodes:
      - id, label, kind, team, tier, health, impact_score, hop_distance, evidence_ids[]
    edges:
      - source, target, relation, confidence, active
```

```text
IncidentDetail
  id, title, severity, status, started_at, resolved_at
  affected_services: string[]
  correlated_change_id, summary
  timeline:
    - id, timestamp, type, title, detail, service_id
  evidence:
    - id, type, source, timestamp, summary, value, quality,
      service_id, supports[], contradicts[]
  hypotheses:
    - id, rank, cause_service, cause, confidence, score,
      evidence_ids[], counter_evidence_ids[], reasoning,
      next_step, status
  feedback:
    - verdict, hypothesis_id, note, submitted_at
```

## Analyze change request

The request is idempotent for the same canonical payload. It persists and returns
the analysis but does not replace the active scenario change or its correlated
incident; only the scenario activation endpoint changes the dashboard context.

```json
{
  "title": "Tighten checkout timeout and retry policy",
  "repository": "acme/checkout-platform",
  "author": "narin",
  "files_changed": 11,
  "lines_added": 286,
  "lines_deleted": 74,
  "changed_services": ["checkout-api", "payment-adapter"],
  "flags": ["config-change", "retry-policy"],
  "test_coverage": 0.72,
  "rollback_ready": true,
  "observability_score": 0.84,
  "previous_failures": 1
}
```

## Feedback request

```json
{
  "hypothesis_id": "hyp-payment-timeout",
  "verdict": "confirmed",
  "note": "Trace replay confirmed timeout before the retry fan-out."
}
```

## Error envelope

FastAPI validation errors retain the standard `detail` collection. Domain errors return:

```json
{
  "detail": "Scenario not found",
  "code": "scenario_not_found"
}
```
