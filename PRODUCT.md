# DeployGuard AI

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- Platform engineers and SREs reviewing a change before deployment.
- Incident commanders and on-call engineers investigating a production incident.
- Engineering managers evaluating operational risk, evidence quality, and learning outcomes.
- Hiring reviewers using the demo and benchmark artifacts to assess the builder's systems, AI, data, and product-engineering skills.

## Product Purpose

DeployGuard AI connects code changes, service dependencies, deployments, telemetry evidence, and incidents in one inspectable workflow. It helps teams estimate change risk before deployment, understand likely blast radius, and rank root-cause hypotheses after an incident without presenting an LLM guess as fact.

Success means a user can move from a change to its affected services, incident timeline, evidence, counter-evidence, and next verification step in a few minutes.

## Positioning

The product's distinctive mechanism is a closed evidence loop:

`change → risk → blast radius → runtime impact → incident hypotheses → human verdict`

Every risk dimension and root-cause hypothesis is traceable to evidence, exposes uncertainty, and can be corrected by a human. Deterministic analysis owns scoring and graph traversal; language models may later summarize bounded evidence but never silently invent causes or execute remediation.

## Operating Context

- Multi-tenant repository workspace for platform, reliability, and incident-response teams.
- Connected GitHub pull-request and deployment metadata through a verified GitHub App.
- Authenticated normalized telemetry events with explicit provenance; native OTLP gateway packaging remains follow-up work.
- Service dependency graphs and temporal incident evidence.
- High-pressure investigation where fast scanning, clear uncertainty, and reversible actions matter.
- Explicitly labelled synthetic scenarios for deterministic evaluation, disabled by default in a fresh runtime.

## Capabilities and Constraints

### MVP capabilities

- Analyze a GitHub-style change with a multi-dimensional, deterministic risk score.
- Calculate a dependency-based blast radius from changed services.
- Present deployment and incident events on a shared timeline.
- Rank three root-cause hypotheses with supporting evidence, counter-evidence, confidence, and a next verification step.
- Capture human confirmation, rejection, or partial-cause feedback.
- Run seeded, reproducible scenarios without external credentials.
- Switch between repository-backed synthetic scenarios from a searchable scope selector.
- Open existing product actions through a keyboard command center and copy the current view as a deep link.
- Persist local state in SQLite and support PostgreSQL through configuration and migrations.
- Create tenant workspaces, connect verified GitHub repositories, invite members, enforce workspace roles, and inspect audit events. Development substitutes appear only when the configured environment explicitly enables them.
- Operate through a repository-native UI with global search, visible workspace/repository scope, responsive navigation, settings-style operations, and bilingual English/Thai copy.

### Constraints

- Initial scenarios and telemetry are synthetic and must always be labeled as such.
- Production OIDC verification, GitHub App repository discovery, and SMTP invitation delivery are implemented and remain credential-gated. Connected OpenTelemetry ingestion requires its configured token. Local substitutes are visibly labelled development providers.
- Copied view links preserve UI scope only and never grant access or act as anonymous invitations.
- The system does not run shell commands, deploy code, roll back releases, or remediate infrastructure.
- Risk scores are decision support, not deployment authorization.
- LLM synthesis is deliberately deferred until the deterministic evidence contract and evaluation harness are stable.

## Brand Commitments

- Product name: DeployGuard AI
- Voice: calm, exact, evidence-first, and free of autonomous-AI hype.
- Product language prefers “hypothesis”, “evidence”, “counter-evidence”, “uncertainty”, and “verify next” over claims of certainty.
- Interaction language is familiar to repository users, but DeployGuard does not copy GitHub branding or product assets.

## Evidence on Hand

- A product and research plan established in the project conversation.
- Public evaluation and integration candidates: RCAEval, OpenRCA, OpenTelemetry Demo, Grafana LGTM, and GitHub webhooks.
- No customer logos, production accuracy claims, paid-plan claims, or private incident data are available; the product must not fabricate them.

## Product Principles

1. Show the evidence chain, not only the answer.
2. Make uncertainty visible and actionable.
3. Prefer deterministic, testable analysis before generative synthesis.
4. Keep every action reversible and human-controlled.
5. Make the demo reproducible from a clean checkout.

## Accessibility & Inclusion

- Meet WCAG 2.2 AA contrast and keyboard access for the primary investigation workflow.
- Do not rely on color alone for risk or hypothesis state.
- Respect reduced-motion preferences.
- Support both English product terminology and readable Thai documentation.
