# Operations runbook

เอกสารนี้เป็น runbook สำหรับรันและดูแล DeployGuard AI ตาม capability ที่มีใน
repository ปัจจุบัน ไม่ใช่ใบรับรองว่า environment ใด production-ready

## Runtime profiles

| Profile | Database | Auth | External providers | Intended use |
|---|---|---|---|---|
| Local development | SQLite | Development bearer | Optional | Real connected-mode integration by default; synthetic verification only with `SEED_SYNTHETIC_DATA=true` |
| Docker Compose | PostgreSQL container | Development โดย default | Optional | Local integration |
| Production | PostgreSQL managed | OIDC only | Explicit credentials | ต้องมี hardening เพิ่มตาม checklist |

`docker-compose.yml` กำหนด `ENVIRONMENT=container` และ development defaults จึง
ไม่ควร deploy ไฟล์นี้ตรง ๆ เป็น production manifest

## Local startup

Requirements:

- Python 3.12+
- Node.js 22+ (Docker build stage ใช้ Node 24)
- npm
- PowerShell

จาก project root:

```powershell
.\scripts\run-dev.ps1
```

Default local configuration starts without bundled demo records. If a synthetic
evaluation run is required, set `SEED_SYNTHETIC_DATA=true` explicitly in the
API environment. If an override is needed, copy `.env.example` to the API
working directory:

```powershell
Copy-Item .env.example backend/.env
```

เมื่อ dependencies มีอยู่แล้ว:

```powershell
.\scripts\run-dev.ps1 -SkipInstall
```

Endpoints:

- UI: `http://127.0.0.1:4300`
- API docs: `http://127.0.0.1:8100/docs`
- Liveness: `http://127.0.0.1:8100/api/v1/health/live`
- Readiness: `http://127.0.0.1:8100/api/v1/health/ready`
- Health (backward-compatible readiness alias): `http://127.0.0.1:8100/api/v1/health`
- Metrics (private Prometheus scrape): `http://127.0.0.1:8100/api/v1/metrics`
- Logs: `.runtime/backend.*.log` และ `.runtime/frontend.*.log`

หยุด process ที่ script สร้าง:

```powershell
.\scripts\stop-dev.ps1
```

Stop script ตรวจ command line ว่า PID ยังเป็น process ของ project นี้ก่อนหยุด
เพื่อลดความเสี่ยงจาก stale PID file

## Docker Compose

```powershell
Copy-Item .env.example .env
docker compose config
docker compose up --build
docker compose ps
```

Compose รอ PostgreSQL health ก่อนเริ่ม API และรอ API health ก่อนเริ่ม web
application Nginx proxy `/api/` ไป FastAPI

หยุด containers:

```powershell
docker compose down
```

คำสั่งนี้ไม่ลบ named volume หากต้องลบข้อมูล local ต้องตัดสินใจอย่างชัดเจนและ
สำรองก่อน อย่าใช้ `down --volumes` กับ environment ที่มีข้อมูลสำคัญ

## Configuration contract

### Required for production

```dotenv
ENVIRONMENT=production
DATABASE_URL=postgresql+psycopg://...
AUTH_PROVIDER=oidc
OIDC_ISSUER=https://identity.example/
OIDC_AUDIENCE=deployguard-api
OIDC_CLIENT_ID=deployguard-web
OIDC_JWKS_URL=https://identity.example/.well-known/jwks.json
FRONTEND_PUBLIC_URL=https://deployguard.example
CORS_ORIGINS=https://deployguard.example
ALLOW_DATABASE_RESET=false
```

Production startup fail-fast หาก `AUTH_PROVIDER` ไม่ใช่ OIDC หรือ OIDC
configuration ไม่ครบ

### GitHub App

```dotenv
GITHUB_APP_ID=...
GITHUB_APP_SLUG=...
GITHUB_APP_PRIVATE_KEY=...
GITHUB_WEBHOOK_SECRET=...
GITHUB_API_URL=https://api.github.com
GITHUB_API_VERSION=2026-03-10
GITHUB_CHECKS_ENABLED=false
GITHUB_WEBHOOK_MAX_BODY_BYTES=1048576
```

- เก็บ private key และ webhook secret ใน secret manager
- `GITHUB_CHECKS_ENABLED` เป็น explicit write-capability switch
- เมื่อเปิด Signed PR webhook จะ publish ผ่าน durable publication record
  Transient failure ทำให้ delivery retry ได้ และ responder ใช้ manual endpoint
  เพื่อ retry/PATCH Check เดิม
