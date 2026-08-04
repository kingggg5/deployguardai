# Evidence synthesis and AI boundary

DeployGuard's supported decision path is deterministic. Explicit, versioned
policy and stored evidence drive change risk, blast radius, ranked hypotheses,
and readable incident explanations.

## What ships now

- `POST /api/v1/incidents/{incident_id}/synthesize` returns a deterministic,
  evidence-grounded explanation.
- Every statement cites stored evidence IDs. Unknown, empty, cross-incident, or
  unrelated citations are rejected before a response is returned.
- The response includes contract and validator versions, evidence-bundle
  SHA-256, uncertainty, and citation coverage.
- Tenant scope and safe audit metadata are enforced without persisting raw
  prompts or credentials.
- Human verdicts capture server-owned actor provenance and a structured
  verification outcome.
- Resolved connected incidents can create immutable, content-addressed
  postmortem snapshots and append-only, purpose-specific consent decisions.
- The browser receives no provider credentials and the service calls no
  external model.

## Relationship to DeployGuard Bench

Operational inputs become a provenance-preserving evidence graph. Human review
adds accountable ground truth. Dataset governance can mark an exact snapshot
`ready_for_review` for evaluation or training.

That status is not an export authorization. The connected-data exporter is
hard-disabled. Only repository-owned synthetic fixtures can currently be
exported into [DeployGuard Bench](../bench/README.md).

The capture and consent gates are implemented; the publication pipeline is not.
Connected publication still requires deterministic redaction, source license
and retention inventory, leakage review, immutable release registration,
revocation propagation, independent approval, and frozen dataset splits.

## What does not ship

There is no configured OpenAI or other external-model provider, outbound model
request, public real-world dataset, fine-tuning pipeline, or autonomous action.
The system cannot deploy, roll back, run commands, write files, or change
infrastructure.

## Gate for an optional external provider

An external provider may be considered only after all of the following are
implemented and reviewed:

1. Server-only secret management and approved outbound network egress.
2. Tenant-scoped evidence selection, deterministic secret/PII redaction,
   retention policy, and documented provider region/data-use terms.
3. Typed output restricted to existing hypotheses and evidence IDs, followed by
   the current citation validator.
4. Prompt-injection, missing-citation, cross-tenant, timeout, and provider
   failure tests with deterministic fallback or an explicit unavailable state.
5. Audit metadata for model, prompt revision, evidence-bundle hash, validator,
   latency, and cost without raw prompts or credentials.
6. A blinded evaluation demonstrating a material groundedness or usability
   benefit over the deterministic baseline within fixed cost and latency limits.
7. A frozen DeployGuard Bench split that was not used for prompt development or
   training, plus per-task failure slices and contamination review.

Until these gates pass, the deterministic baseline is the only supported
explanation path and must not be marketed as an external LLM integration.
