from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SRC = SERVICE_ROOT.parents[1] / "packages" / "leos-contracts" / "src"
CONTRACT_ROOT = SERVICE_ROOT.parents[1] / "contracts"


class ExecutionDispatcherDonorBaselineTests(unittest.TestCase):
    def run_service_code(
        self,
        source: str,
        *,
        configure_contract_root: bool = True,
    ) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            env = os.environ.copy()
            env["EXECUTION_DISPATCHER_DATA_DIR"] = data_dir
            if configure_contract_root:
                env["LEOS_CONTRACT_ROOT"] = str(CONTRACT_ROOT)
            else:
                env.pop("LEOS_CONTRACT_ROOT", None)
            env["PYTHONPATH"] = os.pathsep.join(
                [str(SERVICE_ROOT), str(PACKAGE_SRC)]
            )
            result = subprocess.run(
                [sys.executable, "-c", textwrap.dedent(source)],
                cwd=SERVICE_ROOT,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)

    def test_import_startup_does_not_load_contract_root(self):
        self.run_service_code(
            """
            from app import main
            assert main.app.title == "LEOS Execution Dispatcher"
            assert callable(main.validate_governed_contract)
            """,
            configure_contract_root=False,
        )

    def test_health_endpoint_reports_initialized_service(self):
        self.run_service_code(
            """
            from app import main
            result = main.health()
            assert result["ok"] is True
            assert result["service"] == "execution-dispatcher-service"
            assert result["execution_count"] == 0
            """
        )

    def test_contract_endpoint_freezes_donor_surface(self):
        self.run_service_code(
            """
            from app import main
            result = main.contract()
            assert result["contract_version"] == "leos.execution.v1"
            assert result["default_request_shape"] == "legacy_wrapped"
            assert "canonical_envelope" in result["request_shapes"]
            """
        )

    def test_donor_database_initializes_expected_tables(self):
        self.run_service_code(
            """
            from app import main
            with main.connect() as db:
                tables = {
                    row["name"] for row in db.execute(
                        "select name from sqlite_master where type='table'"
                    )
                }
                mode = db.execute("pragma journal_mode").fetchone()[0]
            assert {"provider_adapters", "executions"} <= tables
            assert mode == "wal"
            """
        )

    def test_donor_debt_capability_request_uses_provider_id(self):
        self.run_service_code(
            """
            import asyncio
            from app import main
            captured = {}
            class Response:
                status_code = 200
                text = ""
                def json(self):
                    return {"provider": {"provider_id": "chosen"}}
            class Client:
                def __init__(self, **kwargs): pass
                async def __aenter__(self): return self
                async def __aexit__(self, *args): pass
                async def post(self, url, json):
                    captured.update(json)
                    return Response()
            main.httpx.AsyncClient = Client
            env = main.envelope(main.ExecuteRequest(
                capability_id="baseline.run",
                provider_id="preferred",
            ))
            asyncio.run(main.resolve_provider(env, "preferred"))
            assert captured["provider_id"] == "preferred"
            assert "preferred_provider_id" not in captured
            """
        )

    def test_resolve_provider_accepts_donor_provider_response(self):
        self.run_service_code(
            """
            import asyncio
            from app import main
            class Response:
                status_code = 200
                text = ""
                def json(self):
                    return {"resolution": {
                        "provider": {"provider_id": "chosen"}
                    }}
            class Client:
                def __init__(self, **kwargs): pass
                async def __aenter__(self): return self
                async def __aexit__(self, *args): pass
                async def post(self, url, json): return Response()
            main.httpx.AsyncClient = Client
            env = main.envelope(main.ExecuteRequest(
                capability_id="baseline.run"
            ))
            body, provider = asyncio.run(main.resolve_provider(env, None))
            assert provider["provider_id"] == "chosen"
            assert "resolution" in body
            """
        )

    def test_adapter_selection_freezes_donor_precedence(self):
        self.run_service_code(
            """
            from app import main
            shape, source = main.request_shape(
                "content.write",
                {"provider_id": "provider-one", "metadata": {}},
            )
            assert shape == "flat_input"
            assert source["source"] == "adapter_registry"
            metadata_shape, metadata_source = main.request_shape(
                "other.run",
                {
                    "provider_id": "provider-one",
                    "metadata": {"request_shape": "canonical_envelope"},
                },
            )
            assert metadata_shape == "canonical_envelope"
            assert metadata_source["source"] == "provider_metadata"
            """
        )

    def test_provider_payload_shapes_freeze_legacy_behavior(self):
        self.run_service_code(
            """
            from app import main
            env = main.envelope(main.ExecuteRequest(
                capability_id="baseline.run",
                input={"prompt": "hello"},
            ))
            assert main.shape_payload("flat_input", env) == {"prompt": "hello"}
            assert main.shape_payload("canonical_envelope", env) == env
            assert main.shape_payload("legacy_wrapped", env) == {
                "capability": "baseline.run",
                "input": {"prompt": "hello"},
                "requester": {"type": "system", "id": "leos"},
            }
            """
        )

    def test_provider_target_url_is_normalized(self):
        self.run_service_code(
            """
            from app import main
            assert main.target_url({
                "base_url": "http://provider:8000/",
                "execute_path": "/invoke",
            }) == "http://provider:8000/invoke"
            """
        )

    def test_execution_persistence_retrieval_and_listing(self):
        self.run_service_code(
            """
            from app import main
            request = main.ExecuteRequest(
                capability_id="baseline.run",
                execution_id="execution-baseline",
                input={"prompt": "hello"},
            )
            env = main.envelope(request)
            main.insert_execution(env, request)
            item = main.execution("execution-baseline")["execution"]
            assert item["state"] == "resolving"
            assert item["envelope"]["capability_id"] == "baseline.run"
            listing = main.executions(limit=200)
            assert listing["execution_count"] == 1
            assert listing["executions"][0]["execution_id"] == (
                "execution-baseline"
            )
            with main.connect() as reopened:
                assert reopened.execute(
                    "select count(*) from executions"
                ).fetchone()[0] == 1
            """
        )

    def test_donor_debt_retry_repeats_on_5xx_then_succeeds(self):
        self.run_service_code(
            """
            import asyncio
            from app import main
            responses = [500, 200]
            class Response:
                text = ""
                def __init__(self, status_code): self.status_code = status_code
                def json(self): return {"status": self.status_code}
            class Client:
                def __init__(self, **kwargs): pass
                async def __aenter__(self): return self
                async def __aexit__(self, *args): pass
                async def post(self, url, json):
                    return Response(responses.pop(0))
            main.httpx.AsyncClient = Client
            main.MAX_RETRIES = 1
            status, body, attempts = asyncio.run(
                main.invoke("http://provider/invoke", {"value": 1})
            )
            assert (status, attempts) == (200, 2)
            assert body == {"status": 200}
            """
        )

    def test_donor_debt_non_json_response_becomes_raw_result(self):
        self.run_service_code(
            """
            import asyncio
            from app import main
            class Response:
                status_code = 200
                text = "legacy raw response"
                def json(self): raise ValueError("not json")
            class Client:
                def __init__(self, **kwargs): pass
                async def __aenter__(self): return self
                async def __aexit__(self, *args): pass
                async def post(self, url, json): return Response()
            main.httpx.AsyncClient = Client
            main.MAX_RETRIES = 0
            status, body, attempts = asyncio.run(
                main.invoke("http://provider/invoke", {})
            )
            assert status == 200
            assert attempts == 1
            assert body == {"raw": "legacy raw response"}
            """
        )


if __name__ == "__main__":
    unittest.main()
