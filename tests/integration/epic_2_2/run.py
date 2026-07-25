from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


RANKING = "http://ranking-policy:8000"
CAPABILITY = "http://capability-manager:8000"
MODELS = "http://model-registry:8000"


def request(method, url, body=None):
    data = None if body is None else json.dumps(body).encode()
    headers = {} if body is None else {"Content-Type": "application/json"}
    operation = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(operation, timeout=10) as response:
        return json.loads(response.read())


def ready(url):
    for _ in range(90):
        try:
            request("GET", f"{url}/health")
            return
        except (OSError, urllib.error.HTTPError):
            time.sleep(0.2)
    raise AssertionError(f"service did not become ready: {url}")


for service in (RANKING, CAPABILITY, MODELS):
    ready(service)

request("POST", f"{CAPABILITY}/capabilities", {
    "capability_id": "text.reason", "name": "Reason"
})
provider_revisions = {}
for provider_id in ("p1", "p2"):
    request("POST", f"{CAPABILITY}/providers", {
        "provider_id": provider_id,
        "name": provider_id,
        "provider_type": "service",
        "base_url": f"http://{provider_id}:8000"
    })
    request("POST", f"{CAPABILITY}/bindings", {
        "provider_id": provider_id,
        "capability_id": "text.reason",
        "enabled": True,
        "approval_policy": "allowed"
    })
for item in request("GET", f"{CAPABILITY}/providers?limit=2000")["providers"]:
    provider_revisions[item["provider_id"]] = item["updated_at"]

for model_id in ("m1", "m2"):
    request("POST", f"{MODELS}/models", {
        "model_id": model_id,
        "display_name": model_id,
        "capabilities": ["text.reason"],
        "enabled": True
    })

def bind(provider_id, model_id):
    request("POST", f"{MODELS}/bindings", {
        "binding_id": f"b-{provider_id}-{model_id}",
        "model_id": model_id,
        "provider_id": provider_id,
        "provider_ref": {
            "authority": "capability-manager",
            "reference_id": provider_id,
            "revision": provider_revisions[provider_id]
        },
        "runtime_model_ref": f"native-{model_id}",
        "runtime_type": "synthetic",
        "enabled": True,
        "availability": {"state": "available"}
    })

bind("p1", "m2")
bind("p2", "m1")

for dimension, values in (("provider", ["p1", "p2"]), ("model", ["m1", "m2"])):
    request("POST", f"{RANKING}/rankings", {
        "dimension": dimension,
        "scope_type": "global",
        "ordered_ids": values
    })

resolution_request = {
    "contract_version": "leos.capability-resolution-request.v1",
    "capability_id": "text.reason",
    "requester": {"type": "employee", "id": "emp-1"},
    "constraints": {},
    "policy": {},
    "correlation": {
        "contract_version": "leos.execution-correlation.v1",
        "job_id": "job-1",
        "execution_id": "exec-1"
    },
    "ranking_context": {"employee_id": "emp-1", "job_id": "job-1"},
    "target_requirements": {"model_required": True},
    "requested_at": "2026-07-25T12:00:00Z"
}
crossed = request("POST", f"{CAPABILITY}/resolve", resolution_request)
assert crossed["status"] == "GOVERNED_ORDER_REQUIRED", crossed
assert "selected_target" not in crossed

# Disable crossed bindings, then register the uniquely dominant diagonal.
for binding in request("GET", f"{MODELS}/bindings")["bindings"]:
    request("PATCH", f"{MODELS}/bindings/{binding['binding_id']}", {
        "expected_revision": binding["revision"], "enabled": False
    })
bind("p1", "m1")
bind("p2", "m2")
resolution_request["correlation"]["execution_id"] = "exec-2"
resolved = request("POST", f"{CAPABILITY}/resolve", resolution_request)
assert resolved["status"] == "RESOLVED", resolved
assert resolved["selected_target"]["provider_id"] == "p1", resolved
assert resolved["selected_target"]["model_id"] == "m1", resolved
assert resolved["selected_target"]["runtime_binding_id"] == "b-p1-m1", resolved
assert resolved["rationale"]["provider_effective_ranking"]["ordered_ids"] == [
    "p1", "p2"
]
assert resolved["rationale"]["model_effective_ranking"]["ordered_ids"] == [
    "m1", "m2"
]

# Case C: otherwise-valid unlisted inventory is excluded exactly.
request("POST", f"{CAPABILITY}/providers", {
    "provider_id": "p3",
    "name": "p3",
    "provider_type": "service",
    "base_url": "http://p3:8000"
})
request("POST", f"{CAPABILITY}/bindings", {
    "provider_id": "p3",
    "capability_id": "text.reason",
    "enabled": True,
    "approval_policy": "allowed"
})
provider_revisions["p3"] = next(
    item["updated_at"]
    for item in request("GET", f"{CAPABILITY}/providers?limit=2000")["providers"]
    if item["provider_id"] == "p3"
)
request("POST", f"{MODELS}/models", {
    "model_id": "m3",
    "display_name": "m3",
    "capabilities": ["text.reason"],
    "enabled": True
})
bind("p3", "m3")
resolution_request["correlation"]["execution_id"] = "exec-3"
excluded = request("POST", f"{CAPABILITY}/resolve", resolution_request)
assert excluded["status"] == "RESOLVED", excluded
assert excluded["selected_target"]["provider_id"] == "p1", excluded
assert all(
    item["provider_id"] != "p3"
    for item in excluded["candidate_evaluations"]
), excluded

# Case D: inactive rankings mean inheritance; with no defined order and
# multiple candidates, no list or database order may select.
for ranking in request("GET", f"{RANKING}/rankings")["rankings"]:
    request("PATCH", f"{RANKING}/rankings/{ranking['ranking_id']}", {
        "expected_revision": ranking["revision"],
        "active": False
    })
resolution_request["correlation"]["execution_id"] = "exec-4"
unordered = request("POST", f"{CAPABILITY}/resolve", resolution_request)
assert unordered["status"] == "GOVERNED_ORDER_REQUIRED", unordered
assert "selected_target" not in unordered

# Case E: without rankings, exactly one remaining eligible candidate resolves.
for binding in request("GET", f"{MODELS}/bindings")["bindings"]:
    if binding["binding_id"] in {"b-p2-m2", "b-p3-m3"}:
        request("PATCH", f"{MODELS}/bindings/{binding['binding_id']}", {
            "expected_revision": binding["revision"], "enabled": False
        })
resolution_request["correlation"]["execution_id"] = "exec-5"
single = request("POST", f"{CAPABILITY}/resolve", resolution_request)
assert single["status"] == "RESOLVED", single
assert single["selected_target"]["provider_id"] == "p1", single
assert single["selected_target"]["model_id"] == "m1", single

print("Epic 2.2 real HTTP integration: PASS (5 governed cases)")
