from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "services/ranking-policy-service/app/main.py"


def load(db: Path):
    os.environ["RANKING_POLICY_DB"] = str(db)
    spec = importlib.util.spec_from_file_location("ranking_policy_test_app", MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RankingPolicyConformance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.module = load(Path(self.temp.name) / "rankings.db")
        self.client = TestClient(self.module.app)

    def tearDown(self):
        self.temp.cleanup()

    def create(self, dimension, scope_type, ordered_ids, scope_id=None):
        body = {
            "dimension": dimension,
            "scope_type": scope_type,
            "ordered_ids": ordered_ids,
        }
        if scope_id:
            body["scope_id"] = scope_id
        response = self.client.post("/rankings", json=body)
        self.assertEqual(200, response.status_code, response.text)
        return response.json()["ranking"]

    def effective(self, dimension, **context):
        response = self.client.post(
            "/effective",
            json={
                "contract_version": "leos.effective-ranking-request.v1",
                "dimension": dimension,
                "requested_at": "2026-07-25T12:00:00Z",
                **context,
            },
        )
        self.assertEqual(200, response.status_code, response.text)
        return response.json()

    def test_global_then_capability_employee_job_precedence(self):
        self.create("provider", "global", ["global"])
        self.create("provider", "capability", ["cap"], "text.reason")
        self.create("provider", "employee", ["employee"], "emp-1")
        self.create("provider", "job", ["job"], "job-1")
        self.assertEqual(["global"], self.effective("provider")["ordered_ids"])
        self.assertEqual(
            ["cap"],
            self.effective("provider", capability_id="text.reason")["ordered_ids"],
        )
        self.assertEqual(
            ["employee"],
            self.effective(
                "provider", capability_id="text.reason", employee_id="emp-1"
            )["ordered_ids"],
        )
        result = self.effective(
            "provider",
            capability_id="text.reason",
            employee_id="emp-1",
            job_id="job-1",
        )
        self.assertEqual(["job"], result["ordered_ids"])
        self.assertEqual("job", result["source_scope"])

    def test_every_scope_transition_is_independent_for_both_dimensions(self):
        for dimension in ("provider", "model"):
            suffix = dimension[0]
            self.create(dimension, "global", [f"{suffix}-global"])
            self.assertEqual(
                ("global", [f"{suffix}-global"]),
                (
                    self.effective(dimension)["source_scope"],
                    self.effective(dimension)["ordered_ids"],
                ),
            )
            self.create(
                dimension, "capability", [f"{suffix}-cap"], "text.reason"
            )
            result = self.effective(dimension, capability_id="text.reason")
            self.assertEqual(("capability", [f"{suffix}-cap"]), (
                result["source_scope"], result["ordered_ids"]
            ))
            self.create(
                dimension, "employee", [f"{suffix}-employee"], "emp-1"
            )
            result = self.effective(
                dimension, capability_id="text.reason", employee_id="emp-1"
            )
            self.assertEqual(("employee", [f"{suffix}-employee"]), (
                result["source_scope"], result["ordered_ids"]
            ))
            self.create(dimension, "job", [f"{suffix}-job"], "job-1")
            result = self.effective(
                dimension,
                capability_id="text.reason",
                employee_id="emp-1",
                job_id="job-1",
            )
            self.assertEqual(("job", [f"{suffix}-job"]), (
                result["source_scope"], result["ordered_ids"]
            ))

    def test_dimensions_inherit_independently(self):
        self.create("provider", "job", ["p-job"], "job-1")
        self.create("model", "employee", ["m-employee"], "emp-1")
        context = {"job_id": "job-1", "employee_id": "emp-1"}
        self.assertEqual(["p-job"], self.effective("provider", **context)["ordered_ids"])
        self.assertEqual(
            ["m-employee"], self.effective("model", **context)["ordered_ids"]
        )

    def test_replacement_exact_order_and_no_merge(self):
        self.create("provider", "global", ["a", "b", "c"])
        self.create("provider", "employee", ["c", "a"], "emp-1")
        result = self.effective("provider", employee_id="emp-1")
        self.assertEqual(["c", "a"], result["ordered_ids"])

    def test_model_replacement_and_job_replacement_never_merge(self):
        self.create("model", "global", ["m1", "m2", "m3"])
        self.create("model", "employee", ["m3", "m1"], "emp-1")
        employee = self.effective("model", employee_id="emp-1")
        self.assertEqual(["m3", "m1"], employee["ordered_ids"])
        self.create("model", "job", ["m2"], "job-1")
        job = self.effective("model", employee_id="emp-1", job_id="job-1")
        self.assertEqual(["m2"], job["ordered_ids"])

    def test_inactive_specific_returns_to_inheritance(self):
        self.create("model", "global", ["global"])
        specific = self.create("model", "job", ["job"], "job-1")
        response = self.client.patch(
            f"/rankings/{specific['ranking_id']}",
            json={"expected_revision": specific["revision"], "active": False},
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            ["global"], self.effective("model", job_id="job-1")["ordered_ids"]
        )

    def test_no_ranking_is_explicitly_undefined(self):
        result = self.effective("provider", job_id="missing")
        self.assertEqual("UNDEFINED", result["status"])
        self.assertEqual([], result["ordered_ids"])
        self.assertNotIn("ranking_ref", result)

    def test_empty_and_duplicate_lists_are_rejected(self):
        for ordered in ([], ["a", "a"]):
            response = self.client.post(
                "/rankings",
                json={
                    "dimension": "provider",
                    "scope_type": "global",
                    "ordered_ids": ordered,
                },
            )
            self.assertEqual(422, response.status_code)

    def test_scope_identity_rules(self):
        self.assertEqual(
            422,
            self.client.post(
                "/rankings",
                json={
                    "dimension": "provider",
                    "scope_type": "global",
                    "scope_id": "wrong",
                    "ordered_ids": ["p"],
                },
            ).status_code,
        )
        self.assertEqual(
            422,
            self.client.post(
                "/rankings",
                json={
                    "dimension": "provider",
                    "scope_type": "employee",
                    "ordered_ids": ["p"],
                },
            ).status_code,
        )

    def test_identical_replay_is_idempotent(self):
        first = self.create("provider", "global", ["p1", "p2"])
        replay = self.client.post(
            "/rankings",
            json={
                "dimension": "provider",
                "scope_type": "global",
                "ordered_ids": ["p1", "p2"],
            },
        ).json()
        self.assertFalse(replay["changed"])
        self.assertEqual(first["revision"], replay["ranking"]["revision"])
        self.assertEqual(1, self.client.get("/events").json()["events"].__len__())

    def test_conflicting_create_and_stale_patch(self):
        first = self.create("provider", "global", ["p1"])
        conflict = self.client.post(
            "/rankings",
            json={
                "dimension": "provider",
                "scope_type": "global",
                "ordered_ids": ["p2"],
            },
        )
        self.assertEqual(409, conflict.status_code)
        stale = self.client.patch(
            f"/rankings/{first['ranking_id']}",
            json={"expected_revision": "stale", "ordered_ids": ["p2"]},
        )
        self.assertEqual(409, stale.status_code)

    def test_deterministic_revision_and_exact_order(self):
        first = self.create("model", "global", ["m2", "m1"])
        self.assertEqual(["m2", "m1"], first["ordered_ids"])
        self.assertTrue(first["revision"].startswith("sha256:"))

    def test_reversing_authored_order_changes_revision(self):
        first = self.create("provider", "global", ["p1", "p2"])
        changed = self.client.patch(
            f"/rankings/{first['ranking_id']}",
            json={
                "expected_revision": first["revision"],
                "ordered_ids": ["p2", "p1"],
            },
        ).json()["ranking"]
        self.assertNotEqual(first["revision"], changed["revision"])
        self.assertEqual(["p2", "p1"], changed["ordered_ids"])

    def test_dictionary_key_order_does_not_change_revision(self):
        left = {
            "dimension": "provider",
            "scope_type": "global",
            "ordered_ids": ["p1", "p2"],
            "active": True,
        }
        right = {
            "active": True,
            "ordered_ids": ["p1", "p2"],
            "scope_type": "global",
            "dimension": "provider",
        }
        self.assertEqual(
            self.module.revision(left),
            self.module.revision(right),
        )

    def test_noop_patch_preserves_revision_timestamp_and_event_count(self):
        first = self.create("provider", "global", ["p1", "p2"])
        response = self.client.patch(
            f"/rankings/{first['ranking_id']}",
            json={
                "expected_revision": first["revision"],
                "ordered_ids": ["p1", "p2"],
            },
        ).json()
        self.assertFalse(response["changed"])
        self.assertEqual(first["revision"], response["ranking"]["revision"])
        self.assertEqual(first["updated_at"], response["ranking"]["updated_at"])
        self.assertEqual(1, len(self.client.get("/events").json()["events"]))

    def test_simultaneous_patch_has_one_winner_and_no_lost_update(self):
        first = self.create("provider", "global", ["p1"])
        barrier = threading.Barrier(2)
        statuses = []

        def update(value):
            client = TestClient(self.module.app)
            barrier.wait()
            response = client.patch(
                f"/rankings/{first['ranking_id']}",
                json={
                    "expected_revision": first["revision"],
                    "ordered_ids": [value],
                },
            )
            statuses.append(response.status_code)

        threads = [
            threading.Thread(target=update, args=(value,))
            for value in ("p2", "p3")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual([200, 409], sorted(statuses))
        final = self.client.get(
            f"/rankings/{first['ranking_id']}"
        ).json()["ranking"]
        self.assertIn(final["ordered_ids"], (["p2"], ["p3"]))
        self.assertEqual(2, len(self.client.get("/events").json()["events"]))

    def test_concurrent_identical_creation_has_no_raw_sqlite_error(self):
        barrier = threading.Barrier(2)
        statuses = []

        def create():
            client = TestClient(self.module.app)
            barrier.wait()
            response = client.post(
                "/rankings",
                json={
                    "dimension": "provider",
                    "scope_type": "global",
                    "ordered_ids": ["p1"],
                },
            )
            statuses.append(response.status_code)

        threads = [threading.Thread(target=create) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual([200, 200], sorted(statuses))

    def test_concurrent_conflicting_creation_is_deterministic(self):
        barrier = threading.Barrier(2)
        statuses = []

        def create(value):
            client = TestClient(self.module.app)
            barrier.wait()
            statuses.append(
                client.post(
                    "/rankings",
                    json={
                        "dimension": "model",
                        "scope_type": "global",
                        "ordered_ids": [value],
                    },
                ).status_code
            )

        threads = [threading.Thread(target=create, args=(value,)) for value in ("a", "b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual([200, 409], sorted(statuses))

    def test_authority_surface_contains_no_execute_or_resolve(self):
        paths = set(self.module.app.openapi()["paths"])
        self.assertNotIn("/execute", paths)
        self.assertNotIn("/resolve", paths)


if __name__ == "__main__":
    unittest.main()
