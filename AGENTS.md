# DeployGuard AI Agent Guide

## Architecture

- Public control plane: ASP.NET Core 10, YARP, and Npgsql.
- Internal application and engines: FastAPI, Pydantic, SQLAlchemy 2.x,
  SQLite locally, PostgreSQL by configuration.
- Frontend: Angular standalone components and typed `HttpClient` services.
- Keyless change gate: the standalone `verify` package and root composite
  Action own Evidence Receipt decisions. Skills only orchestrate the CLI.
- Deterministic engines own risk scoring, graph traversal, hypothesis ranking, and explanations.
- Synthetic scenarios must be visibly labeled in the API and UI.

## Boundaries

- Do not add autonomous remediation, shell execution, deployment, rollback, or cluster credentials.
- Do not treat Skill or `AGENTS.md` output as verification evidence or allow a
  pull-request-head policy to weaken the protected-base gate.
- Do not add an LLM call until an evidence-only contract and evaluation tests exist.
- Keep API models typed and backward-compatible.
- Keep scoring weights explicit and covered by tests.
- Treat evidence, counter-evidence, uncertainty, and human feedback as first-class data.

## Verification

- Verify package: `cd verify && python -m pytest`
- Backend: `pytest`
- Control plane: `dotnet test control-plane/DeployGuard.ControlPlane.slnx`
- Frontend: `npm test -- --watch=false` and `npm run build`
- Compose: `docker compose config`
- Inspect desktop and mobile layouts in a browser.
