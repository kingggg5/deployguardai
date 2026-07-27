# DeployGuard AI — User Guide & Operational Runbook
# คู่มือการใช้งานและคู่มือปฏิบัติการ DeployGuard AI

Welcome to the **DeployGuard AI User Guide**. This document provides step-by-step operational instructions for engineers, SREs, and technical leads using DeployGuard AI to analyze pre-deployment risks and investigate service incidents.

ยินดีต้อนรับสู่ **คู่มือการใช้งาน DeployGuard AI** เอกสารนี้รวบรวมขั้นตอนการทำงานอย่างเป็นระบบสำหรับวิศวกรซอฟต์แวร์ ทีม SRE และ Tech Lead ในการประเมินความเสี่ยงก่อนปล่อยระบบ และการสืบสวนสาเหตุการล่มอย่างมีประสิทธิภาพ

---

## 🧭 Navigating the 4 Workspaces / การใช้งาน 4 หน้าหลัก

DeployGuard AI splits your operational workflow into 4 clean, high-efficiency pages:

---

### 1. 🕵️ RCA Investigation Workspace (`investigation`)
**Purpose / วัตถุประสงค์**: Investigate active service incidents, trace root causes, replay timelines, and record expert human verdicts.

#### Step-by-Step Workflow / ขั้นตอนการทำงาน:
1. **Inspect Top Incident Header**: Check incident title, severity tag (`SEV-1`, `SEV-2`), and status (`investigating`, `resolved`).
2. **Explore Service Topology**:
   - Hover and click nodes on the interactive SVG canvas to inspect service health, blast radius hop distance, and team ownership.
   - Toggle **Evidence X-Ray** in the top right navbar to illuminate node impact scores and telemetry evidence weights.
3. **Review Telemetry Evidence Inspector**: Look at telemetry rows (trace spans, metric anomalies, log alerts) linked to the selected node or hypothesis.
4. **Replay Incident Timeline**: Click **"Replay Incident"** or click individual timeline steps to watch how the incident propagated across affected services.
5. **Evaluate Top-3 Hypotheses**: Review ranked hypotheses with confidence meters and next-step recommendations.
6. **Record Human Verdict**:
   - Select a hypothesis card.
   - Enter mandatory investigation notes in the text area.
   - Click **Confirm Cause**, **Mark Partial**, or **Reject Hypothesis** to update the audit ledger.

---

### 2. 🚀 Change Risk Analyzer Workspace (`change_risk`)
**Purpose / วัตถุประสงค์**: Evaluate Pull Request risks before deploying to production.

#### Step-by-Step Workflow / ขั้นตอนการทำงาน:
1. **Review Overall Risk Score Gauge**: Check the 0–100 risk score and level badge (`CRITICAL`, `HIGH`, `MODERATE`, `LOW`).
2. **Inspect Pre-Deploy Recommendations**: Read action items required before promoting the change.
3. **Examine Pull Request Details**: Review commit SHA, author, target branch, files changed, lines added (`+`), and lines deleted (`-`).
4. **Inspect Risk Flags**: Look for automated flags such as `schema-touch`, `hot-path`, or `retry-policy`.
5. **Analyze Weighted Risk Dimensions**: Examine progress meters for blast radius, code size, change type, test gaps, and historical failure priors.

---

### 3. 📊 DORA Performance Dashboard (`dora`)
**Purpose / วัตถุประสงค์**: Track engineering velocity, deployment reliability, and team productivity.

#### Step-by-Step Workflow / ขั้นตอนการทำงาน:
1. **Deployment Frequency**: Monitor weekly deployment velocity against elite benchmarks.
2. **Change Lead Time**: Track elapsed time from commit SHA to production rollout.
3. **Change Failure Rate**: Measure the proportion of releases triggering incident investigations.
4. **Mean Time to Restore (MTTR)**: Track recovery duration between SLO breach and resolution verdict.

---

### 4. 🧪 Scenario Lab Matrix (`scenarios`)
**Purpose / วัตถุประสงค์**: Test, demonstrate, and validate DeployGuard AI using reproducible synthetic scenarios.

#### Step-by-Step Workflow / ขั้นตอนการทำงาน:
1. **Browse Synthetic Scenarios**: Explore registered labs (e.g., *Checkout Latency Regression*, *Worker Queue Saturation*).
2. **Activate Scenario**: Click **"Activate Scenario"** to instantly switch the active change, topology, telemetry evidence, and incidents.

---

## 🌐 Language & Theme Settings / การปรับแต่งภาษาและธีม

- **Language Switching (TH / EN)**: Click **TH** or **EN** in the top right navbar. 100% of all headings, labels, tags, and button texts update instantly.
- **Dark / Light Theme Toggle**: Click the **Theme Toggle Button** in the navbar to switch between Dark Obsidian mode and Light Paper mode.

---

## 🛠️ Troubleshooting & Support / การแก้ปัญหาเบื้องต้น

| Problem / ปัญหา | Cause / สาเหตุ | Solution / วิธีแก้ไข |
|---|---|---|
| White Screen / Page Not Loading | Dev server process interrupted | Run `.\scripts\run-dev.ps1 -SkipInstall` or `npm start` in `frontend` |
| API Connection Interrupted | Backend FastAPI not listening on 8100 | Run `.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8100` |
| Evidence X-Ray Not Showing | Toggle is turned off | Click **"Evidence X-Ray"** switch in the top navbar |
