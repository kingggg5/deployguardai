# DeployGuard Bench

DeployGuard Bench is the dataset and evaluation layer of DeployGuard AI. It
models production-engineering reasoning as an inspectable chain from a change
to evidence, verification, and a human decision.

```text
Operational data -> Evidence graph -> Human review -> Dataset governance -> Consumers
```

AI is a consumer of this contract. It does not own evidence, scores, ground
truth, or human verdicts.

## Current release

This repository ships an **incubating synthetic seed**, not a production LLM
dataset or public benchmark:

- 3 deployment-to-incident examples generated from repository scenarios;
- 2 examples eligible for development evaluation;
- 1 unverified example excluded from accuracy denominators;
- 0 examples approved for model training;
- deterministic JSONL, JSON Schema, per-example SHA-256, dataset SHA-256,
  provenance, license, eligibility, and limitations.

The target of 1,000 deployment scenarios and 500 incident investigations is a
roadmap target, not a current dataset-size claim.

## Operational example contract

An example can contain:

```text
Deployment
  -> service topology
  -> incident timeline
  -> supporting evidence and counter-evidence
  -> ranked hypotheses
  -> ground truth and label source
  -> human verdict with actor provenance
  -> structured verification outcome and cited evidence IDs
  -> immutable postmortem snapshot
  -> purpose-specific consent provenance
```

The public contract stores a pseudonymous `actor_ref`; provider subjects and
email addresses are not part of the dataset schema. Consent refers to an exact
snapshot hash and purpose. Revocation is a new append-only decision, never an
edit to the prior decision.

Schema: [`schema/operational-example-v1.schema.json`](schema/operational-example-v1.schema.json)

Synthetic bundle: [`datasets/synthetic-v0.1`](datasets/synthetic-v0.1)

Initial evaluation tasks are:

1. root-cause ranking;
2. citation-grounded explanation;
3. counter-evidence sensitivity;
4. next-verification planning;
5. deployment-risk analysis once outcome labels are available.

## Reproduce the bundle

```bash
python scripts/export_operational_dataset.py \
  --output-dir .runtime/deployguard-bench

python scripts/export_operational_dataset.py \
  --check --output-dir bench/datasets/synthetic-v0.1
```

The first command builds a local bundle. The second fails when the committed
dataset drifts from the ranker, scenarios, schema, or manifest hashes. `make
bench` runs the engine benchmark and dataset drift check on systems with GNU
Make.

## Ground-truth policy

A record may enter evaluation only when its label source is explicit:

- `scenario_author` for transparent synthetic development data;
- `public_dataset_label` for a license-reviewed external benchmark;
- `human_verdict` for a consented, reviewed operational export.

Unverified records remain useful for annotation but do not enter accuracy
denominators. Synthetic labels must never be presented as real engineer
decisions. Public test records must not become training data.

## Connected-data promotion boundary

The runtime now captures the first governance layer for connected incidents:

1. incident is connected and resolved;
2. verdict is attributed to an authenticated actor;
3. verification records result, method, summary, and evidence IDs;
4. a content-addressed postmortem snapshot is made immutable in storage;
5. an administrator records an audited decision for the exact snapshot and
   `evaluation` or `training` purpose;
6. consent attestations cover workspace authorization, secret review, privacy
   review, and source-license review.

This yields only `ready_for_review`. The connected-data exporter remains
hard-disabled. The current exporter reads repository-owned synthetic fixtures
only and has no database, GitHub, telemetry, or connected-workspace input mode.

Before any connected publication, the project still needs:

- deterministic secret, PII, customer-data, and tenant-identifier redaction;
- review artifacts and source license/retention inventory;
- deduplication, contamination, and train/test leakage checks;
- immutable release registry and revocation/tombstone propagation;
- annotation, adjudication, inter-rater agreement, and quality sampling;
- independent publication approval and frozen train/validation/hidden-test
  policies.

Human attestations are not proof that automated redaction succeeded. Raw
prompts, credentials, private source content, customer payloads, and unredacted
telemetry stay outside the public contract.

## Repository strategy

DeployGuard Bench remains in this repository so schema, engines, exporter, and
CI cannot drift independently. Split it into a dedicated repository only after
the v1 contract is stable, licensing is reviewed, at least 100 examples pass
independent quality review, and the dataset needs a separate release cadence or
maintainer group.
