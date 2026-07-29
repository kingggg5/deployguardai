# Telemetry normalization gateway

DeployGuard does not expose an OTLP receiver. Do not point an `otlphttp` exporter
at `/api/v1/telemetry/events`: OTLP wire payloads do not match the normalized
evidence contract.

A production telemetry path needs a small trusted gateway between the
OpenTelemetry Collector and DeployGuard:

```text
application -> OTLP Collector -> normalization/redaction gateway
            -> DeployGuard normalized event API
```

The gateway must:

1. Authenticate its upstream Collector.
2. Allowlist and redact resource attributes.
3. Map one signal into the bounded JSON contract below.
4. Use a workspace-derived `dgct_...` credential, never the credential root.
5. Send stable event IDs so retries are idempotent.
6. Apply request-body, cardinality, and rate limits.

## HTTP contract

```http
POST /api/v1/telemetry/events
Authorization: Bearer dgct_<workspace-hmac>
Content-Type: application/json
X-DeployGuard-Workspace: <workspace-id>
X-DeployGuard-Repository: <optional-repository-id>
X-DeployGuard-Event-ID: <stable-source-event-id>
```

```json
{
  "source": "otel-gateway",
  "type": "metric",
  "service_id": "checkout-api",
  "summary": "Checkout p95 latency exceeded the review threshold",
  "value": 2.7,
  "supports_hypothesis_ids": [],
  "contradicts_hypothesis_ids": []
}
```

The API stores the first-class source as server-owned `telemetry`; the submitted
source remains provider metadata. `service_id` may be the service UUID or its
workspace-unique slug. Connected workspaces require a registered service.

## Credential derivation

Run this only in a trusted server environment:

```powershell
Set-Location backend
$env:DEPLOYGUARD_WORKSPACE_ID = "<workspace-id>"
python -c "import os; from app.services import derive_telemetry_collector_token as d; print(d(os.environ['TELEMETRY_INGEST_TOKEN'], os.environ['DEPLOYGUARD_WORKSPACE_ID']))"
```

Rotate the credential root through the deployment secret manager and redistribute
derived credentials to the corresponding gateways. Production rejects the raw
root secret.
