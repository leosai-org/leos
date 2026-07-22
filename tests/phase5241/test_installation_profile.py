from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "installation_profile.py"
CATALOG_PATH = ROOT / "config" / "installation-profiles.json"
FIXTURE_PATH = ROOT / "examples" / "installation-profile-fixture.json"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "leos_installation_profile_test_module",
        MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load installation profile module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_module()


def base_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def inventory_for(fixture: dict, node_id: str = "node-test") -> dict:
    return MODULE.collect_inventory(
        node_id=node_id,
        storage_path=Path("."),
        fixture=fixture,
        contact_container_daemon=False,
    )


def recommendation_for(fixture: dict) -> tuple[dict, dict]:
    inventory = inventory_for(fixture)
    catalog = MODULE.load_profile_catalog(CATALOG_PATH)
    return inventory, MODULE.recommend_profile(inventory, catalog)


class InstallationProfileTests(unittest.TestCase):
    def test_fixture_inventory_contract(self):
        inventory = inventory_for(base_fixture())
        self.assertEqual(
            inventory["contract_version"],
            MODULE.INVENTORY_CONTRACT,
        )
        self.assertTrue(
            inventory["inventory_id"].startswith("inventory-")
        )
        self.assertFalse(
            inventory["probe"]["external_network_contacted"]
        )

    def test_standard_nvidia_selected(self):
        _, recommendation = recommendation_for(base_fixture())
        self.assertEqual(
            recommendation["selected_profile"],
            "leos-standard-nvidia",
        )
        self.assertEqual(
            recommendation["readiness"],
            "ready",
        )

    def test_large_nvidia_selected(self):
        fixture = base_fixture()
        fixture["nvidia"]["gpus"][0]["memory_mb"] = 49152
        fixture["memory"]["total_mb"] = 131072
        fixture["memory"]["available_mb"] = 98304
        fixture["storage"]["free_gb"] = 500
        _, recommendation = recommendation_for(fixture)
        self.assertEqual(
            recommendation["selected_profile"],
            "leos-standard-large-nvidia",
        )

    def test_standard_cpu_selected(self):
        fixture = base_fixture()
        fixture["nvidia"]["driver_present"] = False
        fixture["nvidia"]["gpus"] = []
        fixture["nvidia"]["nvidia_container_runtime_present"] = False
        _, recommendation = recommendation_for(fixture)
        self.assertEqual(
            recommendation["selected_profile"],
            "leos-standard-cpu",
        )
        self.assertEqual(
            recommendation["runtime"]["gpu_mode"],
            "cpu",
        )

    def test_minimum_profile_is_degraded(self):
        fixture = base_fixture()
        fixture["cpu"]["logical_cores"] = 2
        fixture["cpu"]["physical_cores"] = 2
        fixture["memory"]["total_mb"] = 4096
        fixture["memory"]["available_mb"] = 3072
        fixture["storage"]["free_gb"] = 25
        fixture["nvidia"]["driver_present"] = False
        fixture["nvidia"]["gpus"] = []
        _, recommendation = recommendation_for(fixture)
        self.assertEqual(
            recommendation["selected_profile"],
            "leos-standard-minimum",
        )
        self.assertEqual(
            recommendation["suitability"],
            "degraded",
        )

    def test_insufficient_host_is_unsupported(self):
        fixture = base_fixture()
        fixture["cpu"]["logical_cores"] = 1
        fixture["cpu"]["physical_cores"] = 1
        fixture["memory"]["total_mb"] = 2048
        fixture["memory"]["available_mb"] = 1024
        fixture["storage"]["free_gb"] = 5
        fixture["nvidia"]["driver_present"] = False
        fixture["nvidia"]["gpus"] = []
        _, recommendation = recommendation_for(fixture)
        self.assertEqual(
            recommendation["selected_profile"],
            "unsupported",
        )
        self.assertEqual(
            recommendation["readiness"],
            "unsupported",
        )
        self.assertTrue(recommendation["blockers"])

    def test_unsupported_operating_system_blocks(self):
        fixture = base_fixture()
        fixture["platform"]["system"] = "Windows"
        _, recommendation = recommendation_for(fixture)
        codes = {
            item["code"]
            for item in recommendation["blockers"]
        }
        self.assertIn("unsupported-operating-system", codes)

    def test_missing_container_runtime_requires_action(self):
        fixture = base_fixture()
        fixture["runtime"]["docker"]["present"] = False
        fixture["runtime"]["docker"]["daemon_accessible"] = False
        fixture["runtime"]["docker"]["daemon_probe_performed"] = False
        inventory, recommendation = recommendation_for(fixture)
        self.assertEqual(
            recommendation["readiness"],
            "action-required",
        )
        plan = MODULE.build_installation_plan(
            inventory,
            recommendation,
        )
        action = next(
            item
            for item in plan["actions"]
            if item["action_id"] == "install-container-runtime"
        )
        self.assertTrue(action["required"])
        self.assertEqual(action["status"], "planned")

    def test_missing_nvidia_runtime_requires_action(self):
        fixture = base_fixture()
        fixture["nvidia"]["nvidia_container_runtime_present"] = False
        inventory, recommendation = recommendation_for(fixture)
        plan = MODULE.build_installation_plan(
            inventory,
            recommendation,
        )
        action = next(
            item
            for item in plan["actions"]
            if item["action_id"]
            == "configure-nvidia-container-runtime"
        )
        self.assertTrue(action["required"])

    def test_plan_contains_compute_node_capacity(self):
        inventory, recommendation = recommendation_for(base_fixture())
        plan = MODULE.build_installation_plan(
            inventory,
            recommendation,
        )
        capacity = plan["compute_node_capacity"]
        self.assertEqual(
            capacity["contract_version"],
            MODULE.COMPUTE_NODE_CONTRACT,
        )
        self.assertEqual(capacity["node_id"], "node-test")
        self.assertGreaterEqual(
            capacity["max_concurrent_jobs"],
            1,
        )

    def test_plan_is_deterministic(self):
        inventory, recommendation = recommendation_for(base_fixture())
        first = MODULE.build_installation_plan(
            inventory,
            recommendation,
        )
        second = MODULE.build_installation_plan(
            inventory,
            recommendation,
        )
        self.assertEqual(first, second)

    def test_resource_budget_is_bounded(self):
        inventory, recommendation = recommendation_for(base_fixture())
        budget = recommendation["resource_budget"]
        self.assertGreaterEqual(
            budget["max_concurrent_employees"],
            1,
        )
        self.assertLessEqual(
            budget["max_concurrent_employees"],
            8,
        )
        self.assertLessEqual(
            budget["cpu_cores_reserved"],
            inventory["cpu"]["logical_cores"],
        )

    def test_cli_all_with_fixture(self):
        command = [
            sys.executable,
            "-B",
            str(MODULE_PATH),
            "--catalog",
            str(CATALOG_PATH),
            "--node-id",
            "node-cli",
            "--fixture",
            str(FIXTURE_PATH),
            "all",
        ]
        process = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        value = json.loads(process.stdout)
        self.assertTrue(value["ok"])
        self.assertEqual(
            value["plan"]["node_id"],
            "node-cli",
        )

    def test_cli_output_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "inventory.json"
            command = [
                sys.executable,
                "-B",
                str(MODULE_PATH),
                "--catalog",
                str(CATALOG_PATH),
                "--node-id",
                "node-output",
                "--fixture",
                str(FIXTURE_PATH),
                "--output",
                str(output),
                "detect",
            ]
            process = subprocess.run(
                command,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(
                process.returncode,
                0,
                process.stderr,
            )
            value = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(value["node_id"], "node-output")


if __name__ == "__main__":
    unittest.main()
