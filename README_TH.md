# DeployGuard AI

**พิสูจน์ว่า change ถูกตรวจอะไรจริงก่อนส่งขึ้น production และบันทึกผลหลัง deploy โดยไม่ต้องส่ง source code ให้ LLM**

[English](README.md) · [ภาษาไทย](README_TH.md) · [คู่มือเริ่มต้น](docs/QUICKSTART.md) · [เอกสารระบบ](docs/ARCHITECTURE.md)

![หน้าสืบสวน incident ของ DeployGuard AI](docs/assets/dashboard-runtime-desktop.png)

DeployGuard เชื่อม change, deployment, service topology, runtime signal และ
การตัดสินใจของคนไว้ใน evidence ledger เดียว เพื่อช่วยตอบว่า **change นี้เสี่ยง
เพราะอะไร** และ **สมมติฐานใดมีหลักฐานสนับสนุนมากที่สุด** ระบบไม่ deploy,
rollback หรือแก้ infrastructure ให้เอง

## ประโยชน์หลัก

- สร้าง Change Outcome Receipt แบบไม่ใช้ LLM key จาก JUnit, Coverage, SARIF
  และ build status พร้อมผล PASS/REVIEW/BLOCK ที่ผูกกับ commit SHA จริง
- อธิบาย risk score ด้วย signal, missing evidence, rollback readiness,
  service criticality และ blast radius ที่ตรวจสอบย้อนกลับได้
- จัดอันดับสมมติฐานด้วย supporting evidence และ counter-evidence โดยไม่ซ่อน
  uncertainty และระบุขั้นตอนตรวจสอบถัดไป
- เก็บ human verdict พร้อม actor provenance ที่ server เป็นผู้กำหนด และ
  structured verification outcome พร้อม evidence ID ที่ใช้อ้างอิง
- สร้าง immutable postmortem snapshot แบบ content-addressed เพื่อเก็บสถานะ
  incident ที่ผู้ตรวจสอบยืนยันไว้จริง
- ป้องกันการนำข้อมูล connected ไปสร้าง dataset จนกว่า incident จะ resolved,
  มี snapshot และผ่าน consent แบบระบุวัตถุประสงค์พร้อม audit trail

## ความสามารถที่มีแล้ว

| ส่วน | ความสามารถ |
| --- | --- |
| DeployGuard Verify | CLI และ GitHub Action แบบไม่ใช้ LLM key, policy จาก protected base, exact-SHA evidence และ reproducible receipt |
| Change risk | deterministic scoring, policy version, missing evidence, rollback readiness และ blast radius |
| Incident investigation | timeline, evidence, counter-evidence, ranked hypotheses, assignment, notification และ human verdict |
| Dataset governance | actor provenance, structured verification, immutable snapshot, append-only consent และ readiness gate |
| GitHub integration | GitHub App, repository sync, signed webhook และ optional Check Runs |
| Workspace | OIDC/development auth, RBAC, invitation, audit event และ tenant isolation |
| Operations | service catalog, normalized telemetry, durable job/outbox, retry, dead letter, metrics, backup และ restore |
| Evaluation | DeployGuard Bench schema, synthetic examples, SHA-256 manifest, golden/property tests และ CI artifacts |

## จาก Operational Data สู่ LLM Dataset

AI เป็น **ผู้ใช้ข้อมูลที่ผ่านการตรวจสอบ** ไม่ใช่ผู้สร้างหลักฐานหรือ ground truth

1. **Operational Data** — GitHub, deployment, telemetry และเหตุการณ์จากการสืบสวน
2. **Evidence Graph** — provenance, supporting evidence, counter-evidence และ hypotheses
3. **Human Review** — verdict, verification และ immutable postmortem
4. **Dataset Gate** — consent, privacy, license และ publication review

![Dataset promotion gate](docs/assets/dataset-promotion-gate-desktop.png)

### Dataset/LLM ทำครบแล้วหรือยัง

ยังไม่ครบทั้งกระบวนการ โดยสถานะจริงคือ:

- **ทำแล้ว:** schema, deterministic synthetic exporter, evaluation harness,
  synthetic examples 3 รายการ, actor provenance, structured verification,
  immutable snapshot และ audited consent
- **ยังปิดอยู่:** connected-data exporter แม้ทุก gate ผ่าน ระบบเพียงเปลี่ยนสถานะ
  เป็น `ready_for_review` และจะไม่ส่งข้อมูลออกเอง
- **ยังต้องทำ:** deterministic secret/PII redaction, publication review,
  release registry, revocation propagation, leakage checks, frozen data splits,
  annotation/adjudication และ real consented corpus
