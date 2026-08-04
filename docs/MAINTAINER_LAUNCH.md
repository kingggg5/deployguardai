# Maintainer launch checklist

This repository is ready to prepare for a public preview after the release
checks pass. The items below require repository-owner action and are not
performed automatically by application code.

## GitHub repository metadata

Choose **one** canonical repository before publishing a preview. The current
`deployguard` and `deployguardai` repositories are both public and have
independent Dependabot queues, so treating both as release authorities risks
divergent artifacts and duplicate security triage. This documentation, CI
badges, image names, and release workflow use `kingggg5/deployguardai`; keep
that as the canonical project, then archive the other repository or document
it as a read-only mirror after maintainers agree.

Set the repository description to:

> Evidence-first change-risk analysis and incident investigation for platform and SRE teams.

Suggested topics:

`devops`, `devsecops`, `sre`, `incident-response`, `deployment`,
`risk-analysis`, `observability`, `github-app`, `fastapi`, `angular`,
`platform-engineering`, `open-source`.

Add a project website only after it is a maintained, public documentation or
demo URL. Do not point visitors to a personal or unstable preview.

## v0.1.0 public-preview release

The release branch must be merged and the full CI run must be green before
tagging. Use the prepared [v0.1.0 release notes](release-notes/v0.1.0.md) as a
draft, update its commit/digest fields from CI, then follow
[RELEASE.md](RELEASE.md). A tag or release should never be created just to make
the repository look active.

## Real contributor backlog

Create issues only when a maintainer is ready to own and review them. The
backlog below is deliberately concrete; it is not a request to inflate issue
count or imply work has started.

| Priority | Issue title | Labels | Done when |
| --- | --- | --- | --- |
| P0 | Capture four verified product screenshots and a 20–40 second demo | `documentation`, `good first issue` | Assets show Dashboard, change risk, investigation timeline, and evidence/hypothesis flow using a clearly labelled synthetic dataset. |
| P0 | Run a credentialed GitHub App sandbox contract test | `integration`, `security`, `needs-maintainer` | A disposable GitHub sandbox verifies webhook signature, repository sync, Check publication, and cleanup; no credentials enter CI logs. |
| P0 | Define provider-redaction test corpus for evidence synthesis | `security`, `ai-safety`, `testing` | Corpus covers injection, secret-like fields, unknown citations, cross-tenant references, and timeout/failure paths. |
| P1 | Add a native OTLP Collector-to-evidence mapping | `observability`, `backend`, `design` | Authenticated mappings preserve tenant provenance and cardinality limits with integration tests. |
| P1 | Publish benchmark data-selection and licensing decision | `evaluation`, `documentation` | A selected public dataset is version-pinned, license-reviewed, checksummed, and kept separate from product claims. |
| P1 | Add a distributed rate-limit adapter contract | `security`, `backend`, `help wanted` | Interface, Redis/gateway reference implementation, and multi-replica tests are documented without making a managed-service assumption. |
| P1 | Record an operational dashboard and alert ownership template | `operations`, `documentation` | SLO/alert examples define owner, severity, response target, and deployment substitutions without claiming hosted monitoring. |
| P2 | Add an accessible keyboard task study for incident investigation | `accessibility`, `frontend`, `research` | Findings include keyboard-only task completion, screen-reader checks, and tracked fixes. |
| P2 | Evaluate optional external-provider synthesis against the baseline | `ai-safety`, `evaluation`, `needs-maintainer` | Blinded rubric, cost/latency budget, redaction review, and citation-validation results meet the AI-boundary gate. |

## Dependabot review policy

Triage each pull request with its own CI run and dependency release notes.
Patch/minor updates may be merged after the relevant workflow passes. Major
runtime, Angular, TypeScript, Node, Python-base-image, or GitHub Action updates
need a compatibility issue or explicit review; do not merge them merely to
clear the queue.
