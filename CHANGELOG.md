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
- Versioned SHA-256-pinned synthetic evaluation manifests with CI-uploaded result artifacts.

### Changed

- README and operations documentation now distinguish implemented hardening from provider- and infrastructure-dependent production work.
- Backend test dependency updated to a secure pytest 9.x range.
- GitHub Actions baseline moved to Node 24-compatible action majors to remove the hosted-runner Node 20 deprecation path.

### Still required for production

- Configure real OIDC, GitHub App, SMTP, telemetry, HTTPS ingress, managed secrets, backups, distributed rate limits, and monitoring.
- Wire the durable queue/outbox into external event and invitation producers, deploy a supervised worker, and complete a production restore rehearsal before processing critical external events.
