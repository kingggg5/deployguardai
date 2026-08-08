# Changelog

All notable changes to DeployGuard AI are documented here. The project follows
release notes from `main` and will use semantic versioning for tagged releases.

## [Unreleased]

### Added

- DeployGuard Verify v0.1: a standalone, zero-LLM-key CLI and composite GitHub
  Action that imports JUnit, Cobertura/LCOV, SARIF, and build status into a
  protected-base-policy, exact-SHA, canonical evidence receipt with stable
  PASS/REVIEW/BLOCK/ERROR exit codes.
- An optional `deployguard-change-safety` Skill and `deployguard init` scaffolder
  for GitHub workflows and concise `AGENTS.md` guidance. Agent prose remains
  non-authoritative and cannot override the deterministic receipt.
- DeployGuard Bench v0.1 foundation with a versioned operational-example schema,
  deterministic synthetic exporter, provenance and eligibility rules,
  reproducible dataset artifacts, contract tests, and CI drift checks.
- Citation-gated deterministic incident explanations with a versioned evidence
  contract, evidence-bundle hash, uncertainty, validation, and audit metadata.
- Cross-platform local development commands, a `make demo` entry point, and CI
  coverage reports/floors for backend and frontend suites.
- An explicit AI-boundary document and a dependency-ordered public roadmap.
- Three-minute connected and isolated demo quickstarts, a polished English/Thai
  project overview, and a real dashboard screenshot for repository discovery.
- A tag-driven GHCR release workflow that reuses CI, publishes signed
  `linux/amd64` and `linux/arm64` API/web images, and records SBOM/provenance
  attestations.
- A release checklist covering version tags, image digests, evaluation evidence,
  restore rehearsal, and rollback.
- An issue form for configuration and operations questions, with explicit
  secret-redaction guidance.
- An explicit Angular Router peer dependency and a Dependabot guard that keeps
  TypeScript major upgrades out of the Angular 22 toolchain queue.
- Current GitHub Actions and CodeQL/Scorecard runners, plus the latest Nginx
  Alpine base image for the web container, with exact Node/Python/Nginx patch
  tags for reproducible container builds.
- A production-shaped ASP.NET Core 10 control plane with native fail-closed
  liveness/readiness, PostgreSQL and upstream probes, bounded request IDs,
  transparent YARP compatibility routing, non-root container, and integration
  tests. Python remains the deterministic engine authority because the
  same-workload microbenchmark did not justify a C# engine rewrite.
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

- Connected GitHub pull-request metadata now records test, rollback,
  observability, and failure-history evidence as unknown instead of fabricated
  zero/false sentinels. Metadata-only GitHub App Checks remain neutral until an
  authenticated, SHA-matched receipt ingestion path exists.
- ASP.NET Core forwarded-header trust is bound and validated through runtime
  Options, requires symmetric proxy chains, and is regression-tested so YARP
  replaces inbound headers with the single resolved client identity.
- Consolidated duplicated user, telemetry, evaluation, and release guidance
  into the maintained README, contract, benchmark, security, contribution, and
  operations documents.
- Public API traffic now enters through .NET 10 while FastAPI runs as an
  internal compatibility/application service; Alembic remains the sole schema
  migration authority and PostgreSQL remains the production source of truth.
- Project positioning now makes the operational-data -> evidence-graph ->
  dataset architecture explicit and treats AI/LLMs as downstream consumers.
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
