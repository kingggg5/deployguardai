# DeployGuard Workspace and Collaboration Research

## Implemented local vertical slice

The product now includes development identity, workspace creation, server-side
Owner/Admin/Responder/Viewer policy, development-fixture repositories, hashed
one-time invitations with accept/revoke flows, audit events, and Alembic
migrations. Production OIDC, GitHub App installation, email delivery, complete
legacy investigation tenant scoping, and connected OpenTelemetry remain external
integration gates.

Date: 2026-07-28

## Decision

DeployGuard should evolve around a persistent scope hierarchy:

```text
Workspace
├─ Team / service ownership
├─ Repository connections
├─ Changes and deployments
└─ Incidents
   ├─ Evidence
   ├─ Decisions
   └─ Post-mortems
```

The current local MVP has no authentication or tenant isolation. Therefore repository selection may expose only API-backed synthetic scenarios, and “share” means copying a deep link for someone who already has access. Workspace invitations, GitHub connection, and public links must not be represented as available until their security contracts exist.

## Product patterns reviewed

| Product/source | Useful pattern | DeployGuard application |
|---|---|---|
| [React Bits](https://reactbits.dev/) | Copy-owned visual primitives rather than a full product architecture | Translate [Stepper](https://reactbits.dev/components/stepper), Animated List, and Spotlight selection behavior into Angular/CSS. Do not add React as a second runtime. |
| [Linear workspaces](https://linear.app/docs/workspaces) | Persistent workspace scope and permission-gated integrations | Workspace switcher, workspace-specific repositories, settings, and members. |
| [Linear invitations](https://linear.app/docs/invite-members) | Role-aware invitations, approved domains, pending members | Owner/admin invitation flow with viewer, investigator, admin, and owner roles. |
| [Linear custom views](https://linear.app/docs/custom-views) | Searchable saved views, favorites, and shareable URLs | Saved “High-risk changes”, “Unconfirmed causes”, and “My team” ledgers. |
| [Sentry issue details](https://docs.sentry.io/product/issues/issue-details/) | Dense detail surface with global state header and collaboration rail | Preserve DeployGuard’s incident header, evidence body, and human-decision rail. |
| [incident.io teams](https://docs.incident.io/catalog/teams) | Team-aware default filtering and service ownership | Resolve the affected service to the responsible team and responders. |
| [Rootly teams](https://docs.rootly.com/managing-teams/configuring-teams) | Teams own services, channels, schedules, and escalation resources | Keep ownership metadata next to affected services; do not bury it in settings. |

## Implemented in the local MVP

- Typed `repository` field on every scenario summary.
- Searchable repository/scope switcher backed by `/api/v1/scenarios`.
- `Ctrl/Cmd + K` command center for current working actions.
- URL state for `view` and `scenario`.
- Copy-view-link action that explicitly does not grant access.
- Standalone Angular components with colocated, flat state styling.

## Production foundation

Implement in this order:

1. Authentication and an explicit `Principal`.
2. Alembic migrations and a `Workspace` tenant boundary.
3. `WorkspaceMembership` with `viewer`, `investigator`, `admin`, and `owner` policy checks.
4. Workspace-scoped repositories and user context.
5. One-time invitation tokens stored only as hashes, with expiry and revocation.
6. GitHub App installation references; never persist PATs or installation tokens.
7. Audit events and cross-workspace negative tests.
8. Only then enable create-workspace, connect-repository, and invite-member UI.

Recommended scoped routes:

```text
GET/POST  /api/v1/workspaces
GET/PUT   /api/v1/me/context
GET       /api/v1/workspaces/{workspace_id}/repositories
GET       /api/v1/workspaces/{workspace_id}/members
POST      /api/v1/workspaces/{workspace_id}/invites
DELETE    /api/v1/workspaces/{workspace_id}/invites/{invite_id}
GET       /api/v1/workspaces/{workspace_id}/repositories/{repository_id}/overview
```

Canonical frontend URLs should become:

```text
/w/:workspaceId/r/:repositoryId/investigation
/w/:workspaceId/r/:repositoryId/changes/:changeId/risk
/w/:workspaceId/r/:repositoryId/metrics
/w/:workspaceId/settings/repositories
/w/:workspaceId/settings/members
```

## Clean-code contract

- Root component becomes composition only; feature state moves into focused stores.
- Route-level standalone components are lazy loaded.
- Typed reactive forms replace `$any($event.target)` mapping.
- Global styles contain tokens/base/primitives; feature styles stay colocated.
- Use one semantic class per element and `data-state`/ARIA for state.
- Do not add a clickable control without a real endpoint, permission, error state, and test.
