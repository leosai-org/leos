from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient


SERVICE_ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = tempfile.TemporaryDirectory()
os.environ["MODEL_REGISTRY_DATA_DIR"] = TEST_DATA.name
os.environ["MODEL_REGISTRY_DB"] = str(Path(TEST_DATA.name) / "registry.db")
sys.path.insert(0, str(SERVICE_ROOT))

from app import main


class ModelAuthorityConformanceTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        TEST_DATA.cleanup()

    def setUp(self) -> None:
        main.migrate()
        with main.connect() as db:
            db.execute("DELETE FROM model_registry_events")
            db.execute("DELETE FROM model_runtime_bindings")
            db.execute("DELETE FROM models")
        self.client = TestClient(main.app)
        self.provider_revision = "provider-revision-1"
        self.verifier = patch.object(
            main,
            "verify_provider_reference",
            new=AsyncMock(return_value=None),
        )
        self.verify_provider = self.verifier.start()
        self.addCleanup(self.verifier.stop)

    def model(self, model_id: str = "qwen-2.5-7b-instruct") -> dict:
        return {
            "model_id": model_id,
            "display_name": "Qwen 2.5 7B Instruct",
            "family": "qwen2.5",
            "publisher": "Qwen",
            "version": "2.5",
            "architecture": "transformer",
            "parameter_count": 7_000_000_000,
            "quantization": "Q4_K_M",
            "modalities": ["text"],
            "capabilities": ["text-generation", "reasoning"],
            "context_window_tokens": 32768,
            "runtime_requirements": {"memory_mb_min": 6000},
            "enabled": True,
            "metadata": {"source": "governed-test"},
        }

    def binding(
        self,
        binding_id: str = "binding-qwen-lucy",
        *,
        model_id: str = "qwen-2.5-7b-instruct",
        provider_id: str = "lucy-ollama",
        alias: str = "qwen2.5:7b-instruct",
    ) -> dict:
        return {
            "binding_id": binding_id,
            "model_id": model_id,
            "provider_id": provider_id,
            "provider_ref": {
                "authority": "capability-manager",
                "reference_id": provider_id,
                "revision": self.provider_revision,
            },
            "runtime_model_ref": alias,
            "runtime_type": "ollama",
            "enabled": True,
            "availability": {
                "state": "available",
                "observed_at": "2026-07-25T18:00:00Z",
                "source": "runtime-observer",
            },
            "runtime_requirements": {"vram_mb_min": 6000},
            "metadata": {"native_digest": "sha256:evidence-only"},
        }

    def register_model(self, model_id: str = "qwen-2.5-7b-instruct") -> dict:
        response = self.client.post("/models", json=self.model(model_id))
        self.assertEqual(200, response.status_code, response.text)
        return response.json()["model"]

    def register_binding(self, **kwargs: str) -> dict:
        response = self.client.post("/bindings", json=self.binding(**kwargs))
        self.assertEqual(200, response.status_code, response.text)
        return response.json()["binding"]

    def test_health_reports_service_and_schema(self):
        response = self.client.get("/health")
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(
            "model-registry.inventory.provisional-v1",
            response.json()["service_contract"],
        )

    def test_model_registration_and_stable_identity(self):
        record = self.register_model()
        self.assertEqual("qwen-2.5-7b-instruct", record["model_id"])
        self.assertTrue(record["revision"].startswith("sha256:"))

    def test_model_read_and_list_are_deterministic(self):
        self.register_model("model-z")
        self.register_model("model-a")
        listed = self.client.get("/models").json()
        self.assertEqual(["model-a", "model-z"], [m["model_id"] for m in listed["models"]])
        fetched = self.client.get("/models/model-a").json()["model"]
        self.assertEqual("model-a", fetched["model_id"])

    def test_duplicate_registration_is_idempotent(self):
        first = self.client.post("/models", json=self.model()).json()
        second = self.client.post("/models", json=self.model()).json()
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(first["model"], second["model"])

    def test_conflicting_duplicate_requires_explicit_update(self):
        self.register_model()
        changed = self.model()
        changed["display_name"] = "Changed"
        response = self.client.post("/models", json=changed)
        self.assertEqual(409, response.status_code)

    def test_material_model_update_changes_revision(self):
        before = self.register_model()
        response = self.client.patch(
            f"/models/{before['model_id']}",
            json={
                "expected_revision": before["revision"],
                "context_window_tokens": 65536,
            },
        )
        self.assertEqual(200, response.status_code)
        after = response.json()["model"]
        self.assertNotEqual(before["revision"], after["revision"])
        self.assertEqual(before["created_at"], after["created_at"])

    def test_noop_model_update_preserves_revision_and_timestamp(self):
        before = self.register_model()
        after = self.client.patch(
            f"/models/{before['model_id']}",
            json={
                "expected_revision": before["revision"],
                "display_name": before["display_name"],
            },
        ).json()
        self.assertFalse(after["changed"])
        self.assertEqual(before, after["model"])

    def test_model_enablement_is_fact_not_preference(self):
        before = self.register_model()
        after = self.client.patch(
            f"/models/{before['model_id']}",
            json={"expected_revision": before["revision"], "enabled": False},
        ).json()["model"]
        self.assertFalse(after["enabled"])
        self.assertNotIn("rank", json.dumps(after).lower())
        self.assertNotIn("preferred", json.dumps(after).lower())

    def test_unknown_identity_facts_may_be_enriched(self):
        request = self.model()
        for field in main.IDENTITY_FIELDS:
            request[field] = None
        before = self.client.post("/models", json=request).json()["model"]
        updates = {
            "expected_revision": before["revision"],
            "version": "2.5",
            "architecture": "transformer",
            "parameter_count": 7_000_000_000,
            "quantization": "Q4_K_M",
        }
        response = self.client.patch(
            f"/models/{before['model_id']}", json=updates
        )
        self.assertEqual(200, response.status_code, response.text)

    def test_known_identity_facts_cannot_change(self):
        replacements = {
            "version": "3.0",
            "architecture": "different-architecture",
            "parameter_count": 14_000_000_000,
            "quantization": "Q8",
        }
        for field, replacement in replacements.items():
            with self.subTest(field=field):
                before = self.register_model(f"model-{field}")
                response = self.client.patch(
                    f"/models/{before['model_id']}",
                    json={
                        "expected_revision": before["revision"],
                        field: replacement,
                    },
                )
                self.assertEqual(409, response.status_code)
                self.assertEqual(
                    "model_identity_conflict",
                    response.json()["detail"]["code"],
                )

    def test_capability_and_modality_order_are_canonical_sets(self):
        first_request = self.model()
        first = self.client.post("/models", json=first_request).json()["model"]
        reordered = self.model()
        reordered["capabilities"] = list(reversed(reordered["capabilities"]))
        reordered["modalities"] = ["text", "text"]
        second = self.client.post("/models", json=reordered).json()
        self.assertFalse(second["changed"])
        self.assertEqual(first["revision"], second["model"]["revision"])
        self.assertEqual(sorted(set(first_request["capabilities"])), first["capabilities"])

    def test_metadata_dictionary_order_does_not_change_revision(self):
        request = self.model()
        request["metadata"] = {"outer": {"b": 2, "a": 1}, "source": "test"}
        first = self.client.post("/models", json=request).json()["model"]
        request["metadata"] = {"source": "test", "outer": {"a": 1, "b": 2}}
        second = self.client.post("/models", json=request).json()["model"]
        self.assertEqual(first["revision"], second["revision"])

    def test_model_patch_requires_current_revision(self):
        before = self.register_model()
        changed = self.client.patch(
            f"/models/{before['model_id']}",
            json={
                "expected_revision": before["revision"],
                "display_name": "Changed once",
            },
        ).json()["model"]
        stale = self.client.patch(
            f"/models/{before['model_id']}",
            json={
                "expected_revision": before["revision"],
                "enabled": False,
            },
        )
        self.assertEqual(409, stale.status_code)
        self.assertEqual("revision_conflict", stale.json()["detail"]["code"])
        self.assertEqual(
            changed["revision"],
            self.client.get(f"/models/{before['model_id']}").json()["model"][
                "revision"
            ],
        )

    def test_concurrent_identical_model_registration_is_idempotent(self):
        def register() -> tuple[int, bool]:
            response = TestClient(main.app).post("/models", json=self.model())
            return response.status_code, response.json().get("changed", False)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: register(), range(2)))
        self.assertEqual([200, 200], sorted(item[0] for item in results))
        self.assertEqual([False, True], sorted(item[1] for item in results))

    def test_concurrent_conflicting_model_registration_is_deterministic(self):
        requests = [self.model(), self.model()]
        requests[1]["display_name"] = "Conflicting identity registration"

        def register(request: dict) -> int:
            return TestClient(main.app).post("/models", json=request).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(register, requests))
        self.assertEqual([200, 409], sorted(statuses))

    def test_simultaneous_model_patches_cannot_erase_each_other(self):
        before = self.register_model()
        requests = (
            {
                "expected_revision": before["revision"],
                "display_name": "Concurrent display change",
            },
            {
                "expected_revision": before["revision"],
                "enabled": False,
            },
        )

        def update(request: dict) -> int:
            return TestClient(main.app).patch(
                f"/models/{before['model_id']}", json=request
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(update, requests))
        self.assertEqual([200, 409], sorted(statuses))

    def test_binding_creation_references_model_and_provider_authority(self):
        self.register_model()
        binding = self.register_binding()
        self.assertEqual("qwen-2.5-7b-instruct", binding["model_id"])
        self.assertEqual("lucy-ollama", binding["provider_id"])
        self.assertEqual("capability-manager", binding["provider_ref"]["authority"])
        self.verify_provider.assert_awaited_once()

    def test_unknown_model_binding_is_rejected(self):
        response = self.client.post("/bindings", json=self.binding())
        self.assertEqual(422, response.status_code)
        self.assertEqual("unknown_model", response.json()["detail"]["code"])

    def test_provider_reference_must_match_provider_id(self):
        self.register_model()
        request = self.binding()
        request["provider_ref"]["reference_id"] = "different-provider"
        response = self.client.post("/bindings", json=request)
        self.assertEqual(422, response.status_code)

    def test_provider_authority_rejection_is_preserved(self):
        self.register_model()
        self.verify_provider.side_effect = HTTPException(
            status_code=422, detail={"code": "unknown_provider"}
        )
        response = self.client.post("/bindings", json=self.binding())
        self.assertEqual(422, response.status_code)
        self.assertEqual("unknown_provider", response.json()["detail"]["code"])

    def test_provider_verifier_requires_exact_inventory_revision(self):
        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {
                    "providers": [
                        {
                            "provider_id": "lucy-ollama",
                            "updated_at": "provider-revision-newer",
                        }
                    ]
                }

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, *args, **kwargs):
                return Response()

        reference = main.ProviderReference(
            authority="capability-manager",
            reference_id="lucy-ollama",
            revision=self.provider_revision,
        )
        self.verifier.stop()
        with patch.object(main.httpx, "AsyncClient", return_value=Client()):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main.verify_provider_reference(reference))
        self.assertEqual(409, raised.exception.status_code)
        self.assertEqual(
            "provider_revision_mismatch",
            raised.exception.detail["code"],
        )

    def test_provider_verifier_rejects_malformed_authority_shapes(self):
        malformed = (
            [],
            {},
            {"providers": {}},
            {"providers": ["not-an-object"]},
            {"providers": [{"provider_id": ""}]},
            {"providers": [{"provider_id": "lucy-ollama"}]},
            {"providers": [{"provider_id": "lucy-ollama", "updated_at": 7}]},
        )

        class Response:
            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self) -> None:
                return None

            def json(self):
                return self.payload

        class Client:
            def __init__(self, payload):
                self.payload = payload

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, *args, **kwargs):
                return Response(self.payload)

        reference = main.ProviderReference(
            authority="capability-manager",
            reference_id="lucy-ollama",
            revision=self.provider_revision,
        )
        self.verifier.stop()
        for payload in malformed:
            with self.subTest(payload=payload):
                with patch.object(
                    main.httpx, "AsyncClient", return_value=Client(payload)
                ):
                    with self.assertRaises(HTTPException) as raised:
                        asyncio.run(main.verify_provider_reference(reference))
                self.assertEqual(502, raised.exception.status_code)
                self.assertEqual(
                    "provider_authority_invalid_response",
                    raised.exception.detail["code"],
                )

    def test_provider_verifier_classifies_transport_and_http_failure(self):
        class Client:
            def __init__(self, error):
                self.error = error

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, *args, **kwargs):
                raise self.error

        reference = main.ProviderReference(
            authority="capability-manager",
            reference_id="lucy-ollama",
            revision=self.provider_revision,
        )
        self.verifier.stop()
        request = main.httpx.Request("GET", "http://capability-manager/providers")
        errors = (
            main.httpx.ConnectError("unavailable", request=request),
            main.httpx.HTTPStatusError(
                "authority failure",
                request=request,
                response=main.httpx.Response(503, request=request),
            ),
        )
        for error in errors:
            with self.subTest(error=type(error).__name__):
                with patch.object(
                    main.httpx, "AsyncClient", return_value=Client(error)
                ):
                    with self.assertRaises(HTTPException) as raised:
                        asyncio.run(main.verify_provider_reference(reference))
                self.assertEqual(503, raised.exception.status_code)
                self.assertEqual(
                    "provider_authority_unavailable",
                    raised.exception.detail["code"],
                )

    def test_provider_verifier_accepts_exact_revision_and_rejects_absence(self):
        class Response:
            def __init__(self, providers):
                self.providers = providers

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"providers": self.providers}

        class Client:
            def __init__(self, providers):
                self.providers = providers

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, *args, **kwargs):
                return Response(self.providers)

        reference = main.ProviderReference(
            authority="capability-manager",
            reference_id="lucy-ollama",
            revision=self.provider_revision,
        )
        self.verifier.stop()
        valid = [
            {
                "provider_id": "lucy-ollama",
                "updated_at": self.provider_revision,
            }
        ]
        with patch.object(main.httpx, "AsyncClient", return_value=Client(valid)):
            self.assertIsNone(
                asyncio.run(main.verify_provider_reference(reference))
            )
        with patch.object(main.httpx, "AsyncClient", return_value=Client([])):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main.verify_provider_reference(reference))
        self.assertEqual(422, raised.exception.status_code)
        self.assertEqual("unknown_provider", raised.exception.detail["code"])

    def test_multiple_providers_may_bind_one_model(self):
        self.register_model()
        self.register_binding()
        self.register_binding(
            binding_id="binding-qwen-alice",
            provider_id="alice-vllm",
            alias="qwen2.5:7b-instruct",
        )
        listed = self.client.get(
            "/bindings", params={"model_id": "qwen-2.5-7b-instruct"}
        ).json()
        self.assertEqual(2, listed["count"])

    def test_logical_binding_target_is_unique(self):
        self.register_model()
        first = self.register_binding()
        duplicate = self.binding(binding_id="different-binding-id")
        response = self.client.post("/bindings", json=duplicate)
        self.assertEqual(409, response.status_code)
        self.assertEqual(
            "binding_target_conflict", response.json()["detail"]["code"]
        )
        self.assertEqual(first["binding_id"], response.json()["detail"]["binding_id"])

    def test_same_runtime_target_cannot_name_two_models(self):
        self.register_model()
        self.register_model("different-model")
        self.register_binding()
        response = self.client.post(
            "/bindings",
            json=self.binding(
                binding_id="different-model-binding",
                model_id="different-model",
            ),
        )
        self.assertEqual(409, response.status_code)
        self.assertEqual(
            "binding_target_conflict", response.json()["detail"]["code"]
        )

    def test_same_model_provider_with_different_alias_is_allowed(self):
        self.register_model()
        self.register_binding()
        second = self.client.post(
            "/bindings",
            json=self.binding(
                binding_id="second-alias", alias="qwen2.5:7b-second-alias"
            ),
        )
        self.assertEqual(200, second.status_code, second.text)

    def test_concurrent_identical_binding_registration_is_idempotent(self):
        self.register_model()

        def register() -> tuple[int, bool]:
            response = TestClient(main.app).post(
                "/bindings", json=self.binding()
            )
            return response.status_code, response.json().get("changed", False)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: register(), range(2)))
        self.assertEqual([200, 200], sorted(item[0] for item in results))
        self.assertEqual([False, True], sorted(item[1] for item in results))

    def test_concurrent_conflicting_binding_registration_is_deterministic(self):
        self.register_model()
        requests = [self.binding(), self.binding(alias="different-alias")]

        def register(request: dict) -> int:
            return TestClient(main.app).post(
                "/bindings", json=request
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(register, requests))
        self.assertEqual([200, 409], sorted(statuses))

    def test_concurrent_logical_duplicate_binding_is_deterministic(self):
        self.register_model()
        requests = [
            self.binding(binding_id="logical-binding-one"),
            self.binding(binding_id="logical-binding-two"),
        ]

        def register(request: dict) -> int:
            return TestClient(main.app).post(
                "/bindings", json=request
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(register, requests))
        self.assertEqual([200, 409], sorted(statuses))

    def test_one_provider_may_expose_multiple_models(self):
        self.register_model()
        self.register_model("embedding-small")
        self.register_binding()
        self.register_binding(
            binding_id="binding-embed-lucy",
            model_id="embedding-small",
            alias="bge-small",
        )
        listed = self.client.get(
            "/bindings", params={"provider_id": "lucy-ollama"}
        ).json()
        self.assertEqual(2, listed["count"])

    def test_runtime_alias_does_not_redefine_model_identity(self):
        self.register_model()
        binding = self.register_binding()
        changed = self.client.patch(
            f"/bindings/{binding['binding_id']}",
            json={
                "expected_revision": binding["revision"],
                "runtime_model_ref": "qwen-alias-after-restart",
            },
        ).json()["binding"]
        self.assertEqual(binding["model_id"], changed["model_id"])
        self.assertNotEqual(binding["revision"], changed["revision"])

    def test_binding_revision_changes_on_material_mutation(self):
        self.register_model()
        binding = self.register_binding()
        updated = self.client.patch(
            f"/bindings/{binding['binding_id']}",
            json={"expected_revision": binding["revision"], "enabled": False},
        ).json()["binding"]
        self.assertNotEqual(binding["revision"], updated["revision"])

    def test_unavailable_is_not_unpreferred(self):
        self.register_model()
        binding = self.register_binding()
        updated = self.client.patch(
            f"/bindings/{binding['binding_id']}",
            json={
                "expected_revision": binding["revision"],
                "availability": {"state": "unavailable"},
            },
        ).json()["binding"]
        self.assertEqual("unavailable", updated["availability"]["state"])
        self.assertNotIn("preference", json.dumps(updated).lower())
        self.assertNotIn("rank", json.dumps(updated).lower())

    def test_disabled_is_not_lower_ranked(self):
        self.register_model()
        binding = self.register_binding()
        updated = self.client.patch(
            f"/bindings/{binding['binding_id']}",
            json={"expected_revision": binding["revision"], "enabled": False},
        ).json()["binding"]
        self.assertFalse(updated["enabled"])
        self.assertNotIn("score", json.dumps(updated).lower())
        self.assertNotIn("priority", json.dumps(updated).lower())

    def test_binding_patch_requires_current_revision(self):
        self.register_model()
        before = self.register_binding()
        changed = self.client.patch(
            f"/bindings/{before['binding_id']}",
            json={
                "expected_revision": before["revision"],
                "runtime_model_ref": "new-alias",
            },
        ).json()["binding"]
        stale = self.client.patch(
            f"/bindings/{before['binding_id']}",
            json={
                "expected_revision": before["revision"],
                "enabled": False,
            },
        )
        self.assertEqual(409, stale.status_code)
        self.assertEqual("revision_conflict", stale.json()["detail"]["code"])
        self.assertEqual(
            changed["revision"],
            self.client.get(f"/bindings/{before['binding_id']}").json()[
                "binding"
            ]["revision"],
        )

    def test_simultaneous_binding_patches_cannot_erase_each_other(self):
        self.register_model()
        before = self.register_binding()
        requests = (
            {
                "expected_revision": before["revision"],
                "runtime_model_ref": "concurrent-alias",
            },
            {
                "expected_revision": before["revision"],
                "enabled": False,
            },
        )

        def update(request: dict) -> int:
            return TestClient(main.app).patch(
                f"/bindings/{before['binding_id']}", json=request
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(update, requests))
        self.assertEqual([200, 409], sorted(statuses))

    def test_inventory_filters_do_not_select(self):
        self.register_model()
        self.register_binding()
        response = self.client.get(
            "/bindings",
            params={"enabled": True, "availability": "available"},
        ).json()
        self.assertEqual(1, response["count"])
        self.assertNotIn("selected", response)

    def test_no_selection_ranking_route_or_fallback_surface(self):
        paths = {route.path for route in main.app.routes}
        for forbidden in (
            "/best-model",
            "/select",
            "/recommend",
            "/route",
            "/fallback",
            "/resolve",
        ):
            self.assertNotIn(forbidden, paths)

    def test_model_and_provider_preferences_remain_separate_future_concepts(self):
        model = self.register_model()
        binding = self.register_binding()
        self.assertIn("model_id", model)
        self.assertIn("provider_id", binding)
        self.assertNotIn("preference", model)
        self.assertNotIn("preference", binding)

    def test_provider_endpoint_authority_is_not_duplicated(self):
        self.register_model()
        binding = self.binding()
        binding["base_url"] = "http://forbidden.example"
        response = self.client.post("/bindings", json=binding)
        self.assertEqual(422, response.status_code)
        self.assertNotIn("base_url", main.BindingWrite.model_fields)

    def test_raw_secret_values_are_rejected_and_not_persisted(self):
        request = self.model()
        request["metadata"]["api_key"] = "forbidden-value"
        response = self.client.post("/models", json=request)
        self.assertEqual(422, response.status_code)
        with main.connect() as db:
            persisted = "\n".join(
                row[0]
                for table in ("models", "model_runtime_bindings")
                for row in db.execute(f"SELECT document_json FROM {table}")
            )
        self.assertNotIn("forbidden-value", persisted)

    def test_legitimate_secret_like_metadata_is_allowed(self):
        request = self.model()
        request["metadata"] = {
            "token_count": 8192,
            "token": "<model-vocabulary-token>",
            "tokenizer": "qwen-tokenizer",
            "key_dimensions": 128,
            "secret_name": "openai-production",
            "api_key_required": True,
            "api_key": True,
            "private_key_support": False,
            "credential_type": "oauth",
            "source": {"provider_id": "raw-source-name"},
        }
        response = self.client.post("/models", json=request)
        self.assertEqual(200, response.status_code, response.text)

    def test_nested_raw_credential_values_are_rejected(self):
        keys = (
            "api_key",
            "access_token",
            "refresh_token",
            "client_secret",
            "password",
            "private_key",
            "private_key_pem",
            "secret_value",
            "credential_value",
        )
        for key in keys:
            with self.subTest(key=key):
                request = self.model(f"model-{key}")
                request["metadata"] = {"nested": {key: "raw-credential-material"}}
                response = self.client.post("/models", json=request)
                self.assertEqual(422, response.status_code)

    def test_nested_metadata_cannot_override_canonical_authority(self):
        request = self.model()
        request["metadata"] = {
            "model_id": "not-authoritative",
            "enabled": False,
            "capabilities": ["not-authoritative"],
            "revision": "not-authoritative",
            "provider_id": "not-authoritative",
        }
        record = self.client.post("/models", json=request).json()["model"]
        self.assertEqual(request["model_id"], record["model_id"])
        self.assertTrue(record["enabled"])
        self.assertEqual(
            sorted(self.model()["capabilities"]), record["capabilities"]
        )
        self.assertTrue(record["revision"].startswith("sha256:"))

    def test_persistence_survives_reopen(self):
        before = self.register_model()
        with main.connect() as db:
            row = db.execute(
                "SELECT * FROM models WHERE model_id = ?", (before["model_id"],)
            ).fetchone()
        self.assertEqual(before["revision"], row["revision"])
        self.assertEqual(
            before,
            self.client.get(f"/models/{before['model_id']}").json()["model"],
        )

    def test_migration_is_non_destructive(self):
        with sqlite3.connect(main.DB_PATH) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS donor_evidence(value TEXT NOT NULL)"
            )
            db.execute("DELETE FROM donor_evidence")
            db.execute("INSERT INTO donor_evidence VALUES ('preserve-me')")
        main.migrate()
        with sqlite3.connect(main.DB_PATH) as db:
            value = db.execute("SELECT value FROM donor_evidence").fetchone()[0]
        self.assertEqual("preserve-me", value)

    def test_restart_migration_preserves_inventory(self):
        before = self.register_model()
        binding = self.register_binding()
        main.migrate()
        record = main.get_model(before["model_id"])["model"]
        self.assertEqual(before["revision"], record["revision"])
        self.assertEqual(
            binding["revision"],
            main.get_binding(binding["binding_id"])["binding"]["revision"],
        )
        with main.connect() as db:
            indexes = {
                row["name"]
                for row in db.execute(
                    "PRAGMA index_list(model_runtime_bindings)"
                )
            }
        self.assertIn("uq_model_binding_runtime_target", indexes)

    def test_pre_correction_populated_v1_schema_migrates_non_destructively(self):
        with tempfile.TemporaryDirectory() as directory:
            old_path = Path(directory) / "old-v1.db"
            model = self.model()
            binding = self.binding()
            with sqlite3.connect(old_path) as db:
                db.executescript(
                    """
                    CREATE TABLE model_registry_schema (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    );
                    CREATE TABLE models (
                        model_id TEXT PRIMARY KEY,
                        document_json TEXT NOT NULL,
                        revision TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE model_runtime_bindings (
                        binding_id TEXT PRIMARY KEY,
                        model_id TEXT NOT NULL,
                        provider_id TEXT NOT NULL,
                        document_json TEXT NOT NULL,
                        revision TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE model_registry_events (
                        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        entity_type TEXT NOT NULL,
                        entity_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        revision TEXT NOT NULL,
                        occurred_at TEXT NOT NULL
                    );
                    CREATE TABLE donor_evidence(value TEXT NOT NULL);
                    """
                )
                db.execute(
                    "INSERT INTO model_registry_schema VALUES (1, ?)",
                    ("2026-07-25T00:00:00+00:00",),
                )
                db.execute(
                    "INSERT INTO models VALUES (?, ?, ?, ?, ?)",
                    (
                        model["model_id"],
                        main.canonical_json(model),
                        "old-model-revision",
                        "2026-07-25T00:00:00+00:00",
                        "2026-07-25T00:00:00+00:00",
                    ),
                )
                db.execute(
                    "INSERT INTO model_runtime_bindings VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        binding["binding_id"],
                        binding["model_id"],
                        binding["provider_id"],
                        main.canonical_json(binding),
                        "old-binding-revision",
                        "2026-07-25T00:00:00+00:00",
                        "2026-07-25T00:00:00+00:00",
                    ),
                )
                db.execute("INSERT INTO donor_evidence VALUES ('preserve-me')")
            with patch.object(main, "DB_PATH", old_path):
                main.migrate()
                main.migrate()
                with main.connect() as db:
                    migrated = db.execute(
                        """
                        SELECT runtime_type, runtime_model_ref
                        FROM model_runtime_bindings
                        """
                    ).fetchone()
                    evidence = db.execute(
                        "SELECT value FROM donor_evidence"
                    ).fetchone()[0]
                    indexes = {
                        row["name"]
                        for row in db.execute(
                            "PRAGMA index_list(model_runtime_bindings)"
                        )
                    }
            self.assertEqual("ollama", migrated["runtime_type"])
            self.assertEqual(binding["runtime_model_ref"], migrated["runtime_model_ref"])
            self.assertEqual("preserve-me", evidence)
            self.assertIn("uq_model_binding_runtime_target", indexes)

    def test_service_has_no_invocation_client_or_execution_state(self):
        source = (SERVICE_ROOT / "app" / "main.py").read_text()
        self.assertNotIn('client.post(', source)
        with main.connect() as db:
            tables = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        self.assertNotIn("executions", tables)
        self.assertNotIn("rankings", tables)


if __name__ == "__main__":
    unittest.main()
