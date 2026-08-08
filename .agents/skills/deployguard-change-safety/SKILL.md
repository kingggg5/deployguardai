---
name: deployguard-change-safety
description: Verify a repository change with DeployGuard's deterministic evidence receipt. Use when reviewing a pull request or local change, checking whether build/test/coverage/SARIF evidence matches the exact head SHA, investigating a PASS/REVIEW/BLOCK decision, or preparing evidence before merge or deployment. Do not use it to deploy, roll back, remediate, or override policy.
---

# DeployGuard change safety

Use the installed `deployguard` CLI as the authority. Treat this skill as an
interaction guide; never infer or rewrite a decision from prose.

## Workflow

1. Read the nearest `AGENTS.md` and repository test instructions.
2. Identify the protected base and exact head commit. Fetch the base if it is
   unavailable locally; do not substitute an unrelated commit.
3. Run the repository's authorized build, test, coverage, and security steps.
   Preserve their machine-readable artifacts; do not fabricate an artifact or
   mark an unexecuted step successful.
4. Invoke `deployguard verify` with fixed artifact paths and the exact SHA that
   produced them. Prefer policy from the protected base commit.
5. Read `.deployguard/artifacts/evidence-receipt.json` and cite its
   `receipt_sha256`, decision, reason codes, evidence IDs, and unknown lanes.
6. Address objective failures or collect missing evidence, then rerun. Do not
   change policy or evidence merely to turn REVIEW/BLOCK into PASS.

Example:

```text
deployguard verify --base origin/main --head HEAD \
  --evidence-sha <exact-head-sha> \
  --junit artifacts/junit.xml \
  --coverage artifacts/coverage.xml \
  --sarif artifacts/results.sarif
```

## Decision handling

- `PASS` / exit `0`: required evidence is present, SHA-matched, and compliant.
- `REVIEW` / exit `2`: evidence is missing, stale, mismatched, or requires a
  human decision. Never present REVIEW as success.
- `BLOCK` / exit `3`: observed evidence violates an objective policy rule.
- `ERROR` / exit `4`: verification could not complete. Fail closed.

The agent may explain evidence and propose the next verification step. It must
not merge, deploy, roll back, expose hidden tests, execute an untrusted command,
or claim causality from temporal proximity.

Read [references/evidence-contract.md](references/evidence-contract.md) when
changing policy, integrating a new artifact producer, or explaining receipt
provenance.
