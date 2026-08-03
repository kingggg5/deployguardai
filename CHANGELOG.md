# Changelog

All notable changes to DeployGuard AI are documented here. The project follows
release notes from `main` and will use semantic versioning for tagged releases.

## [Unreleased]

### Added

- Apache-2.0 open-source foundation with contribution, governance, support, and security policies.
- GitHub issue forms, pull request checklist, CODEOWNERS, Dependabot, CI, CodeQL, dependency review, and OpenSSF Scorecard workflows.
- Request IDs, structured access logs, request body limits, bounded ingress rate limits, and separate liveness/readiness probes.
- Durable `background_jobs` outbox primitives with idempotent enqueue, atomic claim, bounded retry/backoff, stale-lease recovery, dead-letter, and explicit replay semantics.
- Private low-cardinality Prometheus metrics endpoint with request-guard rejection counters.
- Recoverable SQLite/PostgreSQL backup helper and allow-listed, dry-run-first retention report.
- Read-only SQLite integrity/Alembic-head and PostgreSQL archive validation through `scripts/restore_check.py`.
- Engine-backed synthetic RCA evaluation manifest v2 with immutable inputs,
  expected labels, fail-closed validation, versioned scoring metadata,
  per-episode failure slices, and CI-uploaded result artifacts.
- Persisted schema, engine, scoring-policy, and graph provenance on change and
  incident snapshots, including an honest `legacy-unversioned` migration path.
- PostgreSQL migration-chain coverage in CI, including an upgrade/downgrade/
  re-upgrade cycle from the previous release revision.

### Changed

- README and operations documentation now distinguish implemented hardening from provider- and infrastructure-dependent production work.
- Backend test dependency updated to a secure pytest 9.x range.
- GitHub Actions baseline moved to Node 24-compatible action majors to remove the hosted-runner Node 20 deprecation path.
- Removed the unused pseudo-ML module and its fixed, unverified performance
  metrics; semantic unsupported-claim scoring now remains explicitly unmeasured
  until a human review protocol exists.
- Workspace Setup and Operations now clear tenant-scoped records while a new
  workspace snapshot loads, reject mutations without a matching snapshot, and
  show a recoverable unavailable state instead of stale cross-workspace data.
- Analysis identity now includes its version bundle, so an engine or policy
  release creates a new immutable result instead of reusing a stale snapshot.

### Still required for production

- Configure real OIDC, GitHub App, SMTP, telemetry, HTTPS ingress, managed secrets, backups, distributed rate limits, and monitoring.
- Wire the durable queue/outbox into external event and invitation producers, deploy a supervised worker, and complete a production restore rehearsal before processing critical external events.
