# DeployGuard AI roadmap

This roadmap is ordered by dependency and operational risk. “Implemented” means
the repository contains a runtime path and automated coverage; it does not mean
every production environment is configured or independently certified.

## Capability map

| Capability | Status | Current truth |
| --- | --- | --- |
| DeployGuard Verify | Implemented | Keyless CLI/Action, protected-base policy, exact-SHA JUnit/Coverage/SARIF evidence, canonical receipt, stable decisions |
| Connected receipt ingestion | Planned | GitHub App Check remains neutral until an authenticated/attested receipt path exists |
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
| .NET 10 public control plane | Implemented | Native fail-closed health/readiness and full compatibility routing; domain slices migrate only after parity gates |

## P0 — Close the change outcome loop

1. Ship and self-dogfood the versioned `DeployGuard Verify` Action, publish a
   pinned release, and prove 10/10 byte-identical receipt replay.
2. Ingest authenticated/attested receipts without accepting arbitrary commands
   or trusting policy from the pull-request head.
3. Publish PASS/REVIEW/BLOCK through the GitHub App only from an accepted
   receipt; keep metadata-only analysis neutral.
4. Link exact deployed SHA to explicit outcomes: `stable_window_met`, `failed`,
   `rolled_back`, `incident_linked`, or `unknown`, with human confirmation.

## P1 — Close the connected-data safety loop

1. Build deterministic secret, PII, customer-data, and tenant-identifier
   redaction with inspectable review artifacts.
2. Add a source license/retention inventory and publication approval workflow.
3. Create an immutable dataset release registry and propagate consent revocation
   as tombstones to every derived bundle.
4. Add deduplication, contamination, and train/test leakage checks before any
   record can leave `ready_for_review`.
5. Verify migration `0011`, RLS, and immutability triggers on a real PostgreSQL
   16 non-owner role in CI and a reference environment.

## P2 — Make connected operations easier

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

## P3 — Build a credible benchmark

1. Collect the first consented operational corpus under the P1 publication
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

## Runtime migration

ASP.NET Core 10 is the public control-plane entry point. FastAPI is an internal
compatibility/application service and Python remains the deterministic risk and
evidence engine. PostgreSQL is the production source of truth; Alembic stays the
only schema migration authority during coexistence.

Domain routes move to native .NET vertical slices only after real HTTP contract,
authentication/RBAC, PostgreSQL RLS, pooled-connection isolation, idempotency,
failure-mode, and observability parity. Measure HTTP/PostgreSQL throughput,
tail latency, memory, and error rate before each cutover. The old engine-only
microbenchmark did not show a C# performance benefit, so duplicating the Python
engine is explicitly out of scope.

## Definition of done

A capability is complete only when its contract is typed, authorization and
tenant boundaries are explicit, negative/security tests exist, migrations and
rollback are documented, observability is useful, operator failure modes are
described, and the UI never presents synthetic data or readiness as production
truth.
