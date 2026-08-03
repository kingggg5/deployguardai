# API contract

Base URL คือ `/api/v1` ทุก timestamp ใช้ ISO 8601 UTC, score อยู่ในช่วง
`0–100` และ confidence/quality อยู่ในช่วง `0–1`

OpenAPI ที่ FastAPI สร้างจาก Pydantic schemas เป็น contract ระดับ field
เอกสารนี้อธิบาย semantics, authorization และ side effects ที่ schema เพียงอย่าง
เดียวบอกไม่ได้

## Authentication modes

| Mode | ใช้เมื่อ | Contract |
|---|---|---|
| Development bearer | `AUTH_PROVIDER=development` และไม่ใช่ production | ขอ opaque token จาก `/auth/development-session`; token เก็บแบบ SHA-256 digest |
| Local synthetic fallback | Investigation routes บางส่วนใน development | ถ้าไม่มี bearer จะใช้ configured development user เพื่อรักษา demo flow; production ปิด |
| OIDC bearer | `AUTH_PROVIDER=oidc` | API ตรวจ issuer, audience, expiry, signature และ verified email ผ่าน JWKS |
| GitHub webhook | `/webhooks/github` | ตรวจ `X-Hub-Signature-256` บน raw body และ dedupe ด้วย `X-GitHub-Delivery` |
| Telemetry collector credential | `/telemetry/events` | Bearer `dgct_...` ที่ derive ด้วย HMAC จาก credential root + workspace ID; ไม่ใช่ human session |

`GET /capabilities` ไม่ต้อง authenticate เพื่อให้ frontend เลือก login/provider
flow ตาม runtime configuration Workspace-management/operations routes ต้องมี
bearer เสมอ ส่วน legacy synthetic investigation routes ยอม local fallback เฉพาะ
non-production และยัง resolve ผ่าน tenant context

## Role levels

```text
viewer < responder < admin < owner
```

| Action | Minimum role |
|---|---|
| อ่าน workspace, repositories, services, risk policy, events และ members | `viewer` |
| วิเคราะห์ change, activate scenario, เพิ่ม event/note และเปลี่ยน incident lifecycle | `responder` |
| จัดการ repositories, GitHub connection, invitations, services, risk policy และ audit log | `admin` |
| เชิญสมาชิก role `admin` | `owner` |

เมื่อไม่มี membership API คืน `404 workspace_not_found` เพื่อไม่เปิดเผย
resource ของ tenant อื่น เมื่อมี membership แต่ role ไม่ถึงจะคืน `403 forbidden`

## Endpoint inventory

### Connected-mode guardrails

`GET /capabilities` exposes `synthetic_data`, the explicit server-side switch
for bundled evaluation data. When it is `false`, fresh runtimes remain empty
until a real provider is connected and
`POST /workspaces/{workspace_id}/repositories` returns
`409 synthetic_repository_disabled` instead of creating a fixture.

