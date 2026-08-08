# DeployGuard AI

**Prove what was checked before a change ships, then record what happened after deployment - without sending source code to an LLM.**

[![CI](https://github.com/kingggg5/deployguardai/actions/workflows/ci.yml/badge.svg)](https://github.com/kingggg5/deployguardai/actions/workflows/ci.yml)
[![CodeQL](https://github.com/kingggg5/deployguardai/actions/workflows/codeql.yml/badge.svg)](https://github.com/kingggg5/deployguardai/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/kingggg5/deployguardai/badge)](https://securityscorecards.dev/viewer/?uri=github.com/kingggg5/deployguardai)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

[English](README.md) · [ภาษาไทย](README_TH.md) · [Quickstart](docs/QUICKSTART.md) · [Documentation](docs/ARCHITECTURE.md)

![DeployGuard AI investigation workspace](docs/assets/dashboard-runtime-desktop.png)

DeployGuard connects changes, deployments, service topology, runtime signals,
and human decisions in one evidence ledger. It helps an engineer answer two
questions: **why is this change risky?** and **which incident hypothesis is best
supported by evidence?** It never deploys, rolls back, or changes infrastructure.

## Why teams use it

- **Explain risk before production.** See weighted signals, missing evidence,
  rollback readiness, service criticality, and dependency blast radius.
- **Create a keyless Change Outcome Receipt.** Import JUnit, Cobertura/LCOV,
  SARIF, and build status into a canonical, SHA-addressed PASS/REVIEW/BLOCK
  decision that can run as a required GitHub check.
- **Investigate with evidence and counter-evidence.** Rank hypotheses without
  hiding uncertainty, then preserve the next verification step.
- **Keep human decisions accountable.** Verdicts carry server-owned actor
  provenance and structured verification outcomes with cited evidence IDs.
- **Turn incidents into reproducible memory.** Content-addressed postmortem
  snapshots preserve exactly what reviewers approved at a point in time.
- **Prepare operational data safely.** Connected records can only become dataset
  candidates after resolution, immutable snapshotting, and audited,
  purpose-specific consent. Passing the gate still does not export data.

## What is included

| Area | Capabilities |
| --- | --- |
| DeployGuard Verify | Zero-LLM-key CLI and GitHub Action, protected-base policy, exact-SHA evidence, reproducible receipt, and stable exit codes |
| Change risk | Deterministic scoring, versioned policies, missing-evidence signals, rollback readiness, and blast radius |
| Incident investigation | Timeline, evidence ledger, counter-evidence, ranked hypotheses, assignments, notifications, and human verdicts |
| Dataset governance | Actor provenance, structured verification, immutable postmortem snapshots, append-only consent decisions, and readiness gates |
| GitHub integration | GitHub App installation, repository sync, signed PR/deployment webhooks, and optional Check Runs |
| Team workspaces | OIDC/development auth, role-based access, invitations, audit events, and tenant isolation |
| Operations | Service catalog, normalized telemetry, durable jobs, retries, dead letters, traces, metrics, backup, and restore tooling |
| Evaluation | DeployGuard Bench schema, versioned synthetic examples, SHA-256 manifests, golden/property tests, and CI artifacts |

## Operational data, evidence graph, dataset

DeployGuard treats AI as a **consumer** of verified operational data—not as the
source of evidence or ground truth.

```mermaid
flowchart LR
    Data["Operational data\nGitHub · deployments · telemetry"] --> Graph["Evidence graph\nprovenance · counter-evidence"]
    Graph --> Review["Human review\nverdict · verification · postmortem"]
    Review --> Gate["Dataset promotion gate\nconsent · privacy · license"]
    Gate -. "connected export remains disabled" .-> Bench["DeployGuard Bench"]
    Bench --> Consumer["Evaluation and future LLM consumers"]
```

![Dataset promotion gate](docs/assets/dataset-promotion-gate-desktop.png)

### Dataset maturity

| Layer | Status |
| --- | --- |
| Synthetic schema, export, and evaluation foundation | **Implemented.** DeployGuard Bench v0.1 has 3 synthetic examples: 2 evaluation-eligible, 1 unverified, 0 training-approved. |
| Connected incident capture governance | **Implemented.** Actor provenance, structured verification, immutable snapshots, and audited consent are enforced and recorded. |
| Connected export and publication pipeline | **Not implemented.** The connected-data exporter is intentionally closed; redaction, release review, and revocation propagation remain required. |
| Production LLM dataset or public benchmark | **Not complete.** There is no real consented corpus, frozen hidden test set, public leaderboard, or external model integration. |

The target of 1,000 deployment scenarios and 500 incident investigations is a
roadmap goal, not a current dataset-size claim. See [DeployGuard Bench](bench/README.md)
and the [AI boundary](docs/AI_BOUNDARY.md).

## Quick start

### Verify a change without an LLM key

DeployGuard imports evidence your CI already produced; it does not execute
repository-defined commands or call a model. Generate JUnit XML first, then:

```bash
python -m pip install ./verify
deployguard verify --base origin/main --head HEAD \
  --evidence-sha "$(git rev-parse HEAD)" \
  --junit artifacts/junit.xml \
  --coverage artifacts/coverage.xml \
  --sarif artifacts/results.sarif
```

The command writes `.deployguard/artifacts/evidence-receipt.json`. Exit codes
are `0` PASS, `2` REVIEW, `3` BLOCK, and `4` ERROR. Missing or SHA-mismatched
evidence is REVIEW - never a fabricated zero or pass. Run
`deployguard init --github --agent codex` to scaffold a fail-closed workflow and
small `AGENTS.md` policy. The repository also includes the optional
`deployguard-change-safety` Skill; agent prose cannot override the CLI result.

The reusable action lives at the repository root. Pin a released full commit
SHA in production rather than a moving branch or tag.

### Run the connected platform

Requirements: Docker Engine or Docker Desktop with Compose v2.

```bash
git clone https://github.com/kingggg5/deployguardai.git
cd deployguardai
docker compose up --build
```

Open the app at <http://127.0.0.1:4300> and OpenAPI at
<http://127.0.0.1:8100/docs>. Connected mode starts empty. For the isolated,
deterministic product tour:

```bash
docker compose -p deployguard-demo \
  -f docker-compose.yml -f docker-compose.demo.yml up --build
```

Synthetic records are visibly labelled and never pass the connected-data gate.
Provider setup, local development, and cleanup are in the
[quickstart](docs/QUICKSTART.md).

## Architecture

```mermaid
flowchart LR
    User["Engineer or SRE"] --> Web["Angular web app"]
    Web --> Edge["ASP.NET Core 10 control plane"]
    GitHub["GitHub App"] -->|"signed events"| Edge
    OIDC["OIDC"] --> Edge
    Telemetry["Normalized telemetry"] --> Edge
    Edge --> App["FastAPI compatibility services"]
    App --> Engines["Python risk and evidence engines"]
    App --> Jobs["Durable job/outbox"]
    Jobs --> Worker["Supervised worker"]
    Edge -->|"readiness"| DB[("PostgreSQL source of truth")]
    App --> DB
    Engines --> DB
```

PostgreSQL is the production source of truth and enforces row-level tenant
isolation. SQLite supports local development. ASP.NET Core is now the public,
fail-closed entry point and owns native health/readiness; unchanged application
routes are forwarded to the internal FastAPI service while migration proceeds.
Python remains the sole deterministic engine authority because the measured
same-workload engine benchmark did not justify duplicating it in C#.

## Technology and verification

- **Web:** Angular 22, TypeScript 6, RxJS, SCSS design tokens
- **Control plane:** .NET 10, ASP.NET Core, YARP, Npgsql
- **Application and engines:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic
- **Keyless verification:** Python 3.12 CLI, composite GitHub Action, JUnit,
  Cobertura/LCOV, SARIF 2.1.0, canonical JSON receipts
- **Data:** PostgreSQL 16 with RLS; SQLite for local development
- **Operations:** Docker Compose, OpenTelemetry, Prometheus, Nginx, GHCR
- **Quality:** Pytest, Vitest, golden/property/contract tests, CodeQL,
  dependency review, OpenSSF Scorecard, SBOM, and build provenance

```bash
dotnet test control-plane/DeployGuard.ControlPlane.slnx
cd verify && python -m pytest && cd ..
cd backend && python -m pytest && cd ..
cd frontend && npm test -- --watch=false && npm run build && cd ..
docker compose config --quiet
python scripts/evaluate_benchmarks.py --output .runtime/evaluation-results.json
python scripts/export_operational_dataset.py --check --output-dir bench/datasets/synthetic-v0.1
python scripts/capture_contracts.py --check
```

## Documentation and community

[Quickstart](docs/QUICKSTART.md) · [Architecture](docs/ARCHITECTURE.md) ·
[API](docs/API_CONTRACT.md) · [Data model](docs/DATA_MODEL.md) ·
[Security](docs/SECURITY.md) · [Operations](docs/OPERATIONS.md) ·
[DeployGuard Bench](bench/README.md) ·
[Roadmap](docs/ROADMAP.md) · [Contributing](CONTRIBUTING.md)

Vulnerabilities must be reported privately through
[`.github/SECURITY.md`](.github/SECURITY.md). DeployGuard is licensed under
[Apache-2.0](LICENSE).

## Current limitations

- .NET owns the production-shaped entry point and health boundary; business
  routes still use the internal FastAPI compatibility service until each slice
  passes HTTP, auth/RBAC, PostgreSQL RLS, and failure-mode parity.
- No external LLM provider or public, real-world RCA benchmark is integrated.
- The standalone Action is authoritative for its own receipt. Connected receipt
  ingestion and attested linkage to the GitHub App Check are not implemented;
  the App Check remains neutral rather than claiming verified success.
- Connected export, deterministic secret/PII redaction, publication review,
  release registry, and revocation propagation are not implemented.
- Telemetry uses DeployGuard's normalized contract; there is no native OTLP
  evidence receiver yet.
- Slack, Teams, PagerDuty, autonomous remediation, and production execution are
  intentionally not bundled.
- Managed secrets, multi-replica rate limiting, alert routing, backup storage,
  and disaster-recovery ownership remain operator responsibilities.
