---
version: 1
slug: "frontend-src-app-app-ts"
primary_target: "frontend/src/app/app.ts"
related_targets: ["frontend/src/app/app.html","frontend/src/styles.scss","frontend/src/app/layout/scope-switcher/scope-switcher.component.ts","frontend/src/app/layout/command-palette/command-palette.component.ts","frontend/src/app/features/dora/dora-dashboard.component.ts","frontend/src/app/features/scenario-lab/scenario-lab.component.ts","frontend/src/app/features/workspace-setup/workspace-setup.component.ts"]
---

## Scope and mode

Primary DeployGuard web workspace. Mode: Operate.

## Audience, job, and action

Platform engineers and incident responders need to select the correct repository, trace a change through risk, service impact, evidence, ranked hypotheses, and a human verdict under time pressure. Primary actions are switching repository scope, opening commands, inspecting evidence, replaying the incident, recording a verdict, exporting a post-mortem, sharing the current deep link, and running a deterministic change analysis.

## Proof and constraints

All factual content comes from the typed API. Synthetic scenarios and repositories remain visibly labeled. Deep links never grant access. No autonomous remediation, deploy, rollback, customer claims, fake workspace/invite controls, or implied LLM certainty.

## Direction and memorable moment

An investigation cockpit with a narrow command rail, repository scope switcher, searchable command center, a dominant registered topology beside an evidence ledger, then replay, hypotheses, and verdict as one closing loop. Evidence X-ray changes annotations without moving graph geometry.

## Unresolved decisions

Development identity, tenant-isolated workspace management, server-enforced roles, repository fixtures, secure local invitations, and audit events are implemented. Production OIDC, live GitHub data, email delivery, and OpenTelemetry connection states remain credential-gated and must not appear as connected.
