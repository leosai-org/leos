from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


CALLS: list[dict[str, Any]] = []
CALLS_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "LEOSSyntheticProvider/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(
            body, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path == "/health":
            with CALLS_LOCK:
                count = len(CALLS)
            self.send_json(
                200,
                {
                    "ok": True,
                    "service": "epic-1.2e-synthetic-provider",
                    "invocation_count": count,
                },
            )
            return
        if self.path == "/evidence":
            with CALLS_LOCK:
                calls = list(CALLS)
            self.send_json(
                200,
                {
                    "ok": True,
                    "invocation_count": len(calls),
                    "calls": calls,
                },
            )
            return
        self.send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/invoke":
            self.send_json(404, {"ok": False, "error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length))
            execution_id = request["execution_id"]
            correlation = request["trace"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.send_json(
                422,
                {"ok": False, "error": "canonical_envelope_required"},
            )
            return

        response = {
            "ok": True,
            "synthetic": True,
            "message": "epic-1.2e-success",
            "provider_operation_id": f"synthetic-operation-{execution_id}",
        }
        evidence = {
            "execution_id": execution_id,
            "correlation": correlation,
            "payload": request,
            "response": response,
        }
        with CALLS_LOCK:
            CALLS.append(evidence)
        self.send_json(200, response)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()