### Runtime และ capability

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/health/live` | Public | Lightweight liveness probe without database access |
| `GET` | `/health/ready` | Public | Database connectivity และ service status |
| `GET` | `/health` | Public | Backward-compatible readiness alias |
| `GET` | `/capabilities` | Public | Runtime auth/provider availability |

### Identity, context และ workspace

| Method | Path | Role | Purpose |
|---|---|---|---|
| `POST` | `/auth/development-session` | Local only | ออก development bearer token |
| `GET` | `/auth/me` | Authenticated | Principal ปัจจุบัน |
| `GET` | `/me/context` | Authenticated | Workspace/repository/scenario selection |
| `PUT` | `/me/context` | Authenticated | เปลี่ยน selection หลังตรวจ membership |
| `GET` | `/workspaces` | Authenticated | Workspace ที่ผู้ใช้เป็นสมาชิก |
| `POST` | `/workspaces` | Authenticated | สร้าง workspace และ owner membership |
| `GET` | `/workspaces/{workspace_id}/members` | Viewer | รายชื่อสมาชิก |
| `GET` | `/workspaces/{workspace_id}/audit-events` | Admin | Audit events ล่าสุด; `limit=1..200` |

### Repository และ GitHub App

| Method | Path | Role | Purpose |
|---|---|---|---|
| `GET` | `/workspaces/{workspace_id}/repositories` | Viewer | รายการ repository ใน workspace |
| `POST` | `/workspaces/{workspace_id}/repositories` | Admin | เพิ่ม synthetic development repository เฉพาะเมื่อ `synthetic_data=true`; otherwise returns `409 synthetic_repository_disabled` |
| `GET` | `/workspaces/{workspace_id}/repositories/{repository_id}/changes` | Viewer | Connected changes ของ repository |
| `POST` | `/workspaces/{workspace_id}/repositories/{repository_id}/changes/{change_id}/github-check` | Responder | Publish neutral/success GitHub Check Run เมื่อ feature flag เปิด |
| `POST` | `/workspaces/{workspace_id}/providers/github/install` | Admin | สร้าง single-use installation state |
| `GET` | `/providers/github/callback` | State token | รับ GitHub installation callback |
| `GET` | `/workspaces/{workspace_id}/providers/github` | Viewer | Connection health |
| `GET` | `/workspaces/{workspace_id}/providers/github/repositories` | Viewer | Repository ที่ installation เข้าถึงได้ |
| `POST` | `/workspaces/{workspace_id}/providers/github/repositories/sync` | Admin | Import/select repository |
| `DELETE` | `/workspaces/{workspace_id}/providers/github` | Admin | Revoke local connection state |
| `POST` | `/webhooks/github` | Signed webhook | Verify, dedupe และ normalize event |
| `GET` | `/workspaces/{workspace_id}/connectors` | Viewer | Read-only connector health without provider credentials |
| `GET` | `/workspaces/{workspace_id}/deployments` | Viewer | Canonical deployments with repository/environment/status filters |
| `GET` | `/deployments/{deployment_id}` | Viewer | Canonical deployment detail after tenant membership check |

GitHub installation token ถูก mint ฝั่ง server และไม่คืนให้ browser Install
state เก็บแบบ digest, หมดอายุ และใช้ได้ครั้งเดียว ใน production
installation ที่ map workspace ไม่ได้จะไม่ใช้ synthetic fallback

GitHub Check publishing ปิดโดย default ผ่าน `GITHUB_CHECKS_ENABLED=false`
เมื่อเปิดแล้ว App ต้องมี `Checks: write`, repository/change ต้องเป็น connected
resource ใน workspace เดียวกัน และผลที่ publish เป็น decision-support
`neutral|success` เท่านั้น ไม่ deploy, rollback หรือแก้ infrastructure
Signed PR webhook ที่ผ่านเงื่อนไขจะ publish อัตโนมัติ Publication state ถูกเก็บ
แยกด้วย unique `(repository_id, head_sha)`, stable `external_id`, provider Check
ID, attempt count, retry status/error และ next retry time Transient failure ทำให้
webhook delivery เป็น `failed` เพื่อให้ signed retry ทำงานต่อได้ การ publish ซ้ำ
จะ recover/PATCH Check เดิมแทนการสร้าง duplicate Responder ใช้ endpoint ข้างต้น
เพื่อ publish/retry โดยตรงได้

### Invitation

| Method | Path | Role | Purpose |
|---|---|---|---|
| `GET` | `/workspaces/{workspace_id}/invitations` | Admin | รายการ invitation โดยไม่คืน claim token |
| `POST` | `/workspaces/{workspace_id}/invitations` | Admin | สร้างและส่ง invitation |
| `DELETE` | `/workspaces/{workspace_id}/invitations/{invitation_id}` | Admin | Revoke invitation ที่ pending |
| `POST` | `/invitations/accept` | Authenticated | Accept token ที่ email ตรงกับ principal |

Development outbox คืน `claim_token` ครั้งเดียวพร้อม `Cache-Control: no-store`
SMTP mode คืนเฉพาะ delivery status และไม่ expose token

### Service catalog และ risk policy

| Method | Path | Role | Purpose |
|---|---|---|---|
| `GET` | `/workspaces/{workspace_id}/services` | Viewer | รายการ service และ dependencies |
| `POST` | `/workspaces/{workspace_id}/services` | Admin | สร้าง service ใน workspace |
| `GET` | `/services/{service_id}` | Viewer | Service detail หลัง resolve owning workspace |
| `PATCH` | `/services/{service_id}` | Admin | แก้ metadata/dependencies |
| `GET` | `/workspaces/{workspace_id}/risk-policy` | Viewer | Policy ปัจจุบันของ workspace |
| `PUT` | `/workspaces/{workspace_id}/risk-policy` | Admin | เปลี่ยน thresholds/safety requirements แบบ versioned |

Service slug unique ภายใน workspace Dependency ต้องอ้าง service ใน workspace
เดียวกัน ห้าม self-reference และห้ามสร้าง cycle

Service enums:

```text
tier      = tier_1 | tier_2 | tier_3 | tier_4
lifecycle = active | deprecated | experimental
```

`runbook_url` ถ้ามีต้องเป็น HTTP/HTTPS และ dependency/tag list ถูก dedupe โดย
รักษาลำดับแรก

Risk-policy update ต้องส่ง version ถัดจาก current version เท่านั้น และต้องรักษา
invariant `warn_threshold < block_threshold` Field ปัจจุบันคือ `enabled`,
warn/block thresholds, `require_tests`, `require_rollback` และ
`max_blast_radius` Update ใช้ compare-and-swap ที่
`workspace_id + current_version`; concurrent/stale writer คืน
`409 risk_policy_version_conflict`

### Operational events, incidents และ notification

| Method | Path | Role | Purpose |
|---|---|---|---|
| `POST` | `/workspaces/{workspace_id}/events` | Responder | บันทึก normalized durable event |
| `GET` | `/workspaces/{workspace_id}/events` | Viewer | อ่าน event ล่าสุดของ workspace |
| `PATCH` | `/incidents/{incident_id}/lifecycle` | Responder | Transition status/assignee |
| `POST` | `/incidents/{incident_id}/notes` | Responder | เพิ่ม durable responder note |
| `GET` | `/notifications` | Authenticated | Notification ของ principal ปัจจุบัน |
| `PATCH` | `/notifications/{notification_id}/read` | Authenticated | Mark notification ของ principal เป็น read |

Foreign IDs ใน event เช่น repository, service และ incident ต้องอยู่ใน
workspace เดียวกัน Event dedupe key คือ:

```text
(workspace_id, source, provider_event_id)
```

การส่ง event identity เดิมซ้ำด้วย canonical payload และ origin เดิมเป็น
idempotent replay: API คืน representation ของ row เดิมด้วย `201` เช่นเดียวกับ
initial create โดยไม่สร้าง row, audit event หรือ notification เพิ่ม ถ้า identity
เดิมแต่ payload หรือ origin ต่างกัน API คืน
`409 operational_event_idempotency_conflict` Source ถูก normalize เป็น lowercase
ก่อนสร้าง dedupe key `ingestion_status` เป็น `accepted` หรือ `correlated`

Event contract จำกัด:

- severity: `debug|info|warning|error|critical`
- `occurred_at` ต้องมี timezone, ไม่เกิน 5 นาทีในอนาคต และไม่เก่ากว่า 366 วัน
- `attributes` และ `provenance` แต่ละ field ไม่เกิน 100 top-level keys และ
  serialized JSON ไม่เกิน 64 KiB
- list filters: source, event type, severity, repository, service,
  ingestion status และ occurred-at range
- list `limit` อยู่ในช่วง 1–500

Deployment webhooks (`deployment` และ `deployment_status`) upsert ด้วย
`(workspace_id, provider, provider_deployment_id)`, link an exact repository +
commit SHA change when available, and update legacy deployment fields for DORA
compatibility. `workflow_run` remains an operational event and is not treated as
a deployment. Connected scenarios may return `active_incident = null` until a
real incident is correlated; the API does not fabricate an incident record.

Member endpoint discard client-supplied provenance ทั้ง object เพื่อ compatibility
แล้วสร้าง provenance ใหม่ฝั่ง Server ส่วน trusted adapter เก็บ provider
provenance ได้และเขียนทับ reserved `provenance._ingestion`:

```text
channel = member_api | trusted_internal
actor_user_id
request_id
```

`trusted_internal` ใช้เฉพาะ adapter ที่ map provider installation/repository เข้า
tenant แล้ว ไม่ใช่ค่าที่ member API เลือกเองได้ Source namespaces `github`,
`telemetry`, `otel`, `otlp` และ `opentelemetry` สงวนไว้จาก member endpoint

Incident lifecycle เป็น state machine และ `resolved` เป็น terminal state
Assignee ต้องเป็นสมาชิก workspace เดียวกัน Notes เป็น typed append-only entries
ใน incident timeline JSON และไม่ rewrite evidence หรือ feedback เดิม
Notification เป็น in-app และผูกทั้ง workspace กับ recipient; endpoint ไม่ส่ง
arbitrary outbound webhook

Lifecycle เดินหน้าเท่านั้น:

```text
open → acknowledged → investigating → mitigated → resolved
```

สามารถข้าม state ไปข้างหน้าได้ แต่ย้อนกลับหรือแก้ incident ที่ resolved ไม่ได้
Severity ใช้ `sev1|sev2|sev3|sev4` Note ยาวสูงสุด 4,000 ตัวอักษร
Notification list filter ได้ด้วย `workspace_id`, `unread_only` และ `limit=1..500`
การห้ามแก้ incident ที่ resolved ใช้กับ lifecycle PATCH; responder ยัง append
post-resolution investigation/postmortem note ได้

### Investigation และ analysis

| Method | Path | Role | Purpose |
|---|---|---|---|
| `GET` | `/overview` | Viewer | Summary ของ tenant context ปัจจุบัน |
| `GET` | `/scenarios` | Viewer | Scenario ที่อยู่ใน context |
| `POST` | `/scenarios/{scenario_id}/activate` | Responder | เปลี่ยน active scenario |
| `GET` | `/changes` | Viewer | รายการ analyzed changes |
| `GET` | `/changes/{change_id}` | Viewer | Risk ledger และ blast radius |
| `POST` | `/changes/analyze` | Responder | คำนวณและ persist deterministic analysis |
| `GET` | `/incidents` | Viewer | รายการ incidents |
| `GET` | `/incidents/{incident_id}` | Viewer | Timeline, evidence, hypotheses และ feedback |
| `POST` | `/incidents/{incident_id}/feedback` | Responder | Human verdict ต่อ hypothesis |
| `GET` | `/incidents/{incident_id}/export-markdown` | Viewer | Postmortem markdown |
| `POST` | `/incidents/{incident_id}/synthesize-llm` | Viewer | Reserved; ปัจจุบันคืน `501` |
| `GET` | `/metrics/dora` | Viewer | DORA-style aggregate ของ workspace |

`POST /changes/analyze` persist snapshot ใหม่ แต่ไม่เปลี่ยน active scenario
context การ activate scenario เท่านั้นที่เปลี่ยน dashboard context

### Ingestion และ development-only operation

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/telemetry/events` | Workspace-derived telemetry bearer | รับ normalized metric/log/trace/alert record เข้า operational-event ledger |
| `POST` | `/reset-database` | Config flag | Reset synthetic database; disabled by default |

