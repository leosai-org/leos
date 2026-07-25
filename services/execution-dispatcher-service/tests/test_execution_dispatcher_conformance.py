from __future__ import annotations

import copy
import concurrent.futures
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SERVICE_ROOT.parents[1]
PACKAGE_SRC = REPOSITORY_ROOT / "packages" / "leos-contracts" / "src"
CONTRACT_ROOT = REPOSITORY_ROOT / "contracts"
EXAMPLES = REPOSITORY_ROOT / "examples"

sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(PACKAGE_SRC))
os.environ["LEOS_CONTRACT_ROOT"] = str(CONTRACT_ROOT)
os.environ["EXECUTION_DISPATCHER_DATA_DIR"] = tempfile.mkdtemp(
    prefix="leos-dispatcher-import-"
)

from app import main


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        body: object = None,
        *,
        text: str = "",
        content_type: str = "application/json",
    ):
        self.status_code = status_code
        self._body = body
        self.text = text
        self.headers = {"content-type": content_type}

    def json(self):
        if self._body is None:
            raise ValueError("not JSON")
        return self._body


class FakeClient:
    def __init__(self, outcomes: list[object], calls: list[dict]):
        self.outcomes = outcomes
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, json, headers=None):
        self.calls.append(
            {"url": url, "json": json, "headers": headers or {}}
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class DispatcherConformanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.mkdtemp(prefix="leos-dispatcher-test-")
        main.DATA_DIR = Path(self.temporary)
        main.DB_PATH = main.DATA_DIR / "execution-dispatcher.db"
        main.MAX_RETRIES = 1
        main.migrate()

    def tearDown(self):
        shutil.rmtree(self.temporary)

    def example(self, name: str) -> dict:
        return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))

    def request(self) -> dict:
        return self.example("execution.v1.json")

    def resolution(self, status: str = "RESOLVED") -> dict:
        request = self.request()
        resolution_id = f"resolution-{status.lower().replace('_', '-')}"
        correlation = dict(request["trace"])
        correlation["resolution_id"] = resolution_id
        result = {
            "contract_version": main.RESOLUTION_RESULT_CONTRACT,
            "resolution_id": resolution_id,
            "status": status,
            "capability_id": request["capability_id"],
            "requester": dict(request["requester"]),
            "candidate_evaluations": [],
            "rationale": {"outcome": status.lower()},
            "correlation": correlation,
            "resolved_at": "2026-07-25T01:00:00Z",
        }
        if status == "RESOLVED":
            result["candidate_evaluations"] = [
                {
                    "position": 1,
                    "provider_id": "provider-content-writer",
                    "outcome": "ELIGIBLE",
                    "reasons": [],
                }
            ]
            result["selected_target"] = {
                "provider_id": "provider-content-writer",
                "provider_type": "service",
                "target_ref": {
                    "authority": "capability-manager",
                    "reference_id": "provider-content-writer",
                    "revision": "provider-revision-1",
                },
            }
        elif status == "APPROVAL_PENDING":
            result["candidate_evaluations"] = [
                {
                    "position": 1,
                    "provider_id": "provider-content-writer",
                    "outcome": "APPROVAL_REQUIRED",
                    "reasons": ["approval_grant_required"],
                }
            ]
            result["approval_requirement_ref"] = {
                "authority": "capability-manager",
                "reference_id": f"{resolution_id}:approval",
            }
        elif status == "NO_ELIGIBLE_PROVIDER":
            result["candidate_evaluations"] = [
                {
                    "position": 1,
                    "provider_id": "provider-content-writer",
                    "outcome": "REJECTED",
                    "reasons": ["provider_unhealthy"],
                }
            ]
        elif status == "GOVERNED_ORDER_REQUIRED":
            result["candidate_evaluations"] = [
                {
                    "position": 1,
                    "provider_id": "provider-one",
                    "outcome": "ELIGIBLE",
                    "reasons": [],
                },
                {
                    "position": 2,
                    "provider_id": "provider-two",
                    "outcome": "ELIGIBLE",
                    "reasons": [],
                },
            ]
        main.validate_governed_contract(
            main.RESOLUTION_RESULT_CONTRACT,
            result,
        )
        return result

    def provider(self) -> dict:
        return {
            "provider_id": "provider-content-writer",
            "provider_type": "service",
            "base_url": "http://provider-content-writer:8000/",
            "execute_path": "/invoke",
            "updated_at": "provider-revision-1",
        }

    def install_adapter(
        self,
        *,
        adapter_id: str = "adapter-content-write",
        provider_id: str = "provider-content-writer",
        request_shape: str = "canonical_envelope",
        metadata: dict | None = None,
    ) -> None:
        main.provision_adapter(
            main.AdapterCreate(
                adapter_id=adapter_id,
                capability_id="content.write",
                provider_id=provider_id,
                request_shape=request_shape,
                metadata=metadata or {},
            )
        )

    async def execute_with(
        self,
        resolution: dict,
        outcomes: list[object] | None = None,
        execution_request: dict | None = None,
    ) -> tuple[dict, list[dict]]:
        calls: list[dict] = []
        outcomes = outcomes or [
            FakeResponse(200, {"artifact_ref": "artifact-output-1"})
        ]
        client = FakeClient(outcomes, calls)
        with (
            patch.object(
                main,
                "resolve_capability",
                AsyncMock(return_value=resolution),
            ),
            patch.object(
                main,
                "provider_inventory_record",
                AsyncMock(return_value=self.provider()),
            ),
            patch.object(main.httpx, "AsyncClient", return_value=client),
        ):
            result = await main.execute(execution_request or self.request())
        return result, calls

    async def test_canonical_execution_request_validation(self):
        request = self.request()
        request["legacy_provider_id"] = "provider-one"
        resolver = AsyncMock()
        with patch.object(main, "resolve_capability", resolver):
            with self.assertRaises(HTTPException) as raised:
                await main.execute(request)
        self.assertEqual(422, raised.exception.status_code)
        resolver.assert_not_awaited()

    def test_canonical_resolution_request_construction(self):
        request = self.request()
        built = main.build_resolution_request(
            request,
            requested_at="2026-07-25T01:00:00Z",
        )
        self.assertEqual(
            main.RESOLUTION_REQUEST_CONTRACT,
            built["contract_version"],
        )
        self.assertEqual(request["capability_id"], built["capability_id"])
        self.assertEqual(request["requester"], built["requester"])
        self.assertEqual(request["trace"], built["correlation"])
        self.assertEqual({}, built["constraints"])
        self.assertEqual(
            request["policy"]["effective_intelligence_policy_ref"],
            built["policy"]["effective_intelligence_policy_ref"],
        )

    def test_provider_id_preferred_provider_id_bug_is_removed(self):
        built = main.build_resolution_request(self.request())
        self.assertNotIn("provider_id", built)
        self.assertNotIn("preferred_provider_id", built)
        self.assertNotIn("provider_id", built["constraints"])

    async def test_canonical_capability_manager_response_validation(self):
        invalid = self.resolution()
        invalid["contract_version"] = "legacy-resolution"
        with patch.object(
            main,
            "capability_manager_post",
            AsyncMock(return_value=FakeResponse(200, invalid)),
        ):
            with self.assertRaises(HTTPException) as raised:
                await main.resolve_capability(
                    main.build_resolution_request(self.request())
                )
        self.assertEqual(502, raised.exception.status_code)

    async def test_resolved_target_is_invoked(self):
        result, calls = await self.execute_with(self.resolution())
        self.assertEqual("SUCCESS", result["status"])
        self.assertEqual(1, len(calls))
        self.assertEqual(
            "provider-content-writer",
            result["authorized_target"]["provider_id"],
        )

    async def test_approval_pending_causes_zero_invocation(self):
        result, calls = await self.execute_with(
            self.resolution("APPROVAL_PENDING")
        )
        self.assertEqual("APPROVAL_PENDING", result["status"])
        self.assertEqual(0, result["attempt_summary"]["attempt_count"])
        self.assertEqual([], calls)
        self.assertNotIn("authorized_target", result)

    async def test_no_eligible_provider_causes_zero_invocation(self):
        result, calls = await self.execute_with(
            self.resolution("NO_ELIGIBLE_PROVIDER")
        )
        self.assertEqual("NO_ELIGIBLE_PROVIDER", result["status"])
        self.assertEqual(0, result["attempt_summary"]["attempt_count"])
        self.assertEqual([], calls)

    async def test_governed_order_required_causes_zero_invocation(self):
        result, calls = await self.execute_with(
            self.resolution("GOVERNED_ORDER_REQUIRED")
        )
        self.assertEqual("GOVERNED_ORDER_REQUIRED", result["status"])
        self.assertEqual(0, result["attempt_summary"]["attempt_count"])
        self.assertEqual([], calls)

    def test_adapter_cannot_change_resolved_provider(self):
        self.install_adapter(provider_id="provider-other")
        shape, adapter = main.adapter_selection(
            "content.write",
            self.resolution()["selected_target"],
        )
        self.assertEqual("canonical_envelope", shape)
        self.assertEqual(
            "provider-content-writer",
            adapter["provider_id"],
        )
        self.assertIsNone(adapter["adapter_id"])

    async def test_no_provider_failover(self):
        result, calls = await self.execute_with(
            self.resolution(),
            [FakeResponse(503, {"error": "unavailable"})],
        )
        self.assertEqual("AMBIGUOUS_OUTCOME", result["status"])
        self.assertEqual(1, len(calls))
        self.assertEqual(
            {"provider-content-writer"},
            {result["authorized_target"]["provider_id"]},
        )

    async def test_no_model_failover_or_payload_rewrite(self):
        request = self.request()
        request["input"]["model_id"] = "model-authorized"
        result, calls = await self.execute_with(
            self.resolution(),
            execution_request=request,
        )
        self.assertEqual("SUCCESS", result["status"])
        self.assertEqual(
            "model-authorized",
            calls[0]["json"]["input"]["model_id"],
        )

    async def test_success_is_normalized(self):
        result, _ = await self.execute_with(
            self.resolution(),
            [FakeResponse(200, {"value": 42})],
        )
        self.assertEqual("SUCCESS", result["status"])
        self.assertEqual({"value": 42}, result["normalized_result"])
        self.assertNotIn("provider_response", result)

    async def test_non_2xx_is_ambiguous(self):
        result, _ = await self.execute_with(
            self.resolution(),
            [FakeResponse(400, {"error": "invalid"})],
        )
        self.assertEqual("AMBIGUOUS_OUTCOME", result["status"])
        self.assertTrue(result["error"]["remote_side_effect_possible"])

    async def test_transport_error_is_normalized(self):
        request = httpx.Request("POST", "http://provider/invoke")
        result, _ = await self.execute_with(
            self.resolution(),
            [httpx.ConnectError("connection refused", request=request)],
        )
        self.assertEqual("TRANSPORT_ERROR", result["status"])
        self.assertFalse(result["error"]["remote_side_effect_possible"])

    async def test_ambiguous_outcome_is_normalized(self):
        request = httpx.Request("POST", "http://provider/invoke")
        result, _ = await self.execute_with(
            self.resolution(),
            [httpx.ReadTimeout("response unknown", request=request)],
        )
        self.assertEqual("AMBIGUOUS_OUTCOME", result["status"])
        self.assertTrue(result["error"]["remote_side_effect_possible"])

    async def test_ambiguous_operation_is_not_retried(self):
        self.install_adapter(
            metadata={
                "idempotency_supported": True,
                "safe_same_target_retry": True,
            }
        )
        request_error = httpx.Request("POST", "http://provider/invoke")
        result, calls = await self.execute_with(
            self.resolution(),
            [
                httpx.ReadTimeout("response unknown", request=request_error),
                FakeResponse(200, {"should": "not run"}),
            ],
        )
        self.assertEqual("AMBIGUOUS_OUTCOME", result["status"])
        self.assertEqual(1, len(calls))

    async def test_retry_capability_does_not_grant_retry_authority(self):
        self.install_adapter(
            metadata={
                "idempotency_supported": True,
                "safe_same_target_retry": True,
            }
        )
        result, calls = await self.execute_with(
            self.resolution(),
            [
                FakeResponse(503, {"error": "retryable"}),
                FakeResponse(200, {"value": "complete"}),
            ],
        )
        self.assertEqual("AMBIGUOUS_OUTCOME", result["status"])
        self.assertEqual(1, result["attempt_summary"]["attempt_count"])
        self.assertEqual(1, len(calls))
        self.assertNotIn("Idempotency-Key", calls[0]["headers"])

    async def test_retry_never_reresolves(self):
        self.install_adapter(
            metadata={
                "idempotency_supported": True,
                "safe_same_target_retry": True,
            }
        )
        resolver = AsyncMock(return_value=self.resolution())
        calls: list[dict] = []
        client = FakeClient(
            [
                FakeResponse(503, {"error": "retryable"}),
                FakeResponse(200, {"value": "complete"}),
            ],
            calls,
        )
        with (
            patch.object(main, "resolve_capability", resolver),
            patch.object(
                main,
                "provider_inventory_record",
                AsyncMock(return_value=self.provider()),
            ),
            patch.object(main.httpx, "AsyncClient", return_value=client),
        ):
            await main.execute(self.request())
        self.assertEqual(1, resolver.await_count)
        self.assertEqual(1, len(calls))

    async def test_execution_correlation_equality(self):
        result, _ = await self.execute_with(self.resolution())
        self.assertEqual(
            result["execution_id"],
            result["correlation"]["execution_id"],
        )

    async def test_resolution_reference_equality(self):
        result, _ = await self.execute_with(self.resolution())
        self.assertEqual(
            result["resolution_ref"]["reference_id"],
            result["correlation"]["resolution_id"],
        )

    async def test_attempt_count_list_consistency(self):
        result, _ = await self.execute_with(self.resolution())
        self.assertEqual(
            result["attempt_summary"]["attempt_count"],
            len(result["attempt_summary"]["attempts"]),
        )

    async def test_canonical_result_is_persisted(self):
        result, _ = await self.execute_with(self.resolution())
        stored = main.execution(result["execution_id"])["execution"]
        self.assertEqual(result, stored["result"])
        self.assertEqual(self.request(), stored["request"])
        self.assertEqual(
            result["resolution_ref"]["reference_id"],
            stored["resolution_id"],
        )

    async def test_persistence_survives_close_and_reopen(self):
        result, _ = await self.execute_with(self.resolution())
        with main.connect() as reopened:
            row = reopened.execute(
                """
                SELECT result_json FROM canonical_executions
                WHERE execution_id=?
                """,
                (result["execution_id"],),
            ).fetchone()
        self.assertEqual(result, json.loads(row["result_json"]))

    async def test_execution_retrieval(self):
        result, _ = await self.execute_with(self.resolution())
        retrieved = main.execution(result["execution_id"])
        self.assertTrue(retrieved["ok"])
        self.assertEqual(result, retrieved["execution"]["result"])

    async def test_execution_listing(self):
        result, _ = await self.execute_with(self.resolution())
        listing = main.executions(limit=200)
        self.assertEqual(1, listing["execution_count"])
        self.assertEqual(
            result["execution_id"],
            listing["executions"][0]["execution_id"],
        )

    def test_adapter_selection(self):
        self.install_adapter(request_shape="flat_input")
        shape, adapter = main.adapter_selection(
            "content.write",
            self.resolution()["selected_target"],
        )
        self.assertEqual("flat_input", shape)
        self.assertEqual("adapter-content-write", adapter["adapter_id"])

    def test_provider_url_construction(self):
        self.assertEqual(
            "http://provider-content-writer:8000/invoke",
            main.target_url(self.provider()),
        )

    async def test_provider_inventory_materializes_only_resolved_target(self):
        response = FakeResponse(
            200,
            {
                "providers": [
                    self.provider(),
                    {
                        "provider_id": "provider-unselected",
                        "base_url": "http://provider-unselected:8000",
                        "updated_at": "other-revision",
                    },
                ]
            },
        )
        getter = AsyncMock(return_value=response)
        with patch.object(main, "capability_manager_get", getter):
            provider = await main.provider_inventory_record(
                "content.write",
                self.resolution()["selected_target"],
            )
        self.assertEqual("provider-content-writer", provider["provider_id"])
        getter.assert_awaited_once_with(
            "/providers",
            params={"capability_id": "content.write", "limit": 2000},
        )

    def test_health_and_contract_endpoints_are_canonical(self):
        health = main.health()
        contract = main.contract()
        self.assertEqual(main.EXECUTION_CONTRACT, health["request_contract"])
        self.assertEqual(
            main.EXECUTION_RESULT_CONTRACT,
            health["result_contract"],
        )
        self.assertEqual(
            main.RESOLUTION_REQUEST_CONTRACT,
            contract["resolution_request_contract"],
        )
        self.assertNotIn("legacy_wrapped", contract["request_shapes"])

    async def test_raw_credentials_are_not_persisted(self):
        request = self.request()
        request["input"]["api_key"] = "credential-material-for-test"
        calls: list[dict] = []
        client = FakeClient(
            [FakeResponse(200, {"value": "complete"})],
            calls,
        )
        with (
            patch.object(
                main,
                "resolve_capability",
                AsyncMock(return_value=self.resolution()),
            ),
            patch.object(
                main,
                "provider_inventory_record",
                AsyncMock(return_value=self.provider()),
            ),
            patch.object(main.httpx, "AsyncClient", return_value=client),
        ):
            await main.execute(request)
        with main.connect() as db:
            row = db.execute(
                "SELECT * FROM canonical_executions"
            ).fetchone()
        self.assertNotIn(
            "credential-material-for-test",
            json.dumps(dict(row)),
        )

    async def test_malformed_request_invokes_nothing(self):
        request = self.request()
        request.pop("requester")
        resolver = AsyncMock()
        with patch.object(main, "resolve_capability", resolver):
            with self.assertRaises(HTTPException):
                await main.execute(request)
        resolver.assert_not_awaited()

    async def test_duplicate_execution_id_invokes_nothing(self):
        first, _ = await self.execute_with(
            self.resolution("NO_ELIGIBLE_PROVIDER")
        )
        resolver = AsyncMock()
        with patch.object(main, "resolve_capability", resolver):
            duplicate = await main.execute(self.request())
        self.assertEqual(first, duplicate)
        resolver.assert_not_awaited()

    async def test_malformed_capability_result_invokes_nothing(self):
        invalid = self.resolution()
        invalid["selected_target"]["provider_id"] = "not-evaluated"
        provider_lookup = AsyncMock()
        with (
            patch.object(
                main,
                "capability_manager_post",
                AsyncMock(return_value=FakeResponse(200, invalid)),
            ),
            patch.object(
                main,
                "provider_inventory_record",
                provider_lookup,
            ),
        ):
            with self.assertRaises(HTTPException):
                await main.execute(self.request())
        provider_lookup.assert_not_awaited()

    async def test_non_json_provider_output_is_normalized(self):
        result, _ = await self.execute_with(
            self.resolution(),
            [
                FakeResponse(
                    200,
                    None,
                    text="provider text",
                    content_type="text/plain; charset=utf-8",
                )
            ],
        )
        self.assertEqual(
            {
                "content": "provider text",
                "media_type": "text/plain",
            },
            result["normalized_result"],
        )
        self.assertNotIn("raw", result["normalized_result"])

    async def test_all_returned_results_validate_canonically(self):
        for status in (
            "APPROVAL_PENDING",
            "NO_ELIGIBLE_PROVIDER",
            "GOVERNED_ORDER_REQUIRED",
        ):
            with self.subTest(status=status):
                request = self.request()
                request["execution_id"] = f"execution-{status.lower()}"
                request["trace"]["execution_id"] = request["execution_id"]
                resolution = self.resolution(status)
                resolution["correlation"]["execution_id"] = request[
                    "execution_id"
                ]
                result, _ = await self.execute_with(
                    resolution,
                    execution_request=request,
                )
                main.validate_governed_contract(
                    main.EXECUTION_RESULT_CONTRACT,
                    result,
                )
        request = self.request()
        request["execution_id"] = "execution-resolved-validation"
        request["trace"]["execution_id"] = request["execution_id"]
        resolution = self.resolution()
        resolution["correlation"]["execution_id"] = request["execution_id"]
        result, _ = await self.execute_with(
            resolution,
            execution_request=request,
        )
        main.validate_governed_contract(
            main.EXECUTION_RESULT_CONTRACT,
            result,
        )

    def test_non_destructive_migration_retains_donor_table(self):
        with main.connect() as db:
            db.execute(
                "CREATE TABLE executions(execution_id TEXT PRIMARY KEY)"
            )
            db.execute(
                "INSERT INTO executions VALUES('legacy-execution')"
            )
        main.migrate()
        with main.connect() as db:
            self.assertEqual(
                "legacy-execution",
                db.execute(
                    "SELECT execution_id FROM executions"
                ).fetchone()["execution_id"],
            )
            self.assertIn("canonical_executions", main.table_names(db))

    def test_contract_surface_has_no_selection_api(self):
        paths = set(main.app.openapi()["paths"])
        self.assertIn("/execute", paths)
        self.assertIn("/adapters", paths)
        self.assertNotIn("post", main.app.openapi()["paths"]["/adapters"])
        self.assertNotIn("/resolve", paths)
        self.assertFalse(
            any("rank" in path or "select" in path for path in paths)
        )

    async def test_credentialed_target_is_rejected_without_invocation(self):
        resolution = self.resolution()
        resolution["selected_target"]["credential_ref"] = {
            "authority": "secret-manager",
            "reference_id": "credential-reference-1",
        }
        main.validate_governed_contract(
            main.RESOLUTION_RESULT_CONTRACT,
            resolution,
        )
        result, calls = await self.execute_with(resolution)
        self.assertEqual("REJECTED", result["status"])
        self.assertEqual(
            "credential_boundary_unavailable",
            result["error"]["code"],
        )
        self.assertEqual([], calls)

    def test_resolved_revision_is_required_by_contract(self):
        resolution = self.resolution()
        resolution["selected_target"]["target_ref"].pop("revision")
        with self.assertRaises(main.ContractValidationError):
            main.validate_governed_contract(
                main.RESOLUTION_RESULT_CONTRACT, resolution
            )

    async def test_stale_revision_is_control_plane_failure(self):
        provider = self.provider()
        provider["updated_at"] = "provider-revision-2"
        with (
            patch.object(
                main,
                "resolve_capability",
                AsyncMock(return_value=self.resolution()),
            ),
            patch.object(
                main,
                "capability_manager_get",
                AsyncMock(
                    return_value=FakeResponse(
                        200, {"providers": [provider]}
                    )
                ),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await main.execute(self.request())
        self.assertEqual(
            "resolved_provider_revision_mismatch",
            raised.exception.detail["code"],
        )
        with main.connect() as db:
            self.assertIsNone(
                db.execute("SELECT * FROM execution_claims").fetchone()
            )

    async def test_adapter_metadata_cannot_redirect_endpoint(self):
        self.install_adapter(
            metadata={
                "endpoint": "http://attacker.invalid/invoke",
                "url": "http://attacker.invalid",
                "provider": "provider-other",
                "target": "provider-other",
                "model": "model-other",
            }
        )
        result, calls = await self.execute_with(self.resolution())
        self.assertEqual("SUCCESS", result["status"])
        self.assertEqual(
            "http://provider-content-writer:8000/invoke",
            calls[0]["url"],
        )

    async def test_different_request_fingerprint_conflicts(self):
        await self.execute_with(self.resolution())
        changed = self.request()
        changed["input"]["topic"] = "different request"
        with self.assertRaises(HTTPException) as raised:
            await main.execute(changed)
        self.assertEqual(
            "execution_identity_conflict",
            raised.exception.detail["code"],
        )

    async def test_in_flight_is_durable_before_transmission(self):
        observed: list[str] = []

        class InspectingClient(FakeClient):
            async def post(client_self, url, json, headers=None):
                with main.connect() as db:
                    attempt = db.execute(
                        "SELECT status FROM canonical_invocation_attempts"
                    ).fetchone()
                    claim = db.execute(
                        "SELECT lifecycle_state FROM execution_claims"
                    ).fetchone()
                observed.extend(
                    [attempt["status"], claim["lifecycle_state"]]
                )
                return await super().post(url, json, headers)

        calls: list[dict] = []
        with (
            patch.object(
                main,
                "resolve_capability",
                AsyncMock(return_value=self.resolution()),
            ),
            patch.object(
                main,
                "provider_inventory_record",
                AsyncMock(return_value=self.provider()),
            ),
            patch.object(
                main.httpx,
                "AsyncClient",
                return_value=InspectingClient(
                    [FakeResponse(200, {"ok": True})], calls
                ),
            ),
        ):
            await main.execute(self.request())
        self.assertEqual(["IN_FLIGHT", "IN_FLIGHT"], observed)

    async def test_orphaned_in_flight_recovers_as_ambiguous(self):
        request = self.request()
        main.claim_execution(request)
        resolution = self.resolution()
        main.store_claim_resolution(request["execution_id"], resolution)
        main.journal_attempt_in_flight(
            request["execution_id"],
            "attempt-orphaned",
            1,
            "provider-content-writer",
            "http://provider-content-writer:8000/invoke",
            "canonical_envelope",
            "2026-07-25T01:00:00Z",
            {"payload": {"safe": True}},
        )
        resolver = AsyncMock()
        with patch.object(main, "resolve_capability", resolver):
            result = await main.execute(request)
        self.assertEqual("AMBIGUOUS_OUTCOME", result["status"])
        self.assertTrue(result["error"]["remote_side_effect_possible"])
        resolver.assert_not_awaited()

    async def test_inventory_outage_is_not_rejected(self):
        with (
            patch.object(
                main,
                "resolve_capability",
                AsyncMock(return_value=self.resolution()),
            ),
            patch.object(
                main,
                "capability_manager_get",
                AsyncMock(
                    side_effect=httpx.ConnectError(
                        "inventory unavailable",
                        request=httpx.Request(
                            "GET", "http://capability-manager/providers"
                        ),
                    )
                ),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await main.execute(self.request())
        self.assertEqual(502, raised.exception.status_code)

    async def test_malformed_inventory_is_not_rejected(self):
        with (
            patch.object(
                main,
                "resolve_capability",
                AsyncMock(return_value=self.resolution()),
            ),
            patch.object(
                main,
                "capability_manager_get",
                AsyncMock(return_value=FakeResponse(200, {"providers": {}})),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await main.execute(self.request())
        self.assertEqual(502, raised.exception.status_code)
        self.assertEqual(
            "invalid_provider_inventory_response",
            raised.exception.detail["code"],
        )

    async def test_active_same_id_never_invokes(self):
        request = self.request()
        main.claim_execution(request)
        resolver = AsyncMock()
        with patch.object(main, "resolve_capability", resolver):
            with self.assertRaises(HTTPException) as raised:
                await main.execute(request)
        self.assertEqual(
            "execution_already_active", raised.exception.detail["code"]
        )
        resolver.assert_not_awaited()

    def test_concurrent_duplicate_claim_has_one_owner(self):
        request = self.request()

        def attempt_claim():
            try:
                main.claim_execution(request)
                return "owned"
            except HTTPException as error:
                return error.detail["code"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: attempt_claim(), range(2)))
        self.assertEqual(
            ["execution_already_active", "owned"],
            sorted(outcomes),
        )

    async def test_legitimate_sensitive_named_fields_are_transmitted(self):
        request = self.request()
        request["input"].update(
            {"token": "game-piece", "key": "map-key", "secret": "clue"}
        )
        result, calls = await self.execute_with(
            self.resolution(), execution_request=request
        )
        self.assertEqual("SUCCESS", result["status"])
        self.assertEqual("game-piece", calls[0]["json"]["input"]["token"])
        self.assertEqual("map-key", calls[0]["json"]["input"]["key"])
        self.assertEqual("clue", calls[0]["json"]["input"]["secret"])
        stored = main.execution(result["execution_id"])["execution"]
        self.assertEqual("game-piece", stored["request"]["input"]["token"])
        self.assertEqual("map-key", stored["request"]["input"]["key"])
        self.assertEqual("clue", stored["request"]["input"]["secret"])


if __name__ == "__main__":
    unittest.main()
