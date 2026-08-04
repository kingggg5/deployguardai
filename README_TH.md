# DeployGuard AI

ระบบวิเคราะห์ความเสี่ยงของ change และช่วยสืบสวน incident สำหรับทีม Platform,
SRE และทีมวิศวกรรม โดยใช้หลักฐานที่ตรวจสอบย้อนกลับได้

[English](README.md) · [คู่มือเริ่มต้นใช้งาน](docs/QUICKSTART.md) · [คู่มือ release](docs/RELEASE.md)

![DeployGuard AI workspace](docs/assets/dashboard-runtime-desktop.png)

## DeployGuard ช่วยอะไร

DeployGuard รวม pull request, deployment, dependency ของ service, telemetry
และข้อสังเกตจากมนุษย์ไว้ใน workspace เดียว เพื่อช่วยตอบคำถามสำคัญสองข้อ:

1. change นี้เสี่ยงตรงไหนก่อนขึ้น production
2. สมมติฐานของ incident ใดมีหลักฐานสนับสนุนมากที่สุด มี counter-evidence อะไร
   และควรตรวจสอบอะไรต่อ

ผลลัพธ์ของระบบมาจาก deterministic engine น้ำหนักคะแนนที่ระบุชัดเจน หลักฐานที่
เก็บไว้ และ policy ที่มี version จึงสามารถอธิบายและทำซ้ำได้ ระบบไม่ deploy,
rollback, รัน shell หรือแก้ infrastructure เองโดยอัตโนมัติ

## แนวทางข้อมูล: AI เป็นผู้ใช้ Evidence Graph

DeployGuard AI กำลังสร้างฐานข้อมูลเชิงปฏิบัติการสำหรับประเมิน AI/LLM ด้าน
Production Engineering โดยแบ่งเป็น 3 layer:

1. **Operational Data** — GitHub, OpenTelemetry, Prometheus, deployment และ
   เหตุการณ์จากการสืบสวน พร้อม provenance
2. **Evidence Graph** — เชื่อม change, topology, supporting evidence,
   counter-evidence, hypotheses, verification, human verdict และ postmortem
3. **DeployGuard Bench** — ตัวอย่างที่ผ่าน privacy review และมี version สำหรับ
   evaluation และใช้ train โมเดลได้เฉพาะเมื่อ consent/license/split policy อนุญาต

AI เป็น **consumer** ของ dataset ไม่ใช่ผู้สร้าง evidence หรือ ground truth
ปัจจุบัน [DeployGuard Bench](bench/README.md) มี schema, deterministic exporter
และ synthetic seed 3 ตัวอย่าง เป้าหมาย 1,000 deployment scenarios และ 500
incident investigations เป็น roadmap ไม่ใช่จำนวนข้อมูลที่มีแล้ว Incident จริง
เป็นเพียง candidate example จนกว่าจะผ่าน consent, redaction, licensing และ
human review โดย synthetic seed ปัจจุบันใช้ evaluation เท่านั้นและยังไม่อนุมัติ
ให้ใช้ train โมเดล

## ทดลองในไม่กี่นาที

โหมดปกติเป็น connected mode และเริ่มจากฐานข้อมูลว่าง:

```bash
git clone https://github.com/kingggg5/deployguardai.git
cd deployguardai
docker compose up --build
```

เปิด <http://127.0.0.1:4300> และดู OpenAPI ได้ที่
<http://127.0.0.1:8100/docs>

ถ้าต้องการดูหน้าจอพร้อมข้อมูลตัวอย่าง ให้ใช้ฐานข้อมูล demo ที่แยกออกจากระบบ
จริงและมีป้าย `synthetic` ชัดเจน:

```bash
docker compose -p deployguard-demo \
  -f docker-compose.yml -f docker-compose.demo.yml up --build
```

ข้อมูล demo ไม่ใช่ข้อมูลจาก GitHub และห้ามนำไปใช้เป็นหลักฐาน production
หรือ benchmark claim

## ความสามารถหลัก

- วิเคราะห์ change risk พร้อมเหตุผล, missing evidence, rollback readiness,
  service criticality และ blast radius
- timeline ของ incident พร้อม evidence, counter-evidence, uncertainty,
  ranked hypotheses และ human verdict
- GitHub App, signed webhook, repository/PR sync และ deployment lifecycle
- service catalog, risk policy, notifications, invitations และ audit ledger
- tenant isolation, RBAC, PostgreSQL RLS และ durable worker/outbox
- OpenTelemetry/OTLP, metrics ที่ลดข้อมูลละเอียดอ่อน และ restore/retention tools
- evaluation manifest ที่ pin checksum และแยกข้อมูล `connected` กับ `synthetic`

## สถานะ AI, dataset และ evaluation

- **LLM:** ยังไม่มีการเรียก external model ระบบใช้ deterministic evidence
  synthesis ที่ตรวจ citation ทุก statement ก่อนส่งผลลัพธ์
- **Dataset:** DeployGuard Bench v0.1 มี synthetic seed 3 ตัวอย่าง โดย 2 ตัวอย่าง
  ใช้ development evaluation ได้, 1 ตัวอย่างยังไม่มี ground truth และยังไม่มี
  ตัวอย่างใดได้รับอนุมัติให้ใช้ train โมเดล
- **Evaluation:** CI รัน engine-backed benchmark, golden/property tests และ
  contract fixtures แล้ว แต่ยังไม่มีผล accuracy, calibration หรือผลกระทบจาก
  production จริง

อ่าน methodology และข้อจำกัดได้ใน [Evaluation](docs/EVALUATION.md) และ
[AI boundary](docs/AI_BOUNDARY.md)

## ความปลอดภัยและความจริงของข้อมูล

browser จะไม่เห็น GitHub installation token, App private key, SMTP password หรือ
telemetry root credential การเปิดใช้ production ต้องเตรียม OIDC, GitHub App,
HTTPS/WAF, managed secrets, distributed rate limiting, backup storage,
alerting และผู้รับผิดชอบ on-call ให้ครบ จากนั้นรัน:

```powershell
python scripts/production_readiness.py
```

คำสั่งนี้เป็น fail-closed gate และจะไม่สร้างหรือพิมพ์ credential ให้เอง

## เอกสาร

- [Quickstart](docs/QUICKSTART.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API contract](docs/API_CONTRACT.md)
- [Security model](docs/SECURITY.md)
- [Operations runbook](docs/OPERATIONS.md)
- [Evaluation](docs/EVALUATION.md)
- [DeployGuard Bench](bench/README.md)
- [Contributing](CONTRIBUTING.md)
- [Release guide](docs/RELEASE.md)

โปรเจกต์ใช้สัญญา Apache-2.0 ดู [LICENSE](LICENSE) และหากพบปัญหาด้านความปลอดภัย
ให้รายงานแบบส่วนตัวตาม [.github/SECURITY.md](.github/SECURITY.md)