- body limit ป้องกัน oversized webhook ก่อน JSON processing
- GitHub App permissions ต้องตรงกับ action ที่เปิดใช้ การ publish Check Run
  ต้องมี Checks write permission

### SMTP

```dotenv
SMTP_HOST=smtp.example
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_FROM_EMAIL=deployguard@example.com
SMTP_USE_TLS=true
```

Production ที่ไม่มี SMTP configuration จะปิด invitation delivery แทนการคืน
development claim token

### Telemetry

```dotenv
TELEMETRY_INGEST_TOKEN=<random-root-secret-at-least-32-characters>
```

ค่านี้เป็น credential root ฝั่ง server ห้ามส่งจาก production Collector โดยตรง
ให้ derive bearer ต่อ workspace:

```powershell
Set-Location backend
$env:DEPLOYGUARD_WORKSPACE_ID = "<workspace-id>"
python -c "import os; from app.services import derive_telemetry_collector_token as d; print(d(os.environ['TELEMETRY_INGEST_TOKEN'], os.environ['DEPLOYGUARD_WORKSPACE_ID']))"
```

Collector ส่ง `Authorization: Bearer dgct_...`,
`X-DeployGuard-Workspace`, stable `X-DeployGuard-Event-ID` และ
`X-DeployGuard-Repository` เมื่อระบุ repository ได้ `/telemetry/events` รับ
normalized JSON เข้า tenant operational-event ledger ไม่ใช่ OTLP Production
ปฏิเสธ raw root token ควรวาง Collector/gateway หลัง TLS เพื่อทำ redaction,
body/rate limits และ rotation

## Request protection and access logs

The API adds an `X-Request-ID` response header, emits one-line JSON access logs,
rejects requests over `MAX_REQUEST_BODY_BYTES`, and rate-limits development
session, GitHub webhook, and telemetry ingestion routes using
`RATE_LIMIT_REQUESTS` per `RATE_LIMIT_WINDOW_SECONDS`. These controls are a
single-process baseline for local or one-instance deployments. Put a shared
gateway/WAF in front of production and configure distributed quotas before
exposing public ingestion endpoints.

```dotenv
MAX_REQUEST_BODY_BYTES=2097152
RATE_LIMIT_REQUESTS=120
RATE_LIMIT_WINDOW_SECONDS=60
```

## Database migrations

Application startup เรียก Alembic upgrade ถึง `head` อัตโนมัติ การตรวจด้วย CLI:

```powershell
Set-Location backend
alembic current
alembic history
alembic upgrade head
```

`migrations/env.py` อ่าน `DATABASE_URL` จาก environment ถ้ามี

ห้าม apply revision ที่สร้างจาก `alembic revision --autogenerate` โดยไม่ review
ปัจจุบัน metadata กับ revision `0003` มี representation drift ของ unique
index/constraint ที่ `provider_connections.installation_id` และ
`provider_authorization_states.state_hash` แม้ runtime uniqueness มีอยู่แล้ว
ควร reconcile naming/model metadata ก่อนใช้ autogenerate เป็น clean gate

Production migration procedure:

1. ตรวจ `alembic current` เทียบ release target
2. สำรองฐานข้อมูลและทดลอง restore ไป isolated environment
3. รัน migration กับ restored snapshot
4. รัน API smoke tests และตรวจ query latency
5. rollout application ตาม compatibility window
6. ตรวจ `alembic_version`, health และ error rate

Application ปฏิเสธ non-empty database ที่ไม่มี `alembic_version` ใน production
Local legacy bootstrap มีไว้ย้าย schema เก่าเฉพาะ table allowlist และไม่ควรใช้
แทน production migration plan

### Rollback

อย่า downgrade schema โดยอัตโนมัติเมื่อ application deployment fail:

- rollback application ได้เมื่อ old binary ยัง compatible กับ upgraded schema
- ถ้า migration destructive ให้ใช้ expand/migrate/contract หลาย release
- database downgrade ต้องผ่าน restore rehearsal และ approval
- เมื่อ data transform ย้อนกลับไม่ได้ ให้ restore backup ตาม RPO/RTO แทน

## Health และ observability

`GET /api/v1/health/ready` รัน `SELECT 1` และคืน service/database status สำหรับ
readiness ส่วน `GET /api/v1/health/live` เป็น lightweight liveness probe ที่ไม่
แตะฐานข้อมูล `GET /api/v1/health` ยังคงเป็น readiness alias เพื่อความเข้ากันได้