- **LLM ภายนอก:** ยังไม่เรียกใช้ จนกว่า benchmark และ safety gate จะพิสูจน์ได้

ปัจจุบัน DeployGuard Bench v0.1 มี synthetic example 3 รายการ: 2 รายการใช้
development evaluation ได้, 1 รายการยังไม่มี ground truth และ 0 รายการได้รับ
อนุมัติให้ train โมเดล เป้าหมาย 1,000 deployment scenarios และ 500 incident
investigations เป็น roadmap ไม่ใช่จำนวนข้อมูลปัจจุบัน

## เริ่มต้นใช้งาน

### ตรวจ change โดยไม่ใช้ LLM key

DeployGuard อ่าน artifact ที่ CI สร้างไว้แล้ว โดยไม่รันคำสั่งจาก repository และ
ไม่เรียกโมเดลภายนอก:

```bash
python -m pip install ./verify
deployguard verify --base origin/main --head HEAD \
  --evidence-sha "$(git rev-parse HEAD)" \
  --junit artifacts/junit.xml \
  --coverage artifacts/coverage.xml \
  --sarif artifacts/results.sarif
```

ผลลัพธ์อยู่ที่ `.deployguard/artifacts/evidence-receipt.json` โดย exit code คือ
`0` PASS, `2` REVIEW, `3` BLOCK และ `4` ERROR ถ้าหลักฐานขาดหรือ SHA ไม่ตรง
ระบบจะเป็น REVIEW ไม่ปลอมค่าเป็นศูนย์หรือ PASS ใช้คำสั่ง
`deployguard init --github --agent codex` เพื่อสร้าง workflow และคำแนะนำใน
`AGENTS.md` ส่วน Skill ช่วยให้ agent เรียกใช้และอธิบาย receipt เท่านั้น
ไม่สามารถเปลี่ยนคำตัดสินของ CLI ได้

### เปิด connected platform

ต้องมี Docker Engine หรือ Docker Desktop ที่รองรับ Compose v2

```bash
git clone https://github.com/kingggg5/deployguardai.git
cd deployguardai
docker compose up --build
```

เปิดเว็บที่ <http://127.0.0.1:4300> และ OpenAPI ที่
<http://127.0.0.1:8100/docs> โหมด connected เริ่มจากฐานข้อมูลว่าง หากต้องการ
ทดลองข้อมูล synthetic ที่แยกจากระบบจริง:

```bash
docker compose -p deployguard-demo \
  -f docker-compose.yml -f docker-compose.demo.yml up --build
```

ข้อมูล synthetic มีป้ายกำกับชัดเจนและไม่สามารถผ่าน connected-data gate ได้
รายละเอียด provider setup และ local development อยู่ใน
[คู่มือเริ่มต้น](docs/QUICKSTART.md)

## เทคโนโลยี

- **Web:** Angular 22, TypeScript 6, RxJS, SCSS design tokens
- **Control plane:** .NET 10, ASP.NET Core, YARP และ Npgsql
- **Application และ engines:** Python 3.12, FastAPI, Pydantic 2,
  SQLAlchemy 2 และ Alembic
- **Data:** PostgreSQL 16 พร้อม RLS; SQLite สำหรับ local development
- **Operations:** Docker Compose, OpenTelemetry, Prometheus, Nginx, GHCR
- **Quality:** Pytest, Vitest, golden/property/contract tests, CodeQL,
  dependency review, OpenSSF Scorecard, SBOM และ build provenance

.NET เป็น public entry point และตรวจ health/readiness แบบ fail-closed ส่วน
business route เดิมยังส่งต่อไปยัง FastAPI ภายในระหว่างการย้ายทีละส่วน Python
ยังเป็นเจ้าของ deterministic risk/evidence engine เพราะ benchmark workload
เดียวกันยังไม่แสดงประโยชน์จากการเขียน engine ซ้ำด้วย C# แนวทางนี้รักษา contract,
RLS และ rollback path พร้อมย้าย control plane โดยไม่เสี่ยง rewrite ทั้งระบบ

## เอกสารและชุมชน

[Quickstart](docs/QUICKSTART.md) · [Architecture](docs/ARCHITECTURE.md) ·
[API](docs/API_CONTRACT.md) · [Data model](docs/DATA_MODEL.md) ·
[Security](docs/SECURITY.md) · [Operations](docs/OPERATIONS.md) ·
[DeployGuard Bench](bench/README.md) ·
[Roadmap](docs/ROADMAP.md) · [Contributing](CONTRIBUTING.md)

รายงานช่องโหว่แบบส่วนตัวตาม [`.github/SECURITY.md`](.github/SECURITY.md)
โปรเจกต์ใช้สัญญาอนุญาต [Apache-2.0](LICENSE)
