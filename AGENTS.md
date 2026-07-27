# DeployGuard AI Agent Guide

## Architecture

- Backend: FastAPI, Pydantic, SQLAlchemy 2.x, SQLite locally, PostgreSQL by configuration.
- Frontend: Angular standalone components and typed `HttpClient` services.
- Deterministic engines own risk scoring, graph traversal, hypothesis ranking, and explanations.
- Synthetic scenarios must be visibly labeled in the API and UI.

## Boundaries

- Do not add autonomous remediation, shell execution, deployment, rollback, or cluster credentials.
- Do not add an LLM call until an evidence-only contract and evaluation tests exist.
- Keep API models typed and backward-compatible.
- Keep scoring weights explicit and covered by tests.
- Treat evidence, counter-evidence, uncertainty, and human feedback as first-class data.

## Verification

- Backend: `pytest`
- Frontend: `npm test -- --watch=false` and `npm run build`
- Compose: `docker compose config`
- Inspect desktop and mobile layouts in a browser.