API มี process-level metrics exporter สำหรับ scrape ภายใน:

- `GET /api/v1/metrics` คืน Prometheus text exposition
- labels มีเฉพาะ HTTP method, status class และเหตุผล rejection ที่เป็น allowlist
- ไม่มี route, tenant ID, request ID หรือ payload label เพื่อป้องกัน cardinality และข้อมูลรั่ว

Endpoint นี้เป็น aggregate ของ process เดียวและไม่แทน distributed metrics
backend; ให้ expose เฉพาะ private network/service monitor และตั้งค่า auth หรือ
network policy ที่ reverse proxy เมื่อ deploy จริง กระบวนการ restart จะ reset
counter จึงควรใช้ Prometheus counter semantics และ scrape ทุก replica

สิ่งที่ deployment platform ควรเก็บเพิ่มเติม:

- HTTP request count/latency/status แยก route
- database pool usage/query latency/errors
- webhook accepted/rejected/duplicate และ processing latency
- operational event accepted/correlated/duplicate
- OIDC/JWKS verification failures
- GitHub API rate limit/retry/errors
- SMTP send outcome
- migration duration/failure
- notification fan-out count

Repository ยังไม่มี dashboard, SLO recording rules หรือ alert policy แบบผูกกับ
องค์กร รายการเหล่านี้ยังต้องกำหนดใน monitoring platform ของแต่ละทีม

## Failure playbooks

### API ไม่เริ่มหลัง release

1. ตรวจ configuration validation error โดยไม่เผย secret
2. ตรวจ database DNS/TLS/credential/connectivity
3. ตรวจ Alembic revision และ migration logs
4. ห้ามเปิด `ALLOW_DATABASE_RESET` เพื่อแก้ production startup
5. rollback application เฉพาะเมื่อ schema compatibility ยืนยันแล้ว

### GitHub webhook ถูกปฏิเสธ

1. ตรวจว่ามี `GITHUB_WEBHOOK_SECRET`
2. ตรวจ event/delivery/signature headers
3. เปรียบเทียบ secret ที่ rotate กับ GitHub App configuration
4. ตรวจ body limit และ invalid JSON metrics
5. ห้าม disable signature verification

Duplicate delivery เป็น expected behavior และต้องไม่มี side effect ซ้ำ

- PR delivery ใช้ `processing → processed|failed`; signed retry ประมวลผลต่อเมื่อ
  ยังไม่ processed
- workflow/deployment retry ตรวจ event ledger และสร้าง normalized event ที่หายไป
  ด้วย delivery ID เดิม
- installation/repository identity ที่ไม่ตรงกับ recorded delivery คืน
  `409 github_delivery_identity_mismatch`

### GitHub connection เป็น `pending_verification`

1. ตรวจว่า installation webhook มาถึง public endpoint
2. ตรวจ webhook signature และ installation ID
3. ตรวจ GitHub App event subscription
4. อย่า force connection เป็น `connected` ใน database

### Operational event replay

Event identity คือ `(workspace_id, source, provider_event_id)` Client ควรถือ
response `201` ที่คืน row เดิมเป็น idempotency outcome เฉพาะเมื่อ canonical
payload และ origin เดิม ถ้า key เดิมแต่ content/origin ต่าง API คืน
`409 operational_event_idempotency_conflict` ห้ามเปลี่ยน provider event ID เพื่อ
บังคับสร้าง event ซ้ำ Member provenance ถูก discard; server-owned `_ingestion`
บอกว่า event มาจาก `member_api` หรือ `trusted_internal`

### Risk policy version conflict

1. อ่าน policy ปัจจุบันอีกครั้ง
2. merge intent ของผู้ใช้กับ current values
3. ส่ง `version = current.version + 1`
4. อย่า retry stale payload แบบ blind

### Incident transition ถูกปฏิเสธ

- lifecycle เดินหน้าเท่านั้น
- `resolved` เป็น terminal สำหรับ lifecycle PATCH แต่ responder ยังเพิ่ม
  post-resolution/postmortem note ได้
- assignee ต้องเป็น active workspace member
- โหลด incident ล่าสุดก่อน retry

### Notification backlog

Notification เป็น in-app rows ไม่มี delivery worker ปัจจุบัน ตรวจ:

