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
- Versioned golden corpus, property tests, captured OpenAPI/HTTP contracts, and
  a reproducible local performance-result schema.
- Transactional GitHub Check job producer, separately supervised allow-listed
  worker, trace propagation, crash recovery, queue visibility, and audited
  replay for failed/dead-letter jobs.
- PostgreSQL tenant RLS policies with transaction-local context, negative CRUD
  and pool-leakage tests, runtime role posture checks, and role grant templates.
- Optional OpenTelemetry API/worker traces and redacting local/production
  Collector configurations.
- Batched retention with legal hold and execution audit, plus isolated writable
  restore rehearsal with runtime grants and post-restore RLS probes.
- Fail-closed production readiness checks and one-shot migrations separated
  from non-root API/worker containers.

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

- Configure real OIDC, GitHub App, SMTP, HTTPS/WAF, managed secrets, distributed
  rate limits, durable telemetry, encrypted backup storage, alerts, and on-call.
- Schedule retention and backup jobs, export audits to immutable storage, and
  complete a recorded restore rehearsal against the target environment/RPO/RTO.
- Notifications, invitations, and normalized event ingestion remain
  synchronous until each producer receives a provider-specific reliability review.
