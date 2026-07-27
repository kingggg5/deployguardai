# DeployGuard AI — Evidence-Backed Change Risk & RCA Investigation Ledger
# ระบบวิเคราะห์และติดตามความเสี่ยงการเปลี่ยนผ่านระบบ (Evidence-First Change Risk & RCA Investigation Ledger)

[![Backend Tests](https://img.shields.io/badge/Backend%20Tests-15%2F15%20Passed-brightgreen)](https://github.com/kingggg5/deployguard)
[![Frontend Tests](https://img.shields.io/badge/Frontend%20Tests-8%2F8%20Passed-brightgreen)](https://github.com/kingggg5/deployguard)
[![Angular Production Build](https://img.shields.io/badge/Angular%20Build-Passing-blue)](https://github.com/kingggg5/deployguard)
[![License](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)

---

## 📌 Project Overview / ภาพรวมโครงการ

**DeployGuard AI** is a production-ready operational investigation ledger designed to analyze pre-deployment Pull Request risks, calculate microservice blast radii, correlate telemetry evidence during SLO breaches, and rank root-cause hypotheses with human verdict feedback.

**DeployGuard AI** คือระบบวิเคราะห์ความเสี่ยงก่อนปล่อยอัปเดตระบบ (Pre-Deployment PR Risk Engine) และระบบสืบสวนหาสาเหตุรากเหง้าของการล่ม (RCA Investigation Ledger) แบบ Evidence-First โดยเชื่อมโยงข้อมูล Pull Request, ผังโครงสร้างระบบ (Dependency Graph), ข้อมูลชี้วัด Telemetry (OTel & Prometheus), และการตัดสินใจโดยทีมวิศวกร (Human Verdict) ไว้อย่างสมบูรณ์

---

## 🏗️ System Architecture Diagram / แผนผังระบบ

```mermaid
flowchart TB
    subgraph Ingestion["1. Ingestion Layer"]
        PR["Pull Request / Commit"] --> GW["Webhook Gateway"]
        OTel["OpenTelemetry Spans"] --> TelemetryIngest["Telemetry Ingest API"]
        Prom["Prometheus Metrics"] --> TelemetryIngest
    end

    subgraph Engines["2. Deterministic Core Engines"]
        GW --> RiskEngine["Deterministic Risk Engine"]
        RiskEngine --> BlastGraph["BFS Blast Radius Graph Traversal"]
        TelemetryIngest --> EvidenceStore[("Evidence Store / SQLite / Postgres")]
        BlastGraph --> RCAEngine["RCA Top-3 Hypothesis Engine"]
        EvidenceStore --> RCAEngine
    end

    subgraph UI["3. Multi-Page Magic UI Dashboard"]
        RCAEngine --> P1["🕵️ Page 1: RCA Investigation"]
        RiskEngine --> P2["🚀 Page 2: Change Risk Analyzer"]
        TelemetryIngest --> P3["📊 Page 3: DORA Metrics"]
        EvidenceStore --> P4["🧪 Page 4: Scenario Lab Matrix"]
    end

    subgraph Feedback["4. Human Audit & Feedback"]
        P1 --> Verdict["Human Verdict Drawer (Confirm / Partial / Reject)"]
        Verdict --> AuditLedger[("Audit & Feedback Ledger")]
    end

    style Ingestion fill:#1e293b,stroke:#3b82f6,color:#fff
    style Engines fill:#1e293b,stroke:#8b5cf6,color:#fff
    style UI fill:#1e293b,stroke:#10b981,color:#fff
    style Feedback fill:#1e293b,stroke:#f59e0b,color:#fff
```

---

## ✨ Key Features & Multi-Page Navigation / คุณสมบัติเด่น

### 1. 🕵️ RCA Investigation Workspace (`investigation`)
- **Interactive Service Topology Canvas**: Microservice dependency graph with real-time health badges, hop-distance calculations, and Evidence X-Ray view mode.
- **Evidence Inspector**: Dynamic telemetry log trace rows paired with confidence scoring.
- **Incident Replay Timeline**: Step-by-step playback scrubber of incident progression.
- **Ranked Hypotheses & Human Verdict Drawer**: Top-3 ranked root-cause hypotheses with interactive human verdict recording (Confirm / Partial / Reject).

### 2. 🚀 Change Risk Analyzer (`change_risk`)
- **PR Risk Score Meter**: Deterministic 0–100 overall risk score gauge.
- **Weighted Dimensions**: Detailed breakdown of blast radius, code size, change flags, test coverage gaps, and operational history.
- **Pre-Deploy Recommendations**: Automated, evidence-backed safety guidelines before production promotion.

### 3. 📊 DORA Metrics Dashboard (`dora`)
- High-level engineering reliability benchmarks:
  - **Deployment Frequency**: Weekly deployment velocity.
  - **Change Lead Time**: Commit-to-production duration.
  - **Change Failure Rate**: Proportion of releases triggering incidents.
  - **Mean Time to Restore (MTTR)**: Average SLO breach recovery speed.

### 4. 🧪 Scenario Lab Matrix (`scenarios`)
- Reproducible synthetic scenario matrix (Checkout Latency Regression, Worker Queue Backlog, etc.) for testing, demonstration, and validation without touching production workloads.

---

## ⚡ Quick Start Guide / วิธีการเริ่มต้นใช้งาน

### Prerequisites / สิ่งที่ต้องเตรียม
- Node.js (v18+)
- Python (3.11+)

### 1. Running Locally / การรันในเครื่อง

```powershell
# Clone the repository
git clone https://github.com/kingggg5/deployguard.git
cd deployguard

# Start both Backend & Frontend dev servers automatically
.\scripts\run-dev.ps1 -SkipInstall
```

Access the applications:
- **DeployGuard UI Dashboard**: [http://127.0.0.1:4300](http://127.0.0.1:4300)
- **FastAPI OpenAPI Documentation**: [http://127.0.0.1:8100/docs](http://127.0.0.1:8100/docs)
- **Backend Health Check**: [http://127.0.0.1:8100/api/v1/health](http://127.0.0.1:8100/api/v1/health)

To stop running services:
```powershell
.\scripts\stop-dev.ps1
```

### 2. Running with Docker Compose / การรันด้วย Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

---

## 🧪 Verification & Testing / การทดสอบความถูกต้อง

Both backend and frontend test suites are 100% covered and passing:

```powershell
# Run Backend Pytest Suite (15/15 Passed)
cd backend
.\.venv\Scripts\python -m pytest

# Run Frontend Vitest Suite (8/8 Passed)
cd ..\frontend
npm test -- --watch=false

# Run Production Frontend Build Check
npm run build
```

---

## 📁 Repository Structure / โครงสร้างโฟลเดอร์

```
deployguard-ai/
├── .agents/                    # Agent Skills & UI/UX Pro Max Configuration
│   └── skills/
│       └── ui-ux-pro-max-skill/
│           └── SKILL.md
├── backend/                    # FastAPI, Pydantic, SQLAlchemy 2.x & Risk Engines
│   ├── app/
│   │   ├── api.py              # REST API Routes & Endpoints
│   │   ├── engines.py          # Deterministic Risk & Blast Radius Engines
│   │   ├── main.py             # FastAPI App Factory & Middleware
│   │   └── seed.py             # Synthetic Scenario Seed Data
│   └── tests/                  # Pytest Unit & Integration Tests
├── frontend/                   # Angular Standalone Applications & Magic UI Components
│   ├── src/
│   │   ├── app/
│   │   │   ├── core/           # API Services, i18n Dictionary & Models
│   │   │   ├── app.html        # 4-Page Bento Grid Layout Template
│   │   │   ├── app.ts          # Reactive Component Logic
│   │   │   └── app.spec.ts     # Vitest Unit Tests
│   │   └── styles.scss         # Magic UI Design Tokens & SCSS
└── docs/                       # Architecture & User Guides
```

---

## 📄 License & Compliance

Distributed under the MIT License. See `LICENSE` for details.
