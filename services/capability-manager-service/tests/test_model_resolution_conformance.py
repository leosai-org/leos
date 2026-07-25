from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SERVICE_ROOT.parents[1]
PACKAGE_SRC = REPOSITORY_ROOT / "packages/leos-contracts" / "src"
TEST_DATA = tempfile.TemporaryDirectory()
os.environ["CAPABILITY_MANAGER_DATA_DIR"] = TEST_DATA.name
os.environ["LEOS_CONTRACT_ROOT"] = str(REPOSITORY_ROOT / "contracts")
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(PACKAGE_SRC))

from app import main


class ModelResolutionConformance(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()

    def setUp(self):
        main.migrate()
        with main.connect() as db:
            for table in (
                "canonical_resolutions", "provider_capabilities",
                "providers", "capabilities", "events",
            ):
                db.execute(f"DELETE FROM {table}")
        main.register_capability(
            main.Capability(capability_id="text.reason", name="Reason")
        )
        for provider_id in ("p1", "p2", "p3"):
            main.register_provider(
                main.Provider(
                    provider_id=provider_id,
                    name=provider_id,
                    provider_type="service",
                    base_url=f"http://{provider_id}:8000",
                )
            )
            main.register_binding(
                main.Binding(
                    provider_id=provider_id,
                    capability_id="text.reason",
                    enabled=True,
                    approval_policy="allowed",
                )
            )

    def request(self):
        return {
            "contract_version": main.REQUEST_CONTRACT,
            "capability_id": "text.reason",
            "requester": {"type": "employee", "id": "emp-1"},
            "constraints": {},
            "policy": {},
            "correlation": {
                "contract_version": main.CORRELATION_CONTRACT,
                "job_id": "job-1",
                "execution_id": "exec-1",
            },
            "ranking_context": {"employee_id": "emp-1", "job_id": "job-1"},
            "target_requirements": {"model_required": True},
            "requested_at": "2026-07-25T12:00:00Z",
        }

    @staticmethod
    def policy(dimension, values=None, scope="global"):
        if values is None:
            return {
                "contract_version": "leos.effective-ranking-result.v1",
                "dimension": dimension,
                "status": "UNDEFINED",
                "ordered_ids": [],
                "resolved_at": "2026-07-25T12:00:00Z",
            }
        result = {
            "contract_version": "leos.effective-ranking-result.v1",
            "dimension": dimension,
            "status": "DEFINED",
            "ordered_ids": values,
            "source_scope": scope,
            "ranking_ref": {
                "authority": "ranking-policy-authority",
                "reference_id": f"{dimension}-ranking",
                "revision": "rev-1",
            },
            "resolved_at": "2026-07-25T12:00:00Z",
        }
        if scope != "global":
            result["source_scope_id"] = "scope-1"
        return result

    @staticmethod
    def model(model_id):
        return {
            "model_id": model_id,
            "enabled": True,
            "capabilities": ["text.reason"],
            "revision": f"{model_id}-rev",
        }

    @staticmethod
    def binding(provider_id, model_id, suffix="", available=True):
        binding_id = f"b-{provider_id}-{model_id}{suffix}"
        return {
            "binding_id": binding_id,
            "provider_id": provider_id,
            "model_id": model_id,
            "enabled": True,
            "revision": f"{binding_id}-rev",
            "provider_ref": {
                "authority": "capability-manager",
                "reference_id": provider_id,
                "revision": None,
            },
            "runtime_type": "synthetic",
            "runtime_model_ref": f"native-{model_id}",
            "availability": {
                "state": "available" if available else "unavailable"
            },
        }

    def resolve(
        self,
        provider_order,
        model_order,
        bindings,
        models=("m1", "m2"),
        *,
        preserve_provider_revision=False,
    ):
        policies = {
            "provider": self.policy("provider", provider_order),
            "model": self.policy("model", model_order),
        }

        async def ranking(dimension, request):
            return policies[dimension]

        async def authority(method, url, json_body=None):
            if "/models" in url:
                return {"models": [self.model(item) for item in models]}
            rows = main.candidate_rows("text.reason")
            prepared = []
            for binding in bindings:
                value = dict(binding)
                value["provider_ref"] = dict(value["provider_ref"])
                if not preserve_provider_revision:
                    value["provider_ref"]["revision"] = rows[
                        value["provider_id"]
                    ]["updated_at"]
                prepared.append(value)
            return {"bindings": prepared}

        with patch.object(main, "effective_ranking", new=ranking), patch.object(
            main, "authority_json", new=authority
        ):
            return main.resolve(self.request())

    def test_aligned_provider_and_model_rankings_select_unique_best(self):
        result = self.resolve(
            ["p1", "p2"], ["m1", "m2"],
            [self.binding("p1", "m1"), self.binding("p2", "m2")],
        )
        self.assertEqual("RESOLVED", result["status"])
        self.assertEqual(("p1", "m1"), (
            result["selected_target"]["provider_id"],
            result["selected_target"]["model_id"],
        ))
        self.assertIn("runtime_binding_ref", result["selected_target"])

    def test_crossed_rankings_require_governed_order(self):
        result = self.resolve(
            ["p1", "p2"], ["m1", "m2"],
            [self.binding("p1", "m2"), self.binding("p2", "m1")],
        )
        self.assertEqual("GOVERNED_ORDER_REQUIRED", result["status"])
        self.assertNotIn("selected_target", result)

    def test_same_provider_uses_model_order(self):
        result = self.resolve(
            ["p1", "p2"], ["m1", "m2"],
            [self.binding("p1", "m1"), self.binding("p1", "m2")],
        )
        self.assertEqual("m1", result["selected_target"]["model_id"])

    def test_same_model_uses_provider_order(self):
        result = self.resolve(
            ["p1", "p2"], ["m1", "m2"],
            [self.binding("p1", "m1"), self.binding("p2", "m1")],
        )
        self.assertEqual("p1", result["selected_target"]["provider_id"])

    def test_one_dimension_leaves_tied_other_dimension_unordered(self):
        result = self.resolve(
            ["p1", "p2"], None,
            [self.binding("p1", "m1"), self.binding("p1", "m2")],
        )
        self.assertEqual("GOVERNED_ORDER_REQUIRED", result["status"])

    def test_provider_only_ranking_orders_different_providers_same_model(self):
        result = self.resolve(
            ["p1", "p2"], None,
            [self.binding("p1", "m1"), self.binding("p2", "m1")],
        )
        self.assertEqual("RESOLVED", result["status"])
        self.assertEqual("p1", result["selected_target"]["provider_id"])

    def test_model_only_ranking_orders_different_models_same_provider(self):
        result = self.resolve(
            None, ["m1", "m2"],
            [self.binding("p1", "m1"), self.binding("p1", "m2")],
        )
        self.assertEqual("RESOLVED", result["status"])
        self.assertEqual("m1", result["selected_target"]["model_id"])

    def test_model_only_ranking_cannot_order_providers_for_same_model(self):
        result = self.resolve(
            None, ["m1", "m2"],
            [self.binding("p1", "m1"), self.binding("p2", "m1")],
        )
        self.assertEqual("GOVERNED_ORDER_REQUIRED", result["status"])

    def test_no_ranking_multiple_candidates_never_selects(self):
        result = self.resolve(
            None, None,
            [self.binding("p1", "m1"), self.binding("p2", "m2")],
        )
        self.assertEqual("GOVERNED_ORDER_REQUIRED", result["status"])

    def test_no_ranking_zero_and_one_candidate_outcomes(self):
        none = self.resolve(None, None, [])
        self.assertEqual("NO_ELIGIBLE_PROVIDER", none["status"])
        one = self.resolve(None, None, [self.binding("p2", "m2")])
        self.assertEqual("RESOLVED", one["status"])
        self.assertEqual(("p2", "m2"), (
            one["selected_target"]["provider_id"],
            one["selected_target"]["model_id"],
        ))

    def test_exact_lists_exclude_unlisted_provider_and_model(self):
        result = self.resolve(
            ["p1"], ["m1"],
            [
                self.binding("p1", "m1"),
                self.binding("p3", "m1"),
                self.binding("p1", "m2"),
            ],
        )
        self.assertEqual("RESOLVED", result["status"])
        evaluated = result["candidate_evaluations"]
        self.assertEqual([("p1", "m1")], [
            (item["provider_id"], item["model_id"]) for item in evaluated
        ])

    def test_unavailable_binding_is_removed_without_reordering(self):
        result = self.resolve(
            ["p1", "p2"], ["m1"],
            [
                self.binding("p1", "m1", available=False),
                self.binding("p2", "m1"),
            ],
        )
        self.assertEqual("RESOLVED", result["status"])
        self.assertEqual("p2", result["selected_target"]["provider_id"])

    def test_unique_best_missing_approval_blocks_lower_candidate(self):
        with main.connect() as db:
            db.execute(
                """
                UPDATE provider_capabilities
                SET approval_policy='approval_required'
                WHERE provider_id='p1' AND capability_id='text.reason'
                """
            )
        result = self.resolve(
            ["p1", "p2"], ["m1", "m2"],
            [self.binding("p1", "m1"), self.binding("p2", "m2")],
        )
        self.assertEqual("APPROVAL_PENDING", result["status"])
        self.assertNotIn("selected_target", result)
        self.assertIn("p1:m1:approval", result["approval_requirement_ref"]["reference_id"])

    def test_approval_is_not_tie_breaker_for_incomparable_best(self):
        with main.connect() as db:
            db.execute(
                """
                UPDATE provider_capabilities
                SET approval_policy='approval_required'
                WHERE provider_id='p1' AND capability_id='text.reason'
                """
            )
        result = self.resolve(
            ["p1", "p2"], ["m1", "m2"],
            [self.binding("p1", "m2"), self.binding("p2", "m1")],
        )
        self.assertEqual("GOVERNED_ORDER_REQUIRED", result["status"])
        self.assertNotIn("approval_requirement_ref", result)

    def test_stale_binding_provider_revision_is_ineligible(self):
        stale = self.binding("p1", "m1")
        stale["provider_ref"]["revision"] = "stale-provider-revision"
        result = self.resolve(
            ["p1"], ["m1"], [stale], preserve_provider_revision=True
        )
        self.assertEqual("NO_ELIGIBLE_PROVIDER", result["status"])
        self.assertEqual(
            ["binding_provider_revision_stale"],
            result["candidate_evaluations"][0]["reasons"],
        )

    def test_selected_target_preserves_exact_inventory_revisions(self):
        result = self.resolve(
            ["p1"], ["m1"], [self.binding("p1", "m1")]
        )
        target = result["selected_target"]
        self.assertEqual("m1-rev", target["model_ref"]["revision"])
        self.assertEqual(
            "b-p1-m1-rev", target["runtime_binding_ref"]["revision"]
        )
        self.assertEqual(
            main.candidate_rows("text.reason")["p1"]["updated_at"],
            target["target_ref"]["revision"],
        )


if __name__ == "__main__":
    unittest.main()
