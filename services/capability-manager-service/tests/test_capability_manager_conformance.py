from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SERVICE_ROOT.parents[1]
PACKAGE_SRC = REPOSITORY_ROOT / "packages" / "leos-contracts" / "src"
TEST_DATA = tempfile.TemporaryDirectory()
os.environ["CAPABILITY_MANAGER_DATA_DIR"] = TEST_DATA.name
os.environ["LEOS_CONTRACT_ROOT"] = str(REPOSITORY_ROOT / "contracts")
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(PACKAGE_SRC))

from fastapi import HTTPException
from leos_contracts import ContractValidationError, validate_contract

from app import main


class CapabilityManagerConformanceTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        TEST_DATA.cleanup()

    def setUp(self) -> None:
        with main.connect() as db:
            for table in (
                "canonical_resolutions",
                "provider_capabilities",
                "providers",
                "capabilities",
                "events",
            ):
                db.execute(f"DELETE FROM {table}")

    def request(
        self,
        *,
        capability_id: str = "baseline.run",
        order: list[str] | None = None,
        approval_refs: list[dict] | None = None,
    ) -> dict:
        constraints = {}
        if order is not None:
            constraints[main.PROVIDER_ORDER_CONSTRAINT] = order
        policy = {}
        if approval_refs is not None:
            policy["approval_grant_refs"] = approval_refs
        return {
            "contract_version": main.REQUEST_CONTRACT,
            "capability_id": capability_id,
            "requester": {"type": "employee", "id": "employee-test"},
            "constraints": constraints,
            "policy": policy,
            "correlation": {
                "contract_version": main.CORRELATION_CONTRACT,
                "job_id": "job-test",
                "execution_id": "execution-test",
            },
            "requested_at": "2026-07-24T18:00:00Z",
        }

    def register_capability(
        self,
        *,
        capability_id: str = "baseline.run",
        approval_required: bool = False,
    ) -> None:
        main.register_capability(
            main.Capability(
                capability_id=capability_id,
                name=capability_id,
                approval_required=approval_required,
            )
        )

    def register_provider(
        self,
        provider_id: str,
        *,
        priority: int = 100,
        status: str = "active",
        enabled: bool = True,
        approval_policy: str = "allowed",
    ) -> None:
        main.register_provider(
            main.Provider(
                provider_id=provider_id,
                name=provider_id,
                provider_type="service",
                base_url=f"http://{provider_id}:8000",
                priority=priority,
                status=status,
            )
        )
        main.register_binding(
            main.Binding(
                provider_id=provider_id,
                capability_id="baseline.run",
                enabled=enabled,
                approval_policy=approval_policy,
            )
        )

    def assert_canonical_result(self, result: dict) -> None:
        self.assertIsNone(validate_contract(main.RESULT_CONTRACT, result))

    def test_canonical_request_is_validated_before_resolution(self):
        malformed = self.request()
        malformed.pop("requester")
        with self.assertRaises(HTTPException) as raised:
            main.resolve(malformed)
        self.assertEqual(422, raised.exception.status_code)
        self.assertEqual("invalid_contract", raised.exception.detail["code"])
        with main.connect() as db:
            count = db.execute(
                "SELECT COUNT(*) FROM canonical_resolutions"
            ).fetchone()[0]
        self.assertEqual(0, count)

    def test_provider_capability_and_binding_registration_remain_supported(self):
        self.register_capability()
        self.register_provider("provider-one")
        with main.connect() as db:
            self.assertEqual(
                1,
                db.execute("SELECT COUNT(*) FROM providers").fetchone()[0],
            )
            self.assertEqual(
                1,
                db.execute("SELECT COUNT(*) FROM capabilities").fetchone()[0],
            )
            self.assertEqual(
                1,
                db.execute(
                    "SELECT COUNT(*) FROM provider_capabilities"
                ).fetchone()[0],
            )

    def test_first_explicitly_ranked_eligible_candidate_is_selected(self):
        self.register_capability()
        self.register_provider("provider-a")
        self.register_provider("provider-b")
        result = main.resolve(
            self.request(order=["provider-b", "provider-a"])
        )
        self.assertEqual("RESOLVED", result["status"])
        self.assertEqual(
            "provider-b",
            result["selected_target"]["provider_id"],
        )
        self.assertEqual(1, result["rationale"]["selected_position"])
        self.assert_canonical_result(result)

    def test_invalid_candidate_is_skipped_for_later_eligible_candidate(self):
        self.register_capability()
        self.register_provider("provider-valid")
        result = main.resolve(
            self.request(order=["not-bound", "provider-valid"])
        )
        self.assertEqual(
            ["REJECTED", "ELIGIBLE"],
            [item["outcome"] for item in result["candidate_evaluations"]],
        )
        self.assertEqual(
            "provider-valid",
            result["selected_target"]["provider_id"],
        )

    def test_internal_scores_and_priorities_do_not_reorder_candidates(self):
        self.register_capability()
        self.register_provider("provider-high-priority", priority=1)
        self.register_provider("provider-user-first", priority=999)
        result = main.resolve(
            self.request(
                order=["provider-user-first", "provider-high-priority"]
            )
        )
        self.assertEqual(
            "provider-user-first",
            result["selected_target"]["provider_id"],
        )
        self.assertNotIn("score", json.dumps(result))

    def test_multiple_eligible_without_order_are_not_selected(self):
        self.register_capability()
        self.register_provider("provider-z", priority=1)
        self.register_provider("provider-a", priority=999)
        result = main.resolve(self.request())
        self.assertEqual("GOVERNED_ORDER_REQUIRED", result["status"])
        self.assertNotIn("selected_target", result)
        self.assertEqual(
            {
                ("provider-a", "ELIGIBLE"),
                ("provider-z", "ELIGIBLE"),
            },
            {
                (item["provider_id"], item["outcome"])
                for item in result["candidate_evaluations"]
            },
        )
        self.assertEqual(
            "governed_order_required",
            result["rationale"]["outcome"],
        )
        self.assert_canonical_result(result)

    def test_one_eligible_provider_without_order_may_be_selected(self):
        self.register_capability()
        self.register_provider("only-provider", priority=999)
        result = main.resolve(self.request())
        self.assertEqual("RESOLVED", result["status"])
        self.assertEqual(
            "only-provider",
            result["selected_target"]["provider_id"],
        )

    def test_unlisted_providers_are_not_appended_to_explicit_order(self):
        self.register_capability()
        self.register_provider("listed-disabled", enabled=False)
        self.register_provider("unlisted-eligible")
        result = main.resolve(
            self.request(order=["listed-disabled"])
        )
        self.assertEqual("NO_ELIGIBLE_PROVIDER", result["status"])
        self.assertEqual(
            ["listed-disabled"],
            [
                item["provider_id"]
                for item in result["candidate_evaluations"]
            ],
        )
        self.assertNotIn("selected_target", result)

    def test_provider_identifier_spelling_never_creates_selection_order(self):
        self.register_capability()
        self.register_provider("aaa-provider")
        self.register_provider("zzz-provider")
        first = main.resolve(self.request())
        with main.connect() as db:
            db.execute("DELETE FROM provider_capabilities")
            db.execute("DELETE FROM providers")
        self.register_provider("mmm-provider")
        self.register_provider("nnn-provider")
        second = main.resolve(self.request())
        for result in (first, second):
            self.assertEqual("GOVERNED_ORDER_REQUIRED", result["status"])
            self.assertNotIn("selected_target", result)
            self.assertTrue(
                all(
                    item["outcome"] == "ELIGIBLE"
                    for item in result["candidate_evaluations"]
                )
            )

    def test_no_eligible_provider_returns_canonical_outcome(self):
        self.register_capability()
        result = main.resolve(self.request())
        self.assertEqual("NO_ELIGIBLE_PROVIDER", result["status"])
        self.assertEqual([], result["candidate_evaluations"])
        self.assertNotIn("selected_target", result)
        self.assert_canonical_result(result)

    def test_approval_pending_blocks_lower_ranked_candidate(self):
        self.register_capability()
        self.register_provider(
            "provider-approval",
            approval_policy="approval_required",
        )
        self.register_provider("provider-lower")
        result = main.resolve(
            self.request(order=["provider-approval", "provider-lower"])
        )
        self.assertEqual("APPROVAL_PENDING", result["status"])
        self.assertEqual(1, len(result["candidate_evaluations"]))
        self.assertEqual(
            "APPROVAL_REQUIRED",
            result["candidate_evaluations"][0]["outcome"],
        )
        self.assertNotIn("selected_target", result)
        self.assert_canonical_result(result)

    def test_caller_approval_boolean_is_rejected(self):
        request = self.request()
        request["constraints"]["allow_approval_required"] = True
        with self.assertRaises(HTTPException) as raised:
            main.resolve(request)
        self.assertEqual(422, raised.exception.status_code)

    def test_opaque_approval_reference_does_not_authorize_candidate(self):
        self.register_capability()
        self.register_provider(
            "provider-approval",
            approval_policy="approval_required",
        )
        result = main.resolve(
            self.request(
                order=["provider-approval"],
                approval_refs=[
                    {
                        "authority": "approval-authority",
                        "reference_id": "grant-test",
                    }
                ],
            )
        )
        self.assertEqual("APPROVAL_PENDING", result["status"])
        self.assertNotIn("selected_target", result)
        self.assertEqual(
            "APPROVAL_REQUIRED",
            result["candidate_evaluations"][0]["outcome"],
        )

    def test_unhealthy_candidate_is_ineligible_without_reordering(self):
        self.register_capability()
        self.register_provider("provider-unhealthy")
        self.register_provider("provider-healthy")
        with main.connect() as db:
            db.execute(
                "UPDATE providers SET health_state='unhealthy' "
                "WHERE provider_id='provider-unhealthy'"
            )
            db.execute(
                "UPDATE providers SET health_state='healthy' "
                "WHERE provider_id='provider-healthy'"
            )
        result = main.resolve(
            self.request(
                order=["provider-unhealthy", "provider-healthy"]
            )
        )
        self.assertEqual(
            "provider_unhealthy",
            result["candidate_evaluations"][0]["reasons"][0],
        )
        self.assertEqual(
            "provider-healthy",
            result["selected_target"]["provider_id"],
        )

    def test_disabled_provider_and_binding_are_ineligible(self):
        self.register_capability()
        self.register_provider("provider-disabled", status="disabled")
        self.register_provider("binding-disabled", enabled=False)
        result = main.resolve(
            self.request(order=["provider-disabled", "binding-disabled"])
        )
        self.assertEqual("NO_ELIGIBLE_PROVIDER", result["status"])
        self.assertEqual(
            ["provider_disabled", "binding_disabled"],
            [
                item["reasons"][0]
                for item in result["candidate_evaluations"]
            ],
        )

    def test_resolution_correlation_is_preserved_and_extended(self):
        self.register_capability()
        self.register_provider("provider-one")
        request = self.request(order=["provider-one"])
        result = main.resolve(request)
        self.assertEqual("job-test", result["correlation"]["job_id"])
        self.assertEqual(
            "execution-test",
            result["correlation"]["execution_id"],
        )
        self.assertEqual(
            result["resolution_id"],
            result["correlation"]["resolution_id"],
        )

    def test_persisted_resolution_validates_and_survives_reopen(self):
        self.register_capability()
        self.register_provider("provider-one")
        result = main.resolve(self.request(order=["provider-one"]))
        with main.connect() as reopened:
            stored = json.loads(
                reopened.execute(
                    "SELECT result_json FROM canonical_resolutions "
                    "WHERE resolution_id=?",
                    (result["resolution_id"],),
                ).fetchone()["result_json"]
            )
        self.assertEqual(result, stored)
        self.assert_canonical_result(stored)
        self.assertEqual(
            stored,
            main.resolution(result["resolution_id"]),
        )

    def test_execute_adapter_and_execution_history_routes_are_removed(self):
        paths = {
            getattr(route, "path", None)
            for route in main.app.routes
        }
        self.assertNotIn("/execute", paths)
        self.assertNotIn("/executions", paths)
        self.assertNotIn("/execution-contract/adapters", paths)
        self.assertFalse(hasattr(main, "execute"))

    def test_fresh_v2_database_has_no_legacy_authority_tables(self):
        with main.connect() as db:
            tables = {
                row["name"]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        self.assertNotIn("resolutions", tables)
        self.assertNotIn("executions", tables)
        self.assertNotIn("provider_payload_adapters", tables)
        self.assertIn("canonical_resolutions", tables)

    def test_non_destructive_migration_preserves_legacy_tables(self):
        with tempfile.TemporaryDirectory() as temporary:
            original_data_dir = main.DATA_DIR
            original_db_path = main.DB_PATH
            try:
                main.DATA_DIR = Path(temporary)
                main.DB_PATH = main.DATA_DIR / "capability-manager.db"
                with sqlite3.connect(main.DB_PATH) as db:
                    for table in (
                        "resolutions",
                        "executions",
                        "provider_payload_adapters",
                    ):
                        db.execute(
                            f"CREATE TABLE {table} (legacy_value TEXT)"
                        )
                        db.execute(
                            f"INSERT INTO {table} VALUES ('preserved')"
                        )
                main.migrate()
                with main.connect() as db:
                    for table in (
                        "resolutions",
                        "executions",
                        "provider_payload_adapters",
                    ):
                        self.assertEqual(
                            "preserved",
                            db.execute(
                                f"SELECT legacy_value FROM {table}"
                            ).fetchone()[0],
                        )
                    self.assertIsNotNone(
                        db.execute(
                            "SELECT 1 FROM sqlite_master "
                            "WHERE type='table' "
                            "AND name='canonical_resolutions'"
                        ).fetchone()
                    )
            finally:
                main.DATA_DIR = original_data_dir
                main.DB_PATH = original_db_path

    def test_raw_credentials_are_rejected_and_not_persisted(self):
        self.register_capability()
        self.register_provider("provider-one")
        request = self.request(order=["provider-one"])
        request["constraints"]["api_key"] = "forbidden-placeholder"
        with self.assertRaises(HTTPException) as raised:
            main.resolve(request)
        self.assertEqual(
            "raw_credentials_forbidden",
            raised.exception.detail["code"],
        )
        with main.connect() as db:
            self.assertEqual(
                0,
                db.execute(
                    "SELECT COUNT(*) FROM canonical_resolutions"
                ).fetchone()[0],
            )

    def test_inventory_metadata_rejects_raw_credentials(self):
        with self.assertRaises(HTTPException):
            main.register_provider(
                main.Provider(
                    provider_id="provider-secret",
                    name="provider-secret",
                    provider_type="service",
                    metadata={"api_key": "forbidden-placeholder"},
                )
            )
        with main.connect() as db:
            stored = db.execute(
                "SELECT 1 FROM providers WHERE provider_id='provider-secret'"
            ).fetchone()
        self.assertIsNone(stored)

    def test_health_reports_only_canonical_resolution_authority(self):
        result = main.health()
        self.assertIn("canonical_resolution_count", result)
        self.assertNotIn("execution_count", result)


if __name__ == "__main__":
    unittest.main()
