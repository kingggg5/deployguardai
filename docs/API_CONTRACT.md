# API contract

DeployGuard exposes typed JSON under `/api/v1`. The generated OpenAPI document
at `/openapi.json` and interactive UI at `/docs` are the field-level source of
truth. This document records the stable behavioral and authorization contract.

## Authentication and tenant scope

- Production uses OIDC bearer tokens validated by issuer, audience, signature,
  expiry, issued-at, and verified email.
- Development sessions are available only outside production.
- Workspace resources require membership. Roles are ordered `viewer`,
  `responder`, `admin`, `owner`.
- Resource IDs from another workspace return `404` or `403`; they are never
  resolved without tenant scope.
- GitHub webhooks use raw-body HMAC verification. Telemetry uses a
  workspace-derived collector bearer and `X-DeployGuard-Workspace`.

## Endpoint inventory

All paths below are relative to `/api/v1`.

### Runtime and identity

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `/health/live`, `/health`, `/health/ready` | Public probes |
| `GET` | `/capabilities` | Public safe capability summary |
| `POST` | `/auth/development-session` | Non-production only |
| `GET` | `/auth/me`, `/me/context` | Authenticated |

### Workspaces and providers

| Method | Path | Minimum role |
| --- | --- | --- |
| `GET`, `POST` | `/workspaces` | Authenticated |
| `GET`, `POST` | `/workspaces/{workspace_id}/repositories` | Viewer / Admin |
| `GET` | `/workspaces/{workspace_id}/members` | Viewer |
| `GET`, `POST`, `DELETE` | `/workspaces/{workspace_id}/invitations...` | Admin |
| `POST` | `/invitations/accept` | Authenticated |
| `GET` | `/workspaces/{workspace_id}/audit-events` | Admin |
| `GET` | `/workspaces/{workspace_id}/connectors` | Viewer |
| `POST`, `GET`, `DELETE` | `/workspaces/{workspace_id}/providers/github...` | Admin |
| `GET`, `POST` | `/workspaces/{workspace_id}/providers/github/repositories...` | Viewer / Admin |
| `POST` | `/workspaces/{workspace_id}/repositories/{repository_id}/changes/{change_id}/github-check` | Responder |

### Investigation and analysis

| Method | Path | Minimum role | Purpose |
| --- | --- | --- | --- |
| `GET` | `/overview`, `/scenarios`, `/changes`, `/incidents` | Viewer | Read current evidence context |
| `POST` | `/scenarios/{scenario_id}/activate` | Responder | Activate a scenario context |
| `GET` | `/changes/{change_id}` | Viewer | Read risk and blast-radius ledger |
| `POST` | `/changes/analyze` | Responder | Persist deterministic analysis |
| `GET` | `/incidents/{incident_id}` | Viewer | Read timeline, evidence, hypotheses, and feedback |
| `POST` | `/incidents/{incident_id}/synthesize` | Viewer | Deterministic citation-gated explanation; no external model |
| `GET` | `/incidents/{incident_id}/export-markdown` | Viewer | Render current postmortem Markdown |
| `POST` | `/incidents/{incident_id}/feedback` | Responder | Record verdict and optional structured verification |
| `POST` | `/incidents/{incident_id}/postmortem-snapshots` | Responder | Create immutable connected-incident snapshot |
| `GET` | `/incidents/{incident_id}/dataset-readiness?purpose=...` | Viewer | Evaluate dataset-promotion gates |
| `POST` | `/incidents/{incident_id}/dataset-consent` | Admin | Append a purpose-specific consent decision |
| `GET` | `/metrics/dora` | Viewer | Workspace DORA-style aggregate |

`/synthesize-llm` is a deprecated compatibility alias for `/synthesize`; it
does not call a model.

### Operations

