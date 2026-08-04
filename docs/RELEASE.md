# Release guide

DeployGuard AI publishes versioned container images only from signed-off
version tags. A release is a distribution artifact, not a claim that every
deployment is production-ready: provider credentials, TLS, secrets, alerting,
backup storage, and on-call ownership remain environment responsibilities.

## Before tagging

1. Update `CHANGELOG.md` with user-visible changes and known limitations.
2. Confirm the version in `frontend/package.json`, `backend/pyproject.toml`,
   and the release notes agree. Start from the
   [`v0.1.0` public-preview draft](release-notes/v0.1.0.md) for the first
   release and replace all placeholders with verified CI evidence.
3. Run the fail-closed readiness check for the target environment:

   ```powershell
   python scripts/production_readiness.py
   ```

4. Confirm the main branch is green for backend, frontend, PostgreSQL
   migrations, Compose smoke, evaluation, CodeQL, dependency review, and
   Scorecard.
5. Rehearse backup and restore using the migration head documented in
   `docs/OPERATIONS.md`.
6. Review the generated evaluation artifact and record its commit, manifest
   checksum, environment, and known limitations.

## Publish

Create an annotated semantic-version tag and push it:

```powershell
git tag -a v0.1.0 -m "DeployGuard AI v0.1.0"
git push deployguardai v0.1.0
```

The `Release` workflow then:

- reuses the complete CI workflow;
- builds `ghcr.io/kingggg5/deployguardai-api` and
  `ghcr.io/kingggg5/deployguardai-web` for `linux/amd64` and `linux/arm64`;
- publishes immutable version tags, a major/minor convenience tag, and
  `latest`;
- attaches BuildKit provenance and SBOM attestations to each image; and
- creates GitHub release notes from merged pull requests.

Deployments should pin an image digest, not `latest`:

```text
ghcr.io/kingggg5/deployguardai-api@sha256:<digest>
ghcr.io/kingggg5/deployguardai-web@sha256:<digest>
```

## Rollback

Roll back by redeploying the previous known-good image digest and following
the database rollback policy in `docs/OPERATIONS.md`. Never repair a failed
migration with ad-hoc production SQL. If the release crossed a schema
compatibility boundary, pause writes and use the documented expand/migrate/
contract procedure.

## Release evidence

Attach or link the following to the release:

```text
Commit/tag:
Image digests:
Schema and migration head:
Engine/scoring/graph versions:
Evaluation manifest and checksum:
CI/security results:
Restore rehearsal:
Known limitations:
Rollback digest and procedure:
```
