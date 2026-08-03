---
version: 1
slug: "frontend-src-app-app-ts"
primary_target: "frontend/src/app/app.ts"
related_targets: ["frontend/src/app/app.html","frontend/src/app/app.scss","frontend/src/styles.scss","frontend/src/app/layout/scope-switcher/scope-switcher.component.ts","frontend/src/app/layout/command-palette/command-palette.component.ts","frontend/src/app/features/dora/dora-dashboard.component.ts","frontend/src/app/features/scenario-lab/scenario-lab.component.ts","frontend/src/app/features/workspace-setup/workspace-setup.component.ts","frontend/src/app/features/operations/operations-center.component.ts"]
---

## Scope and mode

Primary DeployGuard repository workspace. Mode: Operate. This redesign replaces the investigation cockpit visual world with a GitHub/Primer-inspired repository evidence room while retaining DeployGuard branding and domain behavior.

## Audience, job, and action

Platform engineers, SREs, incident commanders, and engineering managers must confirm the current workspace and repository, assess change risk, trace blast radius, compare evidence and counter-evidence, coordinate incidents, and record human decisions. Primary actions are repository selection, command search, change analysis, evidence inspection, timeline replay, incident coordination, workspace setup, and sharing a scoped deep link.

## Proof and constraints

All factual content comes from typed APIs. Connected, synthetic, waiting, and unavailable states remain visibly labelled. Deep links preserve context but never grant access. No autonomous remediation, deploy, rollback, shell execution, fake provider success, invented customers, or implied LLM certainty.

## Direction and memorable moment

A repository-native shell with a compact global header, visible owner/repository scope, explicit data-origin and connection labels, and a horizontal underlined product navigation. Each product area uses issue-style ledgers, tables, timelines, split inspectors, and bordered forms instead of floating card walls. The memorable moment is moving from a selected change to its graph, evidence chain, ranked hypotheses, and human verdict without losing repository context.

## Responsive and interaction behavior

At desktop widths, the 1280px content container supports a primary ledger and narrower inspector. Under 900px, secondary inspectors stack. Under 680px, global controls collapse, repository navigation scrolls horizontally, and every actionable target reaches at least 44px. Keyboard focus, reduced motion, error recovery, empty states, and bilingual English/Thai copy remain first-class.

## Unresolved decisions

Production OIDC, GitHub App, SMTP, and telemetry remain credential-gated. Native OpenTelemetry receiver packaging, durable webhook queueing, rate limiting, production secret management, and evaluation dashboards remain prioritized follow-up work and must not be represented as complete.