| Method | Path | Minimum role |
| --- | --- | --- |
| `GET`, `POST` | `/workspaces/{workspace_id}/services` | Viewer / Admin |
| `GET`, `PATCH` | `/services/{service_id}` | Viewer / Admin |
| `GET` | `/workspaces/{workspace_id}/risk-policy` | Viewer |
| `GET` | `/workspaces/{workspace_id}/deployments`, `/deployments/{deployment_id}` | Viewer |
| `GET`, `POST` | `/workspaces/{workspace_id}/events` | Viewer / Responder |
| `PATCH` | `/incidents/{incident_id}/lifecycle` | Responder |
| `POST` | `/incidents/{incident_id}/notes` | Responder |
| `GET`, `PATCH` | `/notifications...` | Recipient only |
| `GET` | `/workspaces/{workspace_id}/jobs/attention` | Responder |
| `POST` | `/workspaces/{workspace_id}/jobs/{job_id}/replay` | Admin |

### Machine ingestion and local operation

| Method | Path | Authentication |
| --- | --- | --- |
| `POST` | `/webhooks/github` | Signed GitHub webhook |
| `POST` | `/telemetry/events` | Workspace-derived telemetry bearer |
| `POST` | `/reset-database` | Explicit synthetic-mode flag only |

The telemetry endpoint accepts DeployGuard's normalized metric/log/trace/alert
contract. It is not a native OTLP receiver.

## Human verdict contract

```json
{
  "hypothesis_id": "hyp-payment-timeout",
  "verdict": "confirmed",
  "note": "Trace replay reproduced the timeout before retry fan-out.",
  "verification_outcome": {
    "result": "reproduced",
    "method": "trace_replay",
    "summary": "The prior timeout removed the retry fan-out in replay.",
    "evidence_ids": ["ev-payment-trace", "ev-timeout-config"]
  }
}
```

`verification_outcome` remains optional for backward compatibility, but a
structured outcome is required before dataset promotion. Actor provenance is
never accepted from the request. The server copies the authenticated user's ID,
display name, and authentication provider into the feedback record.

## Dataset governance contracts

Snapshot creation has no client-authored content. The server renders the current
postmortem, hashes it with SHA-256, stores engine/schema versions and actor
provenance, and returns the existing row when the content is unchanged.

Consent request:

```json
{
  "purpose": "evaluation",
  "decision": "approved",
  "terms_version": "deployguard-dataset-terms-v1",
  "reason": "Approved for internal evaluation review.",
  "attestations": [
    "workspace_authorized",
    "secrets_reviewed",
    "privacy_reviewed",
    "license_reviewed"
  ]
}
```

The server binds the decision to the latest immutable snapshot. Consent
decisions are append-only and store the exact incident, snapshot, purpose, terms
version, actor, and timestamp. Revocation creates another record.

Readiness response contains six ordered requirements, the latest snapshot and
consent summaries, and one of `not_applicable`, `blocked`, or
`ready_for_review`. `connected_exporter_enabled` is always `false` in the
current contract.

## Core response provenance

`ChangeDetail` and `IncidentDetail` include `analysis_schema_version`,
`engine_version`, `scoring_policy_version`, and `graph_version`. Values are
persisted with the analysis snapshot, not calculated during reads. Legacy rows
return `legacy-unversioned` instead of claiming current-engine provenance.

Incident `feedback[]` includes:

```text
id, hypothesis_id, verdict, note, created_at
actor: user_id, display_name, auth_provider | null
verification_outcome: result, method, summary, evidence_ids[] | null
```

## Errors

Domain errors use:

```json
{
  "detail": "Human-readable message",
  "code": "stable_machine_code"
}
```

| Status | Meaning |
| ---: | --- |
| `400` | Invalid token, state, or domain input |
| `401` | Missing or invalid authentication |
| `403` | Authenticated but insufficient role |
| `404` | Missing or out-of-tenant resource |
| `409` | Lifecycle, idempotency, provider, or version conflict |
| `413` | Request body exceeds the configured limit |
| `422` | Typed request validation failed |
| `503` | Credential-gated provider is unavailable |
