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


class CapabilityManagerDonorBaselineTests(unittest.TestCase):
    def run_service_code(
        self,
        source: str,
        *,
        configure_contract_root: bool = True,
    ) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            env = os.environ.copy()
            env["CAPABILITY_MANAGER_DATA_DIR"] = data_dir
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
            assert main.app.title == "LEOS Capability Manager"
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
            assert result["service"] == "capability-manager-service"
            assert result["provider_count"] == 0
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
            assert {
                "providers", "capabilities", "provider_capabilities",
                "resolutions", "executions", "events",
                "provider_payload_adapters",
            } <= tables
            assert mode == "wal"
            """
        )

    def test_registration_and_persistence_survive_reopen(self):
        self.run_service_code(
            """
            from app import main
            main.register_provider(main.Provider(
                provider_id="provider-one", name="One",
                provider_type="service", base_url="http://one:8000",
            ))
            main.register_capability(main.Capability(
                capability_id="baseline.run", name="Baseline Run",
            ))
            main.register_binding(main.Binding(
                provider_id="provider-one", capability_id="baseline.run",
            ))
            with main.connect() as first:
                assert first.execute(
                    "select count(*) from provider_capabilities"
                ).fetchone()[0] == 1
            with main.connect() as reopened:
                provider = reopened.execute(
                    "select name from providers where provider_id=?",
                    ("provider-one",),
                ).fetchone()
                capability = reopened.execute(
                    "select name from capabilities where capability_id=?",
                    ("baseline.run",),
                ).fetchone()
            assert provider["name"] == "One"
            assert capability["name"] == "Baseline Run"
            """
        )

    def test_successful_resolution_is_persisted(self):
        self.run_service_code(
            """
            from app import main
            main.register_provider(main.Provider(
                provider_id="provider-one", name="One",
                provider_type="service", base_url="http://one:8000",
            ))
            main.register_capability(main.Capability(
                capability_id="baseline.run", name="Baseline Run",
            ))
            main.register_binding(main.Binding(
                provider_id="provider-one", capability_id="baseline.run",
            ))
            result = main.resolve(main.ResolveRequest(
                capability_id="baseline.run"
            ))
            assert result["provider"]["provider_id"] == "provider-one"
            with main.connect() as reopened:
                stored = reopened.execute(
                    "select selected_provider_id from resolutions "
                    "where resolution_id=?",
                    (result["resolution_id"],),
                ).fetchone()
            assert stored["selected_provider_id"] == "provider-one"
            """
        )

    def test_no_provider_resolution_raises_donor_404(self):
        self.run_service_code(
            """
            from fastapi import HTTPException
            from app import main
            main.register_capability(main.Capability(
                capability_id="baseline.run", name="Baseline Run",
            ))
            try:
                main.resolve(main.ResolveRequest(capability_id="baseline.run"))
            except HTTPException as error:
                assert error.status_code == 404
                assert error.detail == "No eligible provider."
            else:
                raise AssertionError("donor resolution unexpectedly succeeded")
            """
        )

    def test_donor_debt_preference_overrides_weighted_score(self):
        self.run_service_code(
            """
            from app import main
            main.register_capability(main.Capability(
                capability_id="baseline.run", name="Baseline Run",
            ))
            for provider_id, priority in (("ranked-first", 1), ("preferred", 999)):
                main.register_provider(main.Provider(
                    provider_id=provider_id, name=provider_id,
                    provider_type="service",
                    base_url=f"http://{provider_id}:8000",
                    priority=priority,
                ))
                main.register_binding(main.Binding(
                    provider_id=provider_id,
                    capability_id="baseline.run",
                ))
            result = main.resolve(main.ResolveRequest(
                capability_id="baseline.run",
                preferred_provider_id="preferred",
            ))
            assert result["provider"]["provider_id"] == "preferred"
            assert result["reason"] == "lowest_weighted_score"
            """
        )

    def test_donor_debt_approval_boolean_controls_eligibility(self):
        self.run_service_code(
            """
            from fastapi import HTTPException
            from app import main
            main.register_provider(main.Provider(
                provider_id="approval-provider", name="Approval",
                provider_type="service", base_url="http://approval:8000",
            ))
            main.register_capability(main.Capability(
                capability_id="approval.run", name="Approval Run",
            ))
            main.register_binding(main.Binding(
                provider_id="approval-provider",
                capability_id="approval.run",
                approval_policy="approval_required",
            ))
            try:
                main.resolve(main.ResolveRequest(capability_id="approval.run"))
            except HTTPException as error:
                assert error.status_code == 404
            else:
                raise AssertionError("approval-required provider was eligible")
            result = main.resolve(main.ResolveRequest(
                capability_id="approval.run",
                allow_approval_required=True,
            ))
            assert result["provider"]["provider_id"] == "approval-provider"
            """
        )

    def test_donor_debt_execute_and_history_surfaces_exist(self):
        self.run_service_code(
            """
            import inspect
            from app import main
            assert any(
                getattr(route, "path", None) == "/execute"
                and "POST" in getattr(route, "methods", set())
                for route in main.app.routes
            )
            assert inspect.iscoroutinefunction(main.execute)
            assert main.executions(limit=200)["executions"] == []
            """
        )

    def test_donor_debt_payload_adapter_surface_and_state_exist(self):
        self.run_service_code(
            """
            from app import execution_contract
            contract = execution_contract.contract()
            adapters = execution_contract.list_adapters()
            assert contract["ok"] is True
            assert "flat_input" in contract["request_shapes"]
            assert adapters["adapter_count"] >= 1
            assert adapters["adapters"][0]["adapter_id"] == (
                "builtin-content-write-flat-input"
            )
            """
        )


if __name__ == "__main__":
    unittest.main()