`/telemetry/events` ไม่ใช่ OTLP receiver `TELEMETRY_INGEST_TOKEN` เป็น credential
root ฝั่ง server แต่ละ Collector ต้องใช้
`HMAC-SHA256(root, "deployguard-telemetry:{workspace_id}")` ในรูป `dgct_...`
พร้อม `X-DeployGuard-Workspace` และ stable `X-DeployGuard-Event-ID` อาจส่ง
`X-DeployGuard-Repository` เพื่อเพิ่ม scope ได้ Production ปฏิเสธ raw root token
ส่วน non-production ยอม raw root token เฉพาะ legacy synthetic workspace

## Core response shapes

```text
Overview
  generated_at
  data_mode: "synthetic" | "connected"
  active_scenario_id
  stats
  active_change: ChangeDetail
  active_incident: IncidentDetail
```

```text
ChangeDetail
  id, workspace_id, repository_id, repository, commit_sha, branch, data_mode
  analysis_schema_version, engine_version, scoring_policy_version, graph_version
  deployment_status, deployment_environment
  changed_services[]
  risk:
    overall_score, level, data_quality
    dimensions[]: key, score, weight, reason, evidence_ids[]
    recommendations[]
  blast_radius:
    nodes[]: id, kind, team, tier, impact_score, hop_distance, evidence_ids[]
    edges[]: source, target, relation, confidence, active
```

