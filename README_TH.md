# DeployGuard AI

**พิสูจน์หลักฐานของ change ก่อน merge และบันทึกผลหลัง deploy อย่างตรวจสอบย้อนกลับได้ โดยไม่ต้องใช้ LLM key**

[English](README.md) · [Quickstart](docs/QUICKSTART.md) · [Architecture](docs/ARCHITECTURE.md) · [Roadmap](docs/ROADMAP.md)

> **สถานะ:** pre-release / self-hosted alpha ระบบ connected พร้อมให้ทดสอบแบบควบคุม แต่ dataset ที่เผยแพร่ยังเป็น synthetic เท่านั้น

![หน้า Operations ล่าสุดของ DeployGuard AI](docs/assets/operations-surface-desktop.png)

ภาพนี้ใช้ scenario สาธิตแบบ synthetic ที่มีป้ายกำกับชัดเจน ไม่ใช่ production evidence

DeployGuard AI เป็นแพลตฟอร์ม open source สำหรับทีม GitHub, DevOps และ SRE โดยเปลี่ยน artifact ที่ CI สร้างอยู่แล้วให้เป็น evidence receipt ที่ผูกกับ commit จริง จากนั้นเชื่อม deployment, incident, verification และ human decision ไว้ใน workspace เดียว

## จุดเด่น

- **DeployGuard Verify** — CLI และ GitHub Action แบบ deterministic รองรับ JUnit, Cobertura/LCOV, SARIF และ build status พร้อมผล PASS, REVIEW, BLOCK หรือ ERROR ที่มี exit code คงที่
- **Evidence-first operations** — วิเคราะห์ความเสี่ยงและ blast radius, supporting/counter-evidence, deployment outcome, incident lifecycle, SLO/error budget และ human verdict ที่มี actor provenance
- **Governed dataset** — immutable postmortem, audited consent, redaction secret/PII, leakage checks และ release registry แบบ append-only พร้อม revocation tombstone
- **ไม่ส่ง source code ไป LLM** — ระบบไม่รันคำสั่งจาก repository, ไม่ deploy, ไม่ rollback และไม่แก้ infrastructure

## ทดลอง Verify

~~~bash
git clone https://github.com/kingggg5/deployguardai.git
cd deployguardai
python -m pip install ./verify
deployguard init --github --agent codex
~~~

สำหรับ workflow จริง ให้ใช้ tag v0.1.0 เพื่อเริ่มต้น แล้ว pin เป็น full commit SHA ก่อนใช้กับ protected branch ดูตัวอย่างและความหมายของแต่ละผลลัพธ์ใน [Quickstart](docs/QUICKSTART.md)

## Connected platform

~~~bash
cp .env.example .env
docker compose up --build
~~~

เปิดเว็บที่ <http://127.0.0.1:4300> และ OpenAPI ที่ <http://127.0.0.1:8100/docs> โหมด connected เริ่มต้นด้วย workspace ว่าง ส่วน demo mode แยกฐานข้อมูลและติดป้าย synthetic เสมอ

## สถานะที่ควรรู้

- เส้นทาง Verify receipt, authenticated receipt ingestion, GitHub Check จากหลักฐานจริง, deployment outcome, OTLP-normalized intake, notification outbox, SLO summary, PostgreSQL RLS และ dataset release/revocation registry มีอยู่ในโค้ดและมีการทดสอบ
- GitHub App, attestation key, OIDC, PostgreSQL runtime role, Collector และ Slack/Teams/PagerDuty ต้องตั้งค่าจริงโดย operator ก่อนใช้งาน production
- โปรเจกต์มีโครงสร้าง dataset และ governance แล้ว แต่ข้อมูลใน repository ยังเป็น synthetic เท่านั้น จึงยังไม่ควรเรียกว่า production benchmark จนกว่าจะมี consented real corpus, redaction review, annotation/adjudication, frozen split, contamination checks และ baseline evaluation

อ่านรายละเอียดต่อใน [AI boundary](docs/AI_BOUNDARY.md), [DeployGuard Bench](bench/README.md), [Operations](docs/OPERATIONS.md) และ [Security](docs/SECURITY.md)

DeployGuard AI ใช้สัญญาอนุญาต [Apache-2.0](LICENSE)
