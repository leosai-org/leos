from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.resource_engine import (
    ResourceEngine,
    ResourceNotFoundError,
)


class RuntimeReservationLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(
            prefix="leos-phase521-resource-"
        )
        self.engine = ResourceEngine(
            Path(self.temp.name) / "resource-policy.db"
        )
        self.engine.upsert_profile(
            {
                "employee_id": "employee-1",
                "priority_class": "normal",
                "resource_profile": {
                    "cpu_cores_min": 1,
                    "memory_mb_min": 512,
                },
                "execution_policy": {
                    "max_concurrent_jobs": 1,
                    "queue_when_unavailable": True,
                    "reservation_ttl_seconds": 30,
                },
            }
        )
        self.engine.register_node(
            {
                "node_id": "worker-1",
                "status": "online",
                "cpu_cores_total": 8,
                "memory_mb_total": 16384,
                "max_concurrent_jobs": 4,
                "gpus": [
                    {
                        "uuid": "GPU-test-1",
                        "name": "Test GPU",
                        "vram_mb_total": 12288,
                    }
                ],
            }
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_active_reservation_can_be_recovered_by_job(self) -> None:
        created = self.engine.reserve(
            "employee-1",
            "job-1",
        )
        reservation = created["reservation"]
        recovered = self.engine.active_reservation_for_job(
            "job-1"
        )
        self.assertEqual(
            recovered["reservation_id"],
            reservation["reservation_id"],
        )
        self.assertEqual(recovered["status"], "active")

    def test_employee_concurrency_is_enforced_until_release(self) -> None:
        first = self.engine.reserve(
            "employee-1",
            "job-1",
        )
        second = self.engine.reserve(
            "employee-1",
            "job-2",
        )
        self.assertTrue(first["reserved"])
        self.assertFalse(second["reserved"])
        self.assertEqual(
            second["decision"]["decision"],
            "queued",
        )
        self.assertEqual(
            second["decision"]["reason"],
            "employee-concurrency-limit-reached",
        )

        self.engine.release(
            first["reservation"]["reservation_id"],
            "test-release",
        )
        third = self.engine.reserve(
            "employee-1",
            "job-2",
        )
        self.assertTrue(third["reserved"])

    def test_expiration_is_durable_and_visible(self) -> None:
        created = self.engine.reserve(
            "employee-1",
            "job-expiring",
        )
        reservation_id = created["reservation"][
            "reservation_id"
        ]
        expired_at = (
            datetime.now(timezone.utc)
            - timedelta(seconds=1)
        ).isoformat()

        with sqlite3.connect(self.engine.database) as connection:
            connection.execute(
                """
                UPDATE reservations
                SET expires_at=?
                WHERE reservation_id=?
                """,
                (expired_at, reservation_id),
            )

        result = self.engine.expire_reservations()
        self.assertEqual(result["expired_count"], 1)
        reservation = self.engine.get_reservation(
            reservation_id
        )
        self.assertEqual(reservation["status"], "expired")
        self.assertEqual(
            reservation["release_reason"],
            "reservation-ttl-expired",
        )
        with self.assertRaises(ResourceNotFoundError):
            self.engine.active_reservation_for_job(
                "job-expiring"
            )

    def test_list_reservations_expires_stale_rows_first(self) -> None:
        created = self.engine.reserve(
            "employee-1",
            "job-list-expiring",
        )
        reservation_id = created["reservation"][
            "reservation_id"
        ]
        with sqlite3.connect(self.engine.database) as connection:
            connection.execute(
                """
                UPDATE reservations
                SET expires_at=?
                WHERE reservation_id=?
                """,
                (
                    (
                        datetime.now(timezone.utc)
                        - timedelta(seconds=1)
                    ).isoformat(),
                    reservation_id,
                ),
            )

        active = self.engine.list_reservations("active")
        self.assertEqual(active, [])
        expired = self.engine.list_reservations("expired")
        self.assertEqual(len(expired), 1)
        self.assertEqual(
            expired[0]["reservation_id"],
            reservation_id,
        )


if __name__ == "__main__":
    unittest.main()
