# Evidence contract

DeployGuard Verify accepts evidence produced outside the verifier and records
only normalized counts, hashes, source paths, and the source commit SHA. It does
not store test logs, SARIF messages, source snippets, credentials, or prompts.

Supported v0.1 inputs:

| Kind | Accepted input | Required provenance |
| --- | --- | --- |
| Tests | JUnit XML | Exact producing commit SHA |
| Coverage | Cobertura XML or LCOV | Exact producing commit SHA |
| Security | SARIF 2.1.0 | Exact producing commit SHA |
| Build | Explicit success/failure from the current CI job | Exact producing commit SHA |

The canonical receipt includes base, head, merge base, protected-base policy
hash, changed paths, normalized evidence, decision reasons, and its SHA-256.
Commit time is used as deterministic `generated_at`; rerunning with identical
inputs must produce identical bytes.

Policy rules come from `.deployguard/policy.yml` at the protected base commit by
default. A pull request must not be able to weaken the gate by modifying its own
policy. Working-tree policy is allowed only for local policy development and is
identified explicitly in the receipt.

Interpretation rules:

- Never convert absent or SHA-mismatched evidence to zero or pass.
- An observed test/build failure or policy-blocking SARIF severity is BLOCK.
- Missing required evidence is REVIEW.
- Risk score and merge decision are separate concepts.
- Skill or agent output cannot change the receipt decision.
- Production incidents are correlation until evidence and an accountable human
  verdict establish the outcome.
