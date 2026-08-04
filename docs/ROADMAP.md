# DeployGuard AI roadmap

This roadmap is ordered by dependency and operational risk. “Implemented” means
the repository contains a runtime path and automated coverage; it does not mean
every production environment is configured or independently certified.

## Capability map

| Capability | Status | Current truth |
| --- | --- | --- |
| Deterministic change risk and blast radius | Implemented | Explicit scoring dimensions, versioned policy, cycle-safe traversal |
| Incident evidence, RCA, and lifecycle | Implemented | Timeline, evidence/counter-evidence, hypotheses, assignments, notes, notifications |
| Human verdict governance | Implemented | Server-owned actor provenance and structured verification outcome |
| Postmortem and consent governance | Implemented | Immutable content-addressed snapshots, append-only purpose-specific consent, readiness gate |
| Workspace, RBAC, and PostgreSQL RLS | Implemented | Viewer/responder/admin/owner roles and negative tenant-isolation tests |
| Durable GitHub provider workflow | Environment-gated | GitHub App, signed webhook, Check Runs, outbox, retry, DLQ, trace propagation |
| OIDC and SMTP | Environment-gated | Runtime paths exist; operators must configure providers and secrets |
| Normalized telemetry ingestion | Environment-gated | Tenant-scoped normalized contract; not a native OTLP receiver |
| Backup, restore, and retention helpers | Implemented | Restore rehearsal, batched retention, legal hold, deletion audit; scheduling/storage external |
| DeployGuard Bench synthetic foundation | Implemented | Schema, deterministic exporter, 3 synthetic examples, manifest, CI drift check |
| Connected-data export/publication | Planned | Exporter remains closed; redaction, review, registry, and revocation propagation absent |
| Public real-world benchmark | Planned | No consented corpus, hidden test split, independent annotation, or leaderboard |
| External LLM provider | Deferred | Requires redaction, security, blinded evaluation, and frozen benchmark first |
| Native OTLP gateway | Planned | Requires authenticated Collector mapping, quotas, and normalization policy |
| Slack/Teams/PagerDuty | Planned | No arbitrary outbound webhook path is currently bundled |
| Hosted public demo | Planned | Requires isolated tenancy, abuse protection, cost limits, and resettable synthetic data |
| .NET 10 read-only parity spike | Environment-gated | Read-only parity exists; no measured reason to replace the production authority yet |

## P0 — Close the connected-data safety loop

1. Build deterministic secret, PII, customer-data, and tenant-identifier
   redaction with inspectable review artifacts.
2. Add a source license/retention inventory and publication approval workflow.
3. Create an immutable dataset release registry and propagate consent revocation
   as tombstones to every derived bundle.
4. Add deduplication, contamination, and train/test leakage checks before any
   record can leave `ready_for_review`.
5. Verify migration `0010`, RLS, and immutability triggers on a real PostgreSQL
   16 non-owner role in CI and a reference environment.

## P1 — Make connected operations easier

1. Native OTLP gateway with authenticated Collector mapping, allow-listed
   attributes, cardinality limits, and redaction before persistence.
2. Slack/Teams/PagerDuty adapters through the durable outbox with allow-listed
   destinations, idempotency, retry, and auditable delivery state.
3. SLO/error-budget dashboards backed by connected deployment and incident
   evidence, not placeholder metrics.
4. Search, saved views, and evidence filters that remain tenant-scoped and
   preserve source provenance.
5. Scheduled retention, backup storage ownership, restore alerts, and
   multi-replica rate limiting.

## P2 — Build a credible benchmark

1. Collect the first consented operational corpus under the P0 publication
   controls; current connected count is zero.
2. Add annotation, adjudication, inter-rater agreement, and quality sampling.
3. Freeze train, validation, public-test, and hidden-test splits with leakage
   controls and versioned dataset cards.
4. Publish deterministic and model baselines with calibration, failure slices,
   cost, latency, and abstention metrics.
5. Measure production usefulness separately: investigation time, evidence
   coverage, verdict reversals, and reviewer trust.

The 1,000 deployment-scenario and 500 incident-investigation target remains a
long-term corpus goal. Quality, consent, and independent review take priority
over example count.

## Deferred — External LLM

Do not add an external model call until the evidence-only contract, redaction,
frozen evaluation split, prompt-injection tests, cost/latency limits, and blinded
comparison show a measurable improvement over the deterministic baseline. AI
remains a consumer of the evidence graph, never the owner of ground truth.

## Runtime decision

FastAPI remains the production authority. The .NET 10 spike is a read-only
parity and operational measurement track. A migration should occur only if full
OpenAPI, security/RLS, golden-corpus, performance, and operational parity are
proven and the measured benefit exceeds the migration and split-runtime cost.

## Definition of done

A capability is complete only when its contract is typed, authorization and
tenant boundaries are explicit, negative/security tests exist, migrations and
rollback are documented, observability is useful, operator failure modes are
described, and the UI never presents synthetic data or readiness as production
truth.
