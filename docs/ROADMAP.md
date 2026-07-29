# DeployGuard AI roadmap

Roadmap นี้เรียงตาม dependency และความเสี่ยง ไม่ใช้เลขสัปดาห์ เพราะเลขสัปดาห์
ไม่ได้เป็นหลักฐานว่า capability พร้อมใช้งาน

## สถานะ

- ✅ **Implemented** — มี runtime path และ automated test coverage ใน repository
- 🟡 **Credential/environment gated** — code มีแล้ว แต่ต้อง configure external
  provider หรือยังต้อง verify บน reference production environment
- ⬜ **Planned** — ยังไม่มี complete runtime path
- ⏸ **Deferred** — จงใจยังไม่ทำจนกว่า prerequisite gate ผ่าน

## Capability map

| Capability | Status | Current truth |
|---|---:|---|
| Angular/FastAPI application shell | ✅ | Typed API client, responsive workspace/investigation UI |
| Deterministic risk + blast radius | ✅ | Explicit dimensions, bounded cycle-safe traversal |
| Incident evidence + RCA + feedback | ✅ | Top hypotheses, counter-evidence และ persistent verdict |
| Workspace, invitation และ RBAC | ✅ | Viewer/responder/admin/owner และ tenant-scoped context |
| OIDC production authentication | 🟡 | JWT/JWKS verifier มีแล้ว; ต้อง configure issuer |
| Alembic migrations | ✅ | Upgrade ถึง head ตอน startup และ guarded legacy bootstrap |
| GitHub App connected repositories | 🟡 | Install/sync/webhook path มีแล้ว; ต้อง configure GitHub App |
| GitHub Check Run feedback | 🟡 | Durable create-or-PATCH/retry path มีแล้ว; ต้องเปิด flag, Checks write และ verify กับ GitHub จริง |
| SMTP invitation delivery | 🟡 | SMTP path มีแล้ว; local ใช้ development outbox |
| Normalized telemetry ingestion | 🟡 | Workspace-derived collector bearer และ tenant ledger มีแล้ว; ไม่ใช่ native OTLP receiver |
| Service catalog | ✅ | Validated dependency DAG ถูก overlay เข้า deterministic risk/blast-radius analysis |
| Workspace risk policy | ✅ | Versioned thresholds และ safety requirements |
| Durable operational events | ✅ | Tenant validation, server-owned provenance และ conflict-safe idempotency |
| Incident lifecycle + notes | ✅ | Role-gated transitions, assignee และ append-only notes |
| In-app notifications | ✅ | Recipient-scoped list/read state |
| PostgreSQL production verification | 🟡 | Driver/config/migrations รองรับ; reference integration gate ยังเปิด |
| Retention/deletion automation | ⬜ | ไม่มี scheduled policy/job |
| Native OTLP ingestion pipeline | ⬜ | ต้องมี authenticated Collector/gateway mapping |
| LLM synthesis | ⏸ | Endpoint เป็น `501`; รอ evidence/security/evaluation gate |

## Foundation ที่ส่งมอบแล้ว

### Deterministic investigation core

- risk score 6 dimensions จาก explicit weights
- risk reason และ evidence IDs
- bounded BFS blast radius พร้อม hop cap และ cycle protection
- deterministic RCA ที่พิจารณา evidence และ counter-evidence
- human verdict แยกจาก original evidence snapshot
- synthetic scenarios ที่ทำซ้ำได้และติดป้ายชัดเจน

ข้อจำกัด: automated fixture correctness ไม่เท่ากับ real-dataset RCA accuracy

### Tenant application layer

- development bearer สำหรับ local
- production OIDC JWT/JWKS verification
- workspace/repository/scenario context ต่อ user
- roles `viewer`, `responder`, `admin`, `owner`
- invitation แบบ hashed, expiring, single-use และ revocable
- application audit events
- tenant-scoped change/incident/provider operations

ข้อจำกัด: ยังไม่มี PostgreSQL RLS และ audit store ยังไม่ tamper-proof

### Connected provider layer

- GitHub App install state และ callback
- installation-to-workspace mapping
- repository discovery/sync
- raw-body webhook HMAC
- durable GitHub delivery dedupe
- PR processing status และ signed-retry repair สำหรับ normalized events
- signed PR metadata เป็น connected change
- SMTP invitation delivery
- normalized telemetry HTTP endpoint

ข้อจำกัด: webhook ยัง synchronous ไม่มี worker/DLQ/background retry scheduler
แม้ Check publication จะมี durable retry state แล้ว และ telemetry endpoint
ไม่ใช่ OTLP receiver

### Operations workspace

- service catalog ที่ไม่ต้องเดาจาก repository name
- dependency validation ภายใน workspace และ cycle rejection
- versioned workspace risk thresholds และ safety requirements
- normalized operational-event ledger พร้อม tenant dedupe
- incident state transitions, assignee และ responder notes
- in-app notifications ที่ scope ตาม recipient

ข้อจำกัด: ยังไม่มี event queue/retention, Slack/Teams/PagerDuty delivery หรือ SLO
engine

## P0 — Production hardening

งานกลุ่มนี้ต้องเสร็จก่อนอ้าง production-ready

### PostgreSQL contract verification

Deliver:

