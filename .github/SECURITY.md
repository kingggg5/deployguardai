# Security policy

DeployGuard AI handles repository metadata, telemetry, evidence, and operational decisions. Please help us keep reports private until a fix is available.

## Reporting a vulnerability

Do **not** open a public issue or pull request for a suspected vulnerability. Use one of these private channels:

1. Open a [GitHub Security Advisory](https://github.com/kingggg5/deployguardai/security/advisories/new) for this repository.
2. If private advisories are unavailable, send a private GitHub message to [@kingggg5](https://github.com/kingggg5) with the subject "DeployGuard security report".

Include only the information needed to reproduce the issue safely:

- affected version, commit, or deployment mode;
- impact and affected component;
- minimal reproduction steps or a proof of concept that does not access real customer data;
- any suggested mitigation.

Never include credentials, access tokens, private keys, session cookies, customer data, production hostnames, or unredacted telemetry. If secrets were exposed, revoke or rotate them immediately and mention only the type of secret in the report.

The public [security intake form](https://github.com/kingggg5/deployguardai/issues/new?template=security.yml) is only for confirming that a private report was sent. It must not contain vulnerability details.

## Response targets

Maintainers aim to acknowledge a private report within 5 business days, provide an initial severity assessment within 10 business days, and coordinate a fix and disclosure timeline with the reporter. Timelines may vary when the issue involves an upstream dependency or an unavailable reproduction.

## Supported versions

Security fixes target the latest release and the main branch. The project may backport a fix when the affected branch is still in active use and the change can be made safely.

## Disclosure

Please allow maintainers reasonable time to investigate and release a fix before public disclosure. We will credit reporters who want attribution and will not publish private details without consent.

## Scope and boundaries

This policy covers the DeployGuard AI source code, official container images, and documented deployment configuration. Third-party providers, user-managed infrastructure, and vulnerabilities caused solely by local configuration should be reported to the relevant vendor as well.

For the project security model and operational controls, see [docs/SECURITY.md](../docs/SECURITY.md).