- fan-out volume ต่อ incident mutation
- indexes บน user/read/created time
- unread query latency
- retention policy ภายนอก

## Backup, restore และ retention

Repository มี helper แบบ explicit สำหรับ backup และ retention report แต่ยังไม่มี
scheduler/managed storage ให้ production owner ต่อเข้ากับ platform ขององค์กร:

สร้าง SQLite backup แบบ atomic (ไม่ overwrite โดย default):

```powershell
python scripts/backup_database.py `
  --database-url "sqlite:///./backend/deployguard.db" `
  --output .runtime/backups/deployguard-$(Get-Date -Format yyyyMMdd-HHmmss).db
```

PostgreSQL ใช้ `pg_dump` custom archive และต้องมี PostgreSQL client/credential
ใน environment:

```powershell
python scripts/backup_database.py `
  --database-url $env:DATABASE_URL `
  --output .runtime/backups/deployguard-$(Get-Date -Format yyyyMMdd-HHmmss).dump
```

ไฟล์ปลายทางที่มีอยู่จะถูกปฏิเสธ เว้นแต่ระบุ `--force` อย่างชัดเจน ควรเก็บ
backup นอก host และเข้ารหัสด้วย storage/secret policy ขององค์กร

ตรวจ retention candidates แบบ read-only ก่อน:

```powershell
python scripts/retention_report.py `
  --database-url $env:DATABASE_URL `
  --days 90
```

การลบต้องระบุทั้ง `--apply` และ `--confirm DELETE-EXPIRED-ROWS` เท่านั้น และ
สคริปต์แตะได้เฉพาะ operational allowlist (`audit_events`,
`operational_events`, `notifications`, webhook/invitation delivery และ
authorization state) ไม่รวม users, workspaces, incidents หรือ evidence:

```powershell
python scripts/retention_report.py `
  --database-url $env:DATABASE_URL `
  --days 90 --table notifications `
  --apply --confirm DELETE-EXPIRED-ROWS
```

ก่อน apply ต้องตรวจ backup, legal hold และผล dry-run เสมอ การ implement
scheduler, deletion audit และ workspace/legal-hold workflow ยังเป็นหน้าที่ของ
production owner

Production owner ต้องกำหนด:

- RPO/RTO
- encrypted backup schedule
- cross-region/off-account copy ตามความเสี่ยง
- restore test cadence
- retention ต่อ webhook event, operational event, incident note, notification
  และ audit event
- workspace deletion/uninstall/legal-hold workflow

ห้ามอ้าง retention เช่น 7/30/90 วันจนมี job, configuration และ deletion audit
ทำงานจริง

## Verification commands

Backend:

```powershell
Set-Location backend
python -m pytest
```

Frontend:

```powershell
Set-Location frontend
npm test -- --watch=false
npm run build
npm audit --omit=dev
```

Compose:

```powershell
docker compose config
```

Migration smoke:

```powershell
Set-Location backend
alembic upgrade head
alembic current
```

คำสั่งเหล่านี้เป็น reproducible verification contract ผู้ดูแล release ต้องเก็บ
ผลลัพธ์ของ run จริงไว้กับ commit/image digest

## Production release checklist

- [ ] Release commit และ image digest ถูก pin
- [ ] Backend/frontend tests และ build ผ่านจาก clean environment
- [ ] Dependency/image scan ไม่มี unresolved critical finding
- [ ] Production uses OIDC; development auth/reset ปิด
- [ ] Secrets มาจาก managed secret provider
- [ ] Database backup และ restore rehearsal ล่าสุดอยู่ใน policy
- [ ] Alembic current/target ถูกต้อง
- [ ] GitHub webhook secret/body limit และ optional Checks permission ถูก review
- [ ] CORS, TLS, CSP และ reverse-proxy limits ถูกตั้งค่า
- [ ] Tenant/RBAC negative tests ผ่านบน PostgreSQL
- [ ] Rate limit/queue/retention controls พร้อม หรือ risk ถูกยอมรับเป็นลายลักษณ์อักษร
- [ ] Dashboards/alerts และ on-call ownership พร้อม
- [ ] Synthetic/connected label ยังแสดงตาม data source จริง
- [ ] ไม่มี deploy, rollback, shell หรือ cluster credential ใน application

ดู architecture boundary ที่ [ARCHITECTURE.md](ARCHITECTURE.md) และ threat model
ที่ [SECURITY.md](SECURITY.md)
