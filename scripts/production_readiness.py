"""Fail-closed production readiness report without printing credentials."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

from pydantic import ValidationError


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings  # noqa: E402


OPERATOR_ATTESTATIONS = {
    "DEPLOYGUARD_TLS_TERMINATED": "TLS/WAF ingress is configured",
    "DEPLOYGUARD_MANAGED_SECRETS": "secrets come from a managed provider",
    "DEPLOYGUARD_DISTRIBUTED_RATE_LIMIT": (
        "one shared ingress or distributed limiter protects all replicas"
    ),
    "DEPLOYGUARD_BACKUP_CONFIGURED": (
        "encrypted off-host backups and expiry policy are configured"
    ),
    "DEPLOYGUARD_RESTORE_REHEARSED": (
        "an isolated restore rehearsal completed within the recovery objective"
    ),
    "DEPLOYGUARD_RETENTION_SCHEDULED": (
        "the dry-run/apply retention workflow is scheduled with legal-hold input"
    ),
    "DEPLOYGUARD_IMMUTABLE_AUDIT_CONFIGURED": (
        "application and deletion audit evidence is exported to immutable storage"
    ),
    "DEPLOYGUARD_WORKER_SUPERVISED": (
        "the background worker is supervised and alerts on dead-letter growth"
    ),
    "DEPLOYGUARD_TELEMETRY_BACKEND_CONFIGURED": (
        "the Collector exports to an authenticated durable telemetry backend"
    ),
    "DEPLOYGUARD_ALERTING_CONFIGURED": "SLO dashboards and alerts are routed",
    "DEPLOYGUARD_ON_CALL_CONFIGURED": "an owned on-call escalation is documented",
}


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "detail": detail}


def assess_production_readiness(
    settings: Settings,
    environment: Mapping[str, str],
) -> dict[str, Any]:
    checks = [
        _check(
            "runtime.production",
            settings.environment.strip().lower() == "production",
            "ENVIRONMENT must be production",
        ),
        _check(
            "database.postgresql",
            settings.database_url.startswith("postgresql+psycopg://"),
            "PostgreSQL through psycopg is required",
        ),
        _check(
            "database.release_migrations",
            settings.run_migrations_on_startup is False,
            "API startup migrations must be disabled in production",
        ),
        _check(
            "identity.oidc",
            settings.auth_provider == "oidc"
            and bool(settings.oidc_issuer)
            and bool(settings.oidc_audience)
            and bool(settings.oidc_jwks_url),
            "OIDC issuer, audience, and JWKS must be configured",
        ),
        _check(
            "github.app",
            settings.github_app_available()
            and settings.github_checks_enabled
            and len(settings.github_webhook_secret) >= 32,
            "GitHub App, Checks worker, and a 32+ character webhook secret are required",
        ),
        _check(
            "email.smtp",
            settings.email_delivery_mode() == "smtp"
            and len(settings.invitation_token_secret) >= 32,
            "SMTP host/from address and a 32+ character invitation token secret are required",
        ),
        _check(
            "telemetry.collector_credential",
            len(settings.telemetry_ingest_token) >= 32,
            "A 32+ character telemetry credential root is required",
        ),
        _check(
            "observability.otlp",
            bool(settings.otel_traces_endpoint.strip()),
            "OTEL_TRACES_ENDPOINT must target the trusted Collector",
        ),
    ]
    attestations = [
        _check(name, _enabled(environment.get(name)), detail)
        for name, detail in OPERATOR_ATTESTATIONS.items()
    ]
    all_checks = checks + attestations
    return {
        "ready": all(item["passed"] for item in all_checks),
        "checks": checks,
        "operator_attestations": attestations,
        "notes": [
            "This report validates configuration shape and explicit operator attestations.",
            "It does not fabricate credentials or prove an external provider SLA.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit compact JSON instead of a readable checklist",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        settings = Settings()
    except ValidationError as error:
        payload = {
            "ready": False,
            "configuration_error": [
                {
                    "location": ".".join(str(item) for item in issue["loc"]),
                    "message": issue["msg"],
                }
                for issue in error.errors()
            ],
        }
        print(json.dumps(payload, separators=(",", ":")))
        return 2
    payload = assess_production_readiness(settings, os.environ)
    if args.json:
        print(json.dumps(payload, separators=(",", ":")))
    else:
        for section in ("checks", "operator_attestations"):
            print(section.replace("_", " ").title())
            for item in payload[section]:
                marker = "PASS" if item["passed"] else "BLOCKED"
                print(f"  [{marker}] {item['name']}: {item['detail']}")
        print(f"Ready: {str(payload['ready']).lower()}")
    return 0 if payload["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