```text
IncidentDetail
  id, scenario_id, data_mode
  analysis_schema_version, engine_version, scoring_policy_version, graph_version
  severity, status, assignee_user_id, started_at, resolved_at
  timeline[], evidence[], hypotheses[], feedback[]
```

Version fields are persisted snapshot provenance, not values calculated at read
time. A change currently reports `risk-weighted-v1` and
`dependency-bfs-v1`; an incident reports `evidence-ranker-v1` and
`not-applicable` because hypothesis ranking does not traverse the service graph.
Rows created before revision `0008` report `legacy-unversioned` rather than
claiming unverifiable current-engine provenance. These fields are response-only;
clients cannot choose the engine or scoring policy in an analysis request.

Responder note ถูก append เป็น typed `TimelineEvent(type="incident_note")` และ
คืนจาก `POST /notes`

```text
ServiceResponse
  id, workspace_id, name, slug, description
  tier, lifecycle, owner_team, repository_id
  dependencies[], runbook_url, tags[]
  created_at, updated_at

RiskPolicyResponse
  enabled, warn_threshold, block_threshold
  require_tests, require_rollback, max_blast_radius
  version, created_at, updated_at

OperationalEventResponse
  id, provider_event_id, workspace_id
  repository_id, service_id, incident_id
  source, event_type, occurred_at, severity, summary
  attributes{}, provenance{}
  ingestion_status, ingested_at

IncidentLifecycleResponse
  incident_id, workspace_id, status, severity
  assignee_user_id, resolved_at, timeline[]

NotificationResponse
  id, workspace_id, user_id, kind
  title, message, resource_type, resource_id
  read_at, created_at
```

## Representative requests

### Analyze change

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

### Human feedback

```json
{
  "hypothesis_id": "hyp-payment-timeout",
  "verdict": "confirmed",
  "note": "Trace replay confirmed timeout before the retry fan-out."
}
```

## Status and error semantics

| Status | Meaning |
|---:|---|
| `200` | Read/update สำเร็จ |
| `201` | สร้าง resource สำเร็จ |
| `303` | GitHub callback กลับไป frontend |
| `400` | Token/state/input domain invalid |
| `401` | ไม่มี credential หรือ credential ใช้ไม่ได้ |
| `403` | Authenticated แล้วแต่ role ไม่พอ |
| `404` | Resource ไม่มีอยู่หรืออยู่นอก tenant |
| `409` | Version, lifecycle, provider หรือ state conflict |
| `413` | GitHub webhook body เกิน configured limit |
| `422` | Pydantic/FastAPI validation error |
| `501` | LLM capability ยังไม่ implement |
| `503` | Credential-gated provider ยังไม่ configured |

Domain error:

```json
{
  "detail": "Workspace not found",
  "code": "workspace_not_found"
}
```

Validation errors ใช้ FastAPI `detail[]` ตามมาตรฐาน
