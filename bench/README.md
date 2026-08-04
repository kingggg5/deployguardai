# DeployGuard Bench

DeployGuard Bench is the dataset and evaluation layer of DeployGuard AI. Its
goal is to make production-engineering reasoning measurable from an inspectable
chain of deployments, operational evidence, hypotheses, verification, and
human decisions.

```text
Operational data              Evidence graph                 Dataset consumers
GitHub / OTel / Prometheus  -> provenance + counter-evidence -> benchmarks / LLMs
```

AI is a consumer of this data contract. It does not own the evidence, ground
truth, risk score, or human verdict.

## Current release

The repository currently ships an **incubating synthetic seed**, not the final
benchmark:

- 3 rich deployment-to-incident examples generated from the product scenarios;
- 2 examples with scenario-author ground truth, reserved for development
  evaluation;
- 1 unverified example that cannot contribute to accuracy metrics;
- 0 examples approved for model training;
- deterministic JSONL, per-example SHA-256, dataset SHA-256, provenance, license,
  eligibility, and explicit limitations.

The target corpus is **1,000 deployment scenarios and 500 incident
investigations**, with held-out splits and independent review. These numbers are
a roadmap target, not a current dataset-size claim.

## Example contract

Every operational example can represent:

```text
Deployment
  -> service topology
  -> incident timeline
  -> supporting evidence and counter-evidence
  -> ranked hypotheses
  -> ground truth and label source
  -> verification steps and observed outcome
  -> human verdict
  -> postmortem
```

The versioned JSON Schema is
[`schema/operational-example-v1.schema.json`](schema/operational-example-v1.schema.json).
The checked-in synthetic bundle is under
[`datasets/synthetic-v0.1`](datasets/synthetic-v0.1).

Initial evaluation tasks are:

1. root-cause ranking;
2. evidence-grounded explanation with valid citations;
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

The first command builds a local bundle. The second fails if the committed
dataset differs from the production ranker, source scenarios, schema, or
manifest hashes. On systems with GNU Make, `make bench` runs the engine benchmark
and the dataset drift check together.

## Ground-truth policy

A record may be used for evaluation only when its label source is explicit:

- `scenario_author` for transparent synthetic development data;
- `public_dataset_label` for a license-reviewed external benchmark;
- `human_verdict` for a consented and reviewed operational export.

Unverified records remain useful for annotation but must not enter accuracy
denominators. Synthetic author labels must never be presented as real engineer
decisions. Public test records must not be reused as training data.

## Privacy and publication boundary

The current exporter accepts only repository-owned synthetic scenarios. It has
no database, GitHub, telemetry, or connected-workspace input mode.

A real incident is only a **candidate example**. It must not automatically
become public or training data. A future connected-data pipeline requires all
of the following before export:

1. workspace-level opt-in and a revocable data-use agreement;
2. secret, PII, customer, repository, and tenant-identifier redaction;
3. license and retention metadata for every source;
4. a resolved incident, evidence provenance, and an attributable human verdict;
5. reviewer approval, leakage/deduplication checks, and immutable dataset version;
6. separate train, validation, and hidden test policies.

Raw prompts, credentials, private repository content, customer payloads, and
unredacted telemetry are outside the public dataset contract.

## Repository strategy

DeployGuard Bench is incubated in this repository so schema, exporter, engine,
and CI cannot drift independently. Split it into a dedicated repository only
after the v1 contract is stable, licensing is reviewed, at least 100 examples
have passed independent quality review, and the dataset needs its own release
cadence or maintainer group.

Until then, opening another mostly empty repository would fragment governance
without improving the benchmark.
