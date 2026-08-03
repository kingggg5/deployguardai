# DeployGuard AI quickstart

This guide has two paths:

- **Connected mode** is the real application path. It starts with an empty
  workspace and waits for a GitHub App, OIDC provider, or telemetry collector.
- **Demo mode** is an isolated, deterministic tour. Its records are synthetic,
  visibly labelled, and never represent a real repository or incident.

## Prerequisites

- Docker Engine and Compose v2 (recommended), or Docker Desktop
- Git
- For the source workflow: Python 3.12+, Node.js 24+, npm, and PowerShell 7

## Connected mode with Compose

```bash
git clone https://github.com/kingggg5/deployguardai.git
cd deployguardai
cp .env.example .env
docker compose up --build
```

On Windows PowerShell, use `Copy-Item .env.example .env` instead of `cp`.

Open:

- Web app: <http://127.0.0.1:4300>
- OpenAPI: <http://127.0.0.1:8100/docs>
- Readiness: <http://127.0.0.1:8100/api/v1/health/ready>

The default development identity is local-only and must not be used for a
shared environment. For real provider data, configure OIDC and a GitHub App in
`.env` or an external secret manager, then restart the API. The full provider
setup is documented in [OPERATIONS.md](OPERATIONS.md) and [SECURITY.md](SECURITY.md).

## Isolated demo mode

Use a separate Compose project name so the demo database cannot mix with a
connected-mode database:

```bash
docker compose -p deployguard-demo \
  -f docker-compose.yml -f docker-compose.demo.yml up --build
```

PowerShell:

```powershell
docker compose -p deployguard-demo `
  -f docker-compose.yml -f docker-compose.demo.yml up --build
```

The UI labels synthetic scenarios. Do not use demo output as operational
evidence, a benchmark claim, or a production migration rehearsal.

## Source development workflow

```powershell
git clone https://github.com/kingggg5/deployguardai.git
cd deployguardai
.\scripts\run-dev.ps1
```

Use `-SkipInstall` on later starts. Stop the local API and web processes with
`.\scripts\stop-dev.ps1`. Run the test suites independently when iterating:

```powershell
Push-Location backend
python -m pytest
Pop-Location

Push-Location frontend
npm ci
npm test -- --watch=false
npm run build
Pop-Location
```

## Cleanup

Stop a connected-mode stack:

```bash
docker compose down
```

Stop and remove only the isolated demo database:

```bash
docker compose -p deployguard-demo down --volumes
```

The `--volumes` flag is intentionally limited to the demo command. Removing a
connected database volume is destructive and should follow the backup and
restore procedure in [OPERATIONS.md](OPERATIONS.md).
