# Evidence synthesis and AI boundary

DeployGuard's decision engines are deterministic. They calculate change risk,
blast radius, and ranked hypotheses from explicit policy and stored evidence.
The incident explanation endpoint is deliberately narrower: it creates a
readable, evidence-grounded explanation from those existing records without
inventing facts.

## What ships now

- `POST /api/v1/incidents/{incident_id}/synthesize` returns a deterministic
  evidence explanation.
- Every statement has one or more evidence IDs. The citation validator rejects
  an empty, unknown, or cross-incident reference before a response is returned.
- The response includes its contract version, validator version, evidence-bundle
  SHA-256, uncertainty, and citation coverage.
- Generation is tenant-scoped and audited without persisting raw evidence in the
  audit metadata.
- The browser can request the explanation, but it never receives provider
  credentials and the service does not call an external model.

This baseline is useful by itself: it gives an engineer a concise reading of
the current evidence, preserves traceability, and establishes the acceptance
contract that any future language model must satisfy.

## What does not ship

There is no configured OpenAI or other external-model provider, no outbound
model request, no prompt containing credentials, and no autonomous action. The
feature cannot deploy, roll back, run commands, write files, call GitHub, or
change infrastructure.

## Gate for an optional external provider

An external provider may be considered only after all of the following are
implemented and reviewed:

1. Server-only secret management and approved outbound network egress.
2. Tenant-scoped evidence selection, secret/PII redaction, retention policy,
   and a documented provider region/data-use policy.
3. Typed output restricted to the existing candidate hypotheses and evidence
   IDs, with the same validator run after model output.
4. Prompt-injection, missing-citation, cross-tenant, timeout, and provider
   failure tests. Failure must return the deterministic baseline or an explicit
   unavailable state, never fabricated text.
5. Audit metadata for model, prompt revision, evidence-bundle hash, validator,
   latency, and cost—without storing raw prompts or credentials in the audit
   event.
6. A blinded evaluation showing a material usability or groundedness benefit
   over the deterministic baseline within a fixed cost and latency budget.

Until those gates are passed, the deterministic baseline is the supported
explanation path and should not be marketed as an external LLM integration.
