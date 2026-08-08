# DeployGuard AI quickstart

This guide has three paths:

- **Verify-only mode** creates a deterministic evidence receipt in an existing
  repository. It needs Python and Git, but no LLM key, database, or DeployGuard
  server.

- **Connected mode** is the real application path. It starts with an empty
  workspace and waits for a GitHub App, OIDC provider, or telemetry collector.
- **Demo mode** is an isolated, deterministic tour. Its records are synthetic,
  visibly labelled, and never represent a real repository or incident.

## Prerequisites

- Docker Engine and Compose v2 (recommended), or Docker Desktop
- Git
- For the source workflow: .NET SDK 10, Python 3.12+, Node.js 24+, and npm
- PowerShell 7 on Windows, or Bash on macOS/Linux. GNU Make is optional on
  macOS/Linux for the short commands below.

## Verify-only mode

```bash
python -m pip install ./verify
deployguard verify --base origin/main --head HEAD \
  --evidence-sha "$(git rev-parse HEAD)" \
  --junit artifacts/junit.xml
```

Add `--coverage` for Cobertura XML or LCOV and `--sarif` for SARIF 2.1.0. Every
input supports repeatable glob arguments. DeployGuard records normalized counts
and hashes, not test logs, source snippets, SARIF messages, credentials, or
prompts.

By default `.deployguard/policy.yml` is read from the protected base commit.
This prevents a pull request from weakening its own gate. The built-in policy
is used during first installation when the base does not contain a policy.

```bash
deployguard init --github --agent codex
```

The initializer never overwrites an existing policy unless `--force` is
explicitly supplied. Its GitHub workflow deliberately returns REVIEW until the
repository's real JUnit path is configured. For production use, pin the root
composite Action to a released full commit SHA.

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
The public control-plane port is loopback-bound by default; the Python engine
and Prometheus endpoint remain reachable only on the private Compose network.

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

On macOS/Linux with GNU Make installed, the same isolated demo is available as:

```bash
make demo
```

## Source development workflow

### Windows PowerShell

```powershell
git clone https://github.com/kingggg5/deployguardai.git
cd deployguardai
.\scripts\run-dev.ps1
```

Use `-SkipInstall` on later starts. Stop the local API and web processes with
`.\scripts\stop-dev.ps1`.

### macOS and Linux

```bash
git clone https://github.com/kingggg5/deployguardai.git
cd deployguardai
chmod +x scripts/run-dev.sh scripts/stop-dev.sh
./scripts/run-dev.sh
```

Use `./scripts/run-dev.sh --skip-install` on later starts. Stop only the
processes started by that helper with `./scripts/stop-dev.sh`. Set
`PYTHON_BIN=python` before the command if your Python 3.12 executable is named
`python` instead of `python3`.

Both source helpers explicitly disable synthetic seeding. Unless you provide a
`DATABASE_URL`, they use `.runtime/connected-local.db` so an older
`backend/deployguard.db` fixture cannot appear in a connected workspace.

### Make shortcuts (macOS/Linux)

```bash
make install
make dev
make test
make coverage
make stop
```

`make demo` starts the same isolated synthetic Compose project; `make demo-down`
stops it without removing its database volume.

Run the test suites independently when iterating:

```powershell
dotnet test control-plane/DeployGuard.ControlPlane.slnx

Push-Location backend
python -m pytest
Pop-Location

Push-Location frontend
npm ci
npm test -- --watch=false
npm run test:coverage
npm run build
Pop-Location
```

The .NET process is the public API on port `8100`; the source helper keeps the
internal Python service on loopback port `8101`. The backend coverage command is
`python -m pytest -p pytest_cov --cov=app
--cov-report=term-missing --cov-fail-under=80`. Angular coverage is reported
under `frontend/coverage/`. The CI workflow keeps those reports as artifacts
and fails only when the documented baseline thresholds regress.

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
