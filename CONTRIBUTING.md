# Contributing to DeployGuard AI

Thanks for helping make DeployGuard AI safer and more useful for engineering teams. DeployGuard is an evidence-first change-risk and incident-analysis tool. Contributions should make decisions easier to audit, explain, and reproduce.

## Before you start

- Read the [README](README.md), [architecture guide](docs/ARCHITECTURE.md), [security policy](.github/SECURITY.md), and [roadmap](docs/ROADMAP.md).
- Search existing issues and pull requests before opening a new one.
- For a security vulnerability, do not open a public issue. Follow [SECURITY.md](.github/SECURITY.md).
- Small, focused pull requests are easier to review than broad rewrites.

## Development setup

The public control plane requires the .NET 10 SDK, the application/engine
service requires Python 3.12 or newer, and the frontend uses the Node.js version
supported by the current Angular toolchain.

```bash
dotnet test control-plane/DeployGuard.ControlPlane.slnx
```

~~~powershell
# Standalone Verify package
cd verify
pip install -e ".[test]"
pytest
cd ..

# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"
pytest

# Frontend (from the repository root)
cd frontend
npm ci
npm test -- --watch=false
npm run build

# Compose validation (from the repository root)
docker compose config --quiet
~~~

Keep local secrets in an untracked .env file. Start from [.env.example](.env.example), and never commit tokens, cookies, private keys, production URLs, or real customer data.

## Design and product boundaries

- Prefer deterministic, typed, evidence-backed behavior. Include evidence, counter-evidence, uncertainty, and human feedback when changing risk or RCA behavior.
- Keep Skill/`AGENTS.md` instructions non-authoritative. Verification policy and
  PASS/REVIEW/BLOCK logic belong in the tested CLI, not agent prose.
- Never execute pull-request-defined commands inside the API or worker. Verify
  imports bounded machine-readable artifacts produced by an isolated CI job.
- Keep scoring weights explicit and cover them with tests.
- Synthetic scenarios must remain clearly labeled in both the API and the UI.
- Do not add autonomous deployment, rollback, shell execution, cluster credentials, or remediation. Proposals in those areas need an explicit security review first.
- Reuse the existing UI tokens and component patterns documented in [DESIGN.md](DESIGN.md). Avoid one-off styles or nested utility-class sprawl.
- Keep API models backward-compatible unless a migration and release note are included.

## Branches, commits, and pull requests

1. Create a branch from main, for example feat/evidence-export or fix/repository-timeout.
2. Make the smallest complete change and add or update tests.
3. Use a clear imperative commit subject. Conventional prefixes such as feat:, fix:, docs:, test:, and chore: are encouraged.
4. Open a pull request using the template. Explain the user impact, risk, migration/rollback plan, and verification performed.
5. Keep the pull request mergeable, respond to review feedback, and squash only when the maintainer asks for it.

At minimum, a pull request should include:

- a passing backend test run when backend code changed;
- a passing `verify/tests` run when receipt, policy, Action, or Skill behavior changed;
- a passing .NET build/test run when control-plane or routing code changed;
- a passing frontend test and production build when frontend code changed;
- updated API, data-model, security, or user documentation when behavior changes;
- screenshots or a short screen recording for meaningful UI changes;
- no secrets, generated runtime databases, or fixture-only behavior presented as connected data.

## Dataset contributions

Read the [DeployGuard Bench dataset card](bench/README.md) before changing the
schema, exporter, source scenarios, labels, or generated bundle.

- Submit synthetic data only. Do not contribute production incidents, private
  repository content, customer payloads, identifiers, prompts, or credentials.
- State the label source, license, provenance, intended task, supporting
  evidence, counter-evidence, and verification step for every example.
- Do not mark a synthetic scenario-author label as a human verdict.
- Keep public development examples out of training data when they are used for
  evaluation.
- Regenerate the bundle and commit the reviewed diff, then run:

~~~powershell
python scripts/export_operational_dataset.py `
  --check --output-dir bench/datasets/synthetic-v0.1
~~~

A large generated corpus without independent label review, split policy, and
leakage checks will not be accepted merely to increase the example count.

## Contract and evaluation changes

Engine, API, and dataset changes must preserve reproducible evidence. Run the
relevant checks from the repository root:

~~~powershell
python scripts/evaluate_benchmarks.py --output .runtime/evaluation-results.json
python scripts/capture_contracts.py --check
python scripts/export_operational_dataset.py --check --output-dir bench/datasets/synthetic-v0.1
~~~

The golden corpus under `scripts/evaluation/` freezes ordinary and boundary
behavior for risk, graph, and RCA engines. An intentional behavior change must
update the corresponding contract version and include a reviewed golden diff;
do not regenerate hashes only to make CI pass. Breaking HTTP changes require a
new versioned contract directory rather than overwriting the existing one.

Performance claims need a machine-readable artifact from
`scripts/performance_baseline.py`, the reference environment and workload, and
an explanation of what the measurement excludes. Local engine timing is not a
production capacity or SLO claim.

## Reporting bugs and requesting features

Use the repository issue forms for reproducible bugs and scoped proposals. Include the smallest safe reproduction, expected behavior, actual behavior, and the relevant commit or environment. Redact personal data and credentials. Feature requests should explain the operational problem and how success could be measured.

## Review and release

Maintainers review changes for correctness, security, accessibility, operability, and long-term maintenance. A change may be declined when it increases blast radius, hides uncertainty, couples the product to a single provider without an adapter boundary, or cannot be tested reliably.

The release process, compatibility expectations, and project decisions are documented in [GOVERNANCE.md](GOVERNANCE.md). All contributors are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

### Maintainer release checklist

Before creating an annotated semantic-version tag, maintainers must update the
changelog and version metadata, verify the complete protected-branch checks,
run `python scripts/production_readiness.py --json`, and attach the resulting
configuration, evaluation, migration, and restore evidence to the release.
Record immutable API/web image digests and a known-good rollback digest.

Deployments must pin a digest rather than `latest`. Rollback means redeploying
the previous known-good digest and following the database rollback policy in
[the operations runbook](docs/OPERATIONS.md); never repair a failed production
migration with ad-hoc SQL.

## ภาษาไทย

ขอบคุณที่ช่วยพัฒนา DeployGuard AI โปรเจกต์นี้เน้นหลักฐานที่ตรวจสอบย้อนหลังได้ จึงควรส่งการเปลี่ยนแปลงที่มี test, อธิบายผลกระทบชัดเจน และไม่ใส่ข้อมูลจริงหรือ secret ลงใน repository

- อ่าน README, architecture, security policy และ roadmap ก่อนเริ่มงาน
- ช่องโหว่ด้านความปลอดภัยต้องรายงานแบบ private ตาม SECURITY.md ห้ามเปิด public issue
- ทุก scoring และการเปลี่ยน API ต้องมี test และเอกสารกำกับ
- การเพิ่ม dataset ต้องเป็นข้อมูล synthetic พร้อม provenance, license,
  ground-truth source และห้ามอ้าง scenario label ว่าเป็น human verdict
- ห้ามเพิ่ม autonomous deploy, rollback, shell execution หรือ remediation โดยอัตโนมัติ
- PR ควรระบุ user impact, risk, migration/rollback และผลการทดสอบ