- run migrations บน empty และ upgraded PostgreSQL
- concurrent policy/event/invitation tests
- transaction retry policy สำหรับ serialization/deadlock
- composite tenant constraints ที่เหมาะสม
- PostgreSQL RLS เป็น defense in depth
- query-plan/index review สำหรับ event/notification/audit list

Exit gate:

- SQLite local และ PostgreSQL contract behavior ตรงกัน
- cross-tenant matrix ผ่านบน PostgreSQL
- migration forward path และ restore path ถูกทดลองจริง

### Ingestion reliability

Deliver:

- fast webhook acknowledgement
- durable job queue
- bounded retry พร้อม exponential backoff
- dead-letter queue และ replay authorization
- scheduled/proactive GitHub reconciliation เพิ่มจาก signed-retry repair ที่มีแล้ว
- per-source/workspace rate limit และ quota
- request-body/cardinality limits
- operational metrics: accepted, duplicate, rejected, lag, retry, dropped

Exit gate:

- duplicate input ไม่สร้าง side effect ซ้ำ
- provider outage ไม่ทำ request thread ค้าง
- replay มี audit และ tenant authorization
- overload test แสดง bounded resource usage

### Data lifecycle

Deliver:

- configurable retention ต่อ data class
- scheduled archive/delete job
- workspace/provider uninstall deletion workflow
- legal-hold override
- backup/restore automation
- deletion และ restore audit

Exit gate:

- policy ไม่ใช่เพียงข้อความใน docs
- expired data ถูกลบจาก primary, backup ตาม policy และ search index ถ้ามี
- restore drill บน reference environment ผ่าน

### Platform security

Deliver:

- managed secret/KMS integration และ rotation
- HTTPS/security headers/CSP deployment profile
- dependency/image/SBOM pipeline
- log/telemetry secret redaction
- abuse/rate-limit tests
- production threat review และ penetration test

Exit gate:

- development provider เปิดไม่ได้ใน production
- no critical access-control/secret finding
- rotation ไม่ทำ synthetic mode เสีย

## P1 — Operational usefulness

### Native telemetry gateway

- OpenTelemetry Collector receiver
- Collector deployment, rotation และ distribution ของ workspace-derived credential
- semantic-convention version
- allowlisted/redacted normalized event contract
- queue/drop metrics และ backpressure
- service/deployment/incident correlation windows

FastAPI ไม่จำเป็นต้องเป็น OTLP receiver โดยตรง Collector ควรเป็น protocol
boundary แล้วส่ง normalized event เข้า API

### SLO และ error budget

- service-level SLI/SLO definition
- availability/latency/error-rate windows
- error budget before/after deployment
- regression detection tied to change/deployment
- SLO evidence เป็น input ของ deterministic risk policy

### Collaboration integrations

- Slack/Teams notification delivery
- PagerDuty/Opsgenie incident link
- Jira/Linear action items
- delivery preference, quiet hours, severity routing
- connection health, last success/error และ test connection

External notification ต้องเป็น allowlisted integration ไม่ใช่ arbitrary webhook
URL

### Search และ saved views

- search commit SHA, PR, service, incident และ event
- filters: time, severity, environment, source, status
- saved views และ deep links
- keyboard command palette
- pagination/cursor contract สำหรับ large workspace

## P2 — Evidence quality และ evaluation

### Versioned evaluation harness

- dataset/scenario/scoring/graph schema versions
- frozen core/held-out suites
- checksums และ run manifest
- Top-K/MRR/graph correctness metrics
- confidence intervals และ failure slices
- public/real-dataset provenance และ license inventory

ผล benchmark ทุกชุดต้อง pin commit, dataset และ configuration และต้องไม่ปน
unit-test count กับ model accuracy

### Risk calibration

- compare predicted risk กับ deployment outcomes
- false-positive/false-negative slices
- policy simulation ก่อน activate
- historical replay
- model/weight version comparison
- workspace feedback analytics โดยไม่ใช้ author identity เป็น risk signal

### Service graph scale decision

เริ่มด้วย relational adjacency/recursive CTE ก่อนเพิ่ม graph database พิจารณา
graph store เฉพาะเมื่อ benchmark บน workload จริงแสดงว่า PostgreSQL ไม่ผ่าน
latency/maintainability target

## Deferred — Evidence-grounded LLM

เปิดพิจารณาเมื่อ:

1. evidence-only typed contract มี version
2. deterministic explanation เป็น baseline
3. unsupported-claim และ citation validator มี tests
4. prompt-injection corpus มี tests
5. tenant/redaction/retention boundary ผ่าน review
6. provider region/retention/cost policy ถูกกำหนด
7. blind evaluation แสดงประโยชน์เหนือ deterministic template

LLM จะไม่มีสิทธิ์ให้คะแนน, สร้าง evidence, execute tool, deploy, rollback หรือ
remediate

## Definition of done

Capability จะเปลี่ยนเป็น implemented/verified ได้เมื่อมี:

- typed API และ data contract
- authorization/tenant negative tests
- deterministic/idempotency tests ตามความเสี่ยง
- migration และ operational failure behavior
- frontend loading/error/empty/accessibility behavior ถ้ามี UI
- reproducible verification command
- documentation ของ credential requirements และ known limitations

Deployment runbook อยู่ใน [OPERATIONS.md](OPERATIONS.md) และ threat controls อยู่
ใน [SECURITY.md](SECURITY.md)
