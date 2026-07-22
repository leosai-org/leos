from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.resource_engine import (
    ResourceEngine,
    ResourcePolicyError,
)


class ResourceEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "resource.db"
        self.engine = ResourceEngine(self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def profile(self, employee_id: str = "writer-employee", **overrides):
        value = {
            "employee_id": employee_id,
            "priority_class": "normal",
            "resource_profile": {
                "cpu_cores_min": 2,
                "memory_mb_min": 2048,
                "gpu_required": False,
            },
            "execution_policy": {
                "max_concurrent_jobs": 2,
                "preemptible": True,
                "allow_preemption": False,
                "queue_when_unavailable": True,
                "reservation_ttl_seconds": 3600,
            },
            "provider_preferences": [
                {
                    "provider": "local",
                    "model": "qwen2.5:7b-instruct",
                    "priority": 1,
                }
            ],
        }
        value.update(overrides)
        return value

    def node(self, node_id: str = "lucy-gpu1", **overrides):
        value = {
            "node_id": node_id,
            "status": "online",
            "labels": {"host": "lucy", "role": "general-ai"},
            "cpu_cores_total": 16,
            "memory_mb_total": 65536,
            "max_concurrent_jobs": 8,
            "gpus": [
                {
                    "uuid": "GPU-TEST-1",
                    "name": "RTX Test",
                    "vram_mb_total": 12288,
                }
            ],
        }
        value.update(overrides)
        return value

    def test_profile_versioning(self):
        first = self.engine.upsert_profile(self.profile())
        second = self.engine.upsert_profile(
            self.profile(priority_class="elevated")
        )
        self.assertEqual(first["version"], 1)
        self.assertEqual(second["version"], 2)
        self.assertEqual(second["priority_weight"], 70)

    def test_admission_and_reservation(self):
        self.engine.upsert_profile(self.profile())
        self.engine.register_node(self.node())
        decision = self.engine.evaluate("writer-employee", "job-1")
        self.assertEqual(decision["decision"], "admitted")
        result = self.engine.reserve("writer-employee", "job-1")
        self.assertTrue(result["reserved"])
        self.assertEqual(result["reservation"]["status"], "active")

    def test_capacity_queue(self):
        self.engine.upsert_profile(
            self.profile(
                execution_policy={
                    "max_concurrent_jobs": 4,
                    "queue_when_unavailable": True,
                    "reservation_ttl_seconds": 3600,
                }
            )
        )
        self.engine.register_node(
            self.node(
                cpu_cores_total=2,
                memory_mb_total=2048,
                max_concurrent_jobs=1,
                gpus=[],
            )
        )
        self.assertTrue(
            self.engine.reserve("writer-employee", "job-1")["reserved"]
        )
        self.assertEqual(
            self.engine.evaluate("writer-employee", "job-2")["decision"],
            "queued",
        )

    def test_release_returns_capacity(self):
        self.engine.upsert_profile(self.profile())
        self.engine.register_node(self.node())
        first = self.engine.reserve("writer-employee", "job-1")
        reservation_id = first["reservation"]["reservation_id"]
        released = self.engine.release(reservation_id, "complete")
        self.assertEqual(released["status"], "released")
        self.assertTrue(
            self.engine.reserve("writer-employee", "job-2")["reserved"]
        )

    def test_gpu_preference(self):
        self.engine.upsert_profile(
            self.profile(
                resource_profile={
                    "cpu_cores_min": 1,
                    "memory_mb_min": 1024,
                    "gpu_required": True,
                    "vram_mb_min": 8000,
                    "gpu_uuid_preferences": ["GPU-TEST-1"],
                }
            )
        )
        self.engine.register_node(self.node())
        decision = self.engine.evaluate("writer-employee", "gpu-job")
        self.assertEqual(decision["selected_gpu_uuid"], "GPU-TEST-1")

    def test_gpu_rejects_cpu_node(self):
        self.engine.upsert_profile(
            self.profile(
                resource_profile={
                    "cpu_cores_min": 1,
                    "memory_mb_min": 1024,
                    "gpu_required": True,
                    "vram_mb_min": 1024,
                },
                execution_policy={
                    "max_concurrent_jobs": 1,
                    "queue_when_unavailable": False,
                    "reservation_ttl_seconds": 3600,
                },
            )
        )
        self.engine.register_node(self.node(gpus=[]))
        self.assertEqual(
            self.engine.evaluate("writer-employee", "gpu-job")["decision"],
            "rejected",
        )

    def test_affinity_prefers_matching_node(self):
        self.engine.upsert_profile(
            self.profile(
                node_affinity={
                    "required_labels": {"host": "lucy"},
                    "preferred_labels": {"gpu_role": "production"},
                }
            )
        )
        self.engine.register_node(
            self.node(
                node_id="lucy-general",
                labels={"host": "lucy", "gpu_role": "general"},
            )
        )
        self.engine.register_node(
            self.node(
                node_id="lucy-production",
                labels={"host": "lucy", "gpu_role": "production"},
            )
        )
        decision = self.engine.evaluate("writer-employee", "job-1")
        self.assertEqual(decision["selected_node_id"], "lucy-production")

    def test_concurrency_limit(self):
        self.engine.upsert_profile(
            self.profile(
                execution_policy={
                    "max_concurrent_jobs": 1,
                    "queue_when_unavailable": True,
                    "reservation_ttl_seconds": 3600,
                }
            )
        )
        self.engine.register_node(self.node())
        self.engine.reserve("writer-employee", "job-1")
        decision = self.engine.evaluate("writer-employee", "job-2")
        self.assertEqual(
            decision["reason"],
            "employee-concurrency-limit-reached",
        )

    def test_preemption(self):
        self.engine.register_node(
            self.node(
                cpu_cores_total=4,
                memory_mb_total=4096,
                max_concurrent_jobs=1,
                gpus=[],
            )
        )
        self.engine.upsert_profile(
            self.profile(
                employee_id="background-employee",
                priority_class="background",
                resource_profile={
                    "cpu_cores_min": 4,
                    "memory_mb_min": 4096,
                },
                execution_policy={
                    "max_concurrent_jobs": 1,
                    "preemptible": True,
                    "queue_when_unavailable": True,
                    "reservation_ttl_seconds": 3600,
                },
            )
        )
        self.engine.upsert_profile(
            self.profile(
                employee_id="critical-employee",
                priority_class="business-critical",
                resource_profile={
                    "cpu_cores_min": 4,
                    "memory_mb_min": 4096,
                },
                execution_policy={
                    "max_concurrent_jobs": 1,
                    "preemptible": False,
                    "allow_preemption": True,
                    "queue_when_unavailable": True,
                    "reservation_ttl_seconds": 3600,
                },
            )
        )
        background = self.engine.reserve(
            "background-employee",
            "background-job",
        )
        decision = self.engine.evaluate(
            "critical-employee",
            "critical-job",
        )
        self.assertEqual(decision["decision"], "preemption-required")
        committed = self.engine.reserve(
            "critical-employee",
            "critical-job",
            commit_preemption=True,
        )
        self.assertTrue(committed["reserved"])
        old = self.engine.get_reservation(
            background["reservation"]["reservation_id"]
        )
        self.assertEqual(old["status"], "preempted")

    def test_fallback_profile(self):
        self.engine.upsert_profile(
            self.profile(
                resource_profile={
                    "cpu_cores_min": 32,
                    "memory_mb_min": 131072,
                    "gpu_required": True,
                    "vram_mb_min": 48000,
                },
                fallback_profiles=[
                    {
                        "name": "cpu-fallback",
                        "resource_profile": {
                            "cpu_cores_min": 2,
                            "memory_mb_min": 2048,
                            "gpu_required": False,
                        },
                        "provider_preferences": [
                            {
                                "provider": "local",
                                "model": "phi-4-mini",
                                "priority": 1,
                            }
                        ],
                    }
                ],
            )
        )
        self.engine.register_node(self.node(gpus=[]))
        decision = self.engine.evaluate("writer-employee", "fallback-job")
        self.assertEqual(decision["selected_profile"], "cpu-fallback")

    def test_execution_window(self):
        self.engine.upsert_profile(
            self.profile(
                allowed_execution_windows=[
                    {
                        "weekdays": [0],
                        "start": "08:00",
                        "end": "09:00",
                        "timezone": "UTC",
                    }
                ]
            )
        )
        self.engine.register_node(self.node())
        requested = datetime(
            2026,
            7,
            19,
            12,
            0,
            tzinfo=timezone.utc,
        ).isoformat()
        decision = self.engine.evaluate(
            "writer-employee",
            "window-job",
            requested,
        )
        self.assertEqual(
            decision["reason"],
            "outside-allowed-execution-window",
        )

    def test_persistence(self):
        self.engine.upsert_profile(self.profile())
        self.engine.register_node(self.node())
        reloaded = ResourceEngine(self.database)
        self.assertEqual(len(reloaded.list_profiles()), 1)
        self.assertEqual(len(reloaded.list_nodes()), 1)

    def test_invalid_priority(self):
        with self.assertRaises(ResourcePolicyError):
            self.engine.upsert_profile(
                self.profile(priority_class="impossible")
            )


if __name__ == "__main__":
    unittest.main()
