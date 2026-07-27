"""
DeployGuard AI - Automated Fault Injection & Incident Simulator
Injects synthetic faults into running DeployGuard API to demonstrate real-time RCA analysis.
"""
import json
import urllib.request
import urllib.parse
from typing import Any

API_BASE = "http://127.0.0.1:8100/api/v1"


def inject_fault(service_id: str = "checkout-api", fault_type: str = "latency_spike") -> dict[str, Any]:
    print(f"[Fault Injection] Injecting Fault [{fault_type}] into Service [{service_id}]...")

    payload = {
        "source": "toxiproxy-simulator",
        "type": "alert",
        "service_id": service_id,
        "summary": f"Fault Injection Simulation: {fault_type} triggered on {service_id}",
        "value": 2500 if fault_type == "latency_spike" else "connection_reset",
        "supports_hypothesis_ids": ["hyp-payment-timeout"],
        "contradicts_hypothesis_ids": [],
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/telemetry/events",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            res_body = json.loads(resp.read().decode("utf-8"))
            print("[OK] Telemetry Event Injected Successfully:")
            print(json.dumps(res_body, indent=2))
            return res_body
    except Exception as err:
        print(f"[ERROR] Failed to inject fault: {err}")
        return {"error": str(err)}


if __name__ == "__main__":
    inject_fault()
