# Changelog

All notable changes to DeployGuard AI are documented here. The project follows
release notes from `main` and will use semantic versioning for tagged releases.

## [Unreleased]

### Added

- Apache-2.0 open-source foundation with contribution, governance, support, and security policies.
- GitHub issue forms, pull request checklist, CODEOWNERS, Dependabot, CI, CodeQL, dependency review, and OpenSSF Scorecard workflows.
- Request IDs, structured access logs, request body limits, bounded ingress rate limits, and separate liveness/readiness probes.
- Versioned SHA-256-pinned synthetic evaluation manifests with CI-uploaded result artifacts.

### Changed

- README and operations documentation now distinguish implemented hardening from provider- and infrastructure-dependent production work.
- Backend test dependency updated to a secure pytest 9.x range.

### Still required for production

- Configure real OIDC, GitHub App, SMTP, telemetry, HTTPS ingress, managed secrets, backups, distributed rate limits, and monitoring.
- Add a durable queue/outbox and production restore rehearsal before processing critical external events.
