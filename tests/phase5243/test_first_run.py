from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/first_run.py"
SPEC = importlib.util.spec_from_file_location("first_run", MODULE_PATH)
first_run = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(first_run)


class FirstRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = json.loads(
            (ROOT / "examples/installation-plan.json").read_text()
        )
        self.manifest = json.loads(
            (ROOT / "examples/installation-manifest.json").read_text()
        )
        self.config = json.loads(
            (ROOT / "config/first-run.json").read_text()
        )
        self.catalog = json.loads(
            (ROOT / "config/first-run-runtime-catalog.json").read_text()
        )
        self.fixture = json.loads(
            (ROOT / "examples/first-run-fixture.json").read_text()
        )

    def docs(self, **overrides):
        args = dict(
            plan=self.plan,
            manifest=self.manifest,
            config=self.config,
            runtime_catalog=self.catalog,
            target_root="leos-first-run-example",
            admin_username="admin",
            admin_display_name="LEOS Administrator",
            admin_email="admin@example.invalid",
            node_name="LEOS Primary Node",
            runtime_profile="local-standard-nvidia",
            allow_network=False,
            generated_at="2026-07-20T00:00:00+00:00",
            state="complete",
        )
        args.update(overrides)
        return first_run.build_documents(**args)

    def make_target(self, temp: Path) -> Path:
        target = temp / "leos"
        (target / "state").mkdir(parents=True)
        manifest = dict(self.manifest)
        manifest["target_root"] = str(target)
        (target / "state/installation-manifest.json").write_text(
            json.dumps(manifest)
        )
        (target / "state/installation-plan.json").write_text(
            json.dumps(self.plan)
        )
        return target

    def test_stable_id_is_deterministic(self):
        self.assertEqual(
            first_run.stable_id("x", {"a": 1}),
            first_run.stable_id("x", {"a": 1}),
        )

    def test_documents_have_required_contracts(self):
        docs = self.docs()
        self.assertEqual(len(docs), 6)
        for relative, contract in first_run.REQUIRED_OUTPUTS:
            self.assertEqual(docs[relative]["contract_version"], contract)

    def test_no_plaintext_secret_fields(self):
        docs = self.docs()
        self.assertFalse(first_run.contains_forbidden_secret(docs))
        self.assertFalse(
            docs["state/administrator-bootstrap.json"][
                "plaintext_secret_persisted"
            ]
        )

    def test_nvidia_runtime_selected(self):
        docs = self.docs()
        runtime = docs["state/runtime-selection.json"]
        self.assertEqual(runtime["profile_id"], "local-standard-nvidia")
        self.assertEqual(runtime["acceleration"], "nvidia")

    def test_cpu_runtime_selected(self):
        plan = json.loads(json.dumps(self.plan))
        plan["selected_profile"] = "leos-standard-cpu"
        manifest = json.loads(json.dumps(self.manifest))
        manifest["selected_profile"] = "leos-standard-cpu"
        docs = self.docs(
            plan=plan,
            manifest=manifest,
            runtime_profile="local-standard-cpu",
        )
        self.assertEqual(
            docs["state/runtime-selection.json"]["acceleration"],
            "cpu",
        )

    def test_remote_runtime_requires_network_permission(self):
        with self.assertRaises(first_run.FirstRunError):
            self.docs(runtime_profile="external-openai-compatible")

    def test_remote_runtime_authorized_without_contact(self):
        docs = self.docs(
            runtime_profile="external-openai-compatible",
            allow_network=True,
        )
        runtime = docs["state/runtime-selection.json"]
        self.assertTrue(runtime["network_permission_granted"])
        self.assertFalse(runtime["external_network_contacted"])

    def test_admin_username_validation(self):
        with self.assertRaises(first_run.FirstRunError):
            self.docs(admin_username="A")

    def test_node_name_validation(self):
        with self.assertRaises(first_run.FirstRunError):
            self.docs(node_name="x")

    def test_unknown_runtime_is_blocked(self):
        with self.assertRaises(first_run.FirstRunError):
            self.docs(runtime_profile="missing-runtime")

    def test_manifest_plan_mismatch_is_blocked(self):
        manifest = dict(self.manifest)
        manifest["plan_id"] = "wrong"
        with self.assertRaises(first_run.FirstRunError):
            self.docs(manifest=manifest)

    def test_apply_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as td:
            target = self.make_target(Path(td))
            docs = self.docs(target_root=str(target))
            with self.assertRaises(first_run.FirstRunError):
                first_run.apply_documents(
                    target=target,
                    documents=docs,
                    config=self.config,
                    confirm="wrong",
                )

    def test_apply_writes_six_files(self):
        with tempfile.TemporaryDirectory() as td:
            target = self.make_target(Path(td))
            docs = self.docs(target_root=str(target))
            result = first_run.apply_documents(
                target=target,
                documents=docs,
                config=self.config,
                confirm=docs["state/first-run-session.json"]["session_id"],
            )
            self.assertEqual(result["changed_count"], 6)

    def test_second_apply_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            target = self.make_target(Path(td))
            docs = self.docs(target_root=str(target))
            token = docs["state/first-run-session.json"]["session_id"]
            first_run.apply_documents(
                target=target, documents=docs,
                config=self.config, confirm=token,
            )
            second = first_run.apply_documents(
                target=target, documents=docs,
                config=self.config, confirm=token,
            )
            self.assertTrue(second["idempotent"])
            self.assertEqual(second["changed_count"], 0)

    def test_partial_state_is_resumed(self):
        with tempfile.TemporaryDirectory() as td:
            target = self.make_target(Path(td))
            docs = self.docs(target_root=str(target))
            token = docs["state/first-run-session.json"]["session_id"]
            first_run.apply_documents(
                target=target, documents=docs,
                config=self.config, confirm=token,
            )
            (target / "state/runtime-selection.json").unlink()
            resumed = first_run.apply_documents(
                target=target, documents=docs,
                config=self.config, confirm=token,
            )
            self.assertEqual(resumed["changed_count"], 1)

    def test_inspect_complete(self):
        with tempfile.TemporaryDirectory() as td:
            target = self.make_target(Path(td))
            docs = self.docs(target_root=str(target))
            token = docs["state/first-run-session.json"]["session_id"]
            first_run.apply_documents(
                target=target, documents=docs,
                config=self.config, confirm=token,
            )
            inspected = first_run.inspect_target(target)
            self.assertTrue(inspected["complete"])

    def test_inspect_missing_file_fails(self):
        with tempfile.TemporaryDirectory() as td:
            target = self.make_target(Path(td))
            inspected = first_run.inspect_target(target)
            self.assertFalse(inspected["ok"])

    def test_lock_blocks_concurrent_apply(self):
        with tempfile.TemporaryDirectory() as td:
            target = self.make_target(Path(td))
            lock = target / "runtime/first-run.lock"
            lock.parent.mkdir(parents=True)
            lock.write_text("busy")
            docs = self.docs(target_root=str(target))
            with self.assertRaises(first_run.FirstRunError):
                first_run.apply_documents(
                    target=target,
                    documents=docs,
                    config=self.config,
                    confirm=docs["state/first-run-session.json"]["session_id"],
                )

    def test_injected_failure_rolls_back_new_files(self):
        with tempfile.TemporaryDirectory() as td:
            target = self.make_target(Path(td))
            docs = self.docs(target_root=str(target))
            with self.assertRaises(first_run.InjectedFailure):
                first_run.apply_documents(
                    target=target,
                    documents=docs,
                    config=self.config,
                    confirm=docs["state/first-run-session.json"]["session_id"],
                    fail_after=3,
                )
            self.assertFalse((target / "config/first-run.json").exists())

    def test_injected_failure_restores_existing_file(self):
        with tempfile.TemporaryDirectory() as td:
            target = self.make_target(Path(td))
            docs = self.docs(target_root=str(target))
            token = docs["state/first-run-session.json"]["session_id"]
            first_run.apply_documents(
                target=target, documents=docs,
                config=self.config, confirm=token,
            )
            original = (target / "config/first-run.json").read_bytes()
            changed_docs = self.docs(
                target_root=str(target),
                admin_display_name="Changed Administrator",
            )
            with self.assertRaises(first_run.InjectedFailure):
                first_run.apply_documents(
                    target=target,
                    documents=changed_docs,
                    config=self.config,
                    confirm=changed_docs["state/first-run-session.json"]["session_id"],
                    fail_after=2,
                )
            self.assertEqual(
                (target / "config/first-run.json").read_bytes(),
                original,
            )

    def test_plan_command_is_non_mutating(self):
        with tempfile.TemporaryDirectory() as td:
            target = self.make_target(Path(td))
            before = sorted(p.relative_to(target).as_posix() for p in target.rglob("*"))
            process = subprocess.run(
                [
                    str(ROOT / "bin/leos-first-run"),
                    "plan",
                    "--target-root", str(target),
                    "--runtime-profile", "local-standard-nvidia",
                    "--generated-at", "2026-07-20T00:00:00+00:00",
                ],
                cwd=ROOT, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=False,
            )
            after = sorted(p.relative_to(target).as_posix() for p in target.rglob("*"))
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(before, after)

    def test_cli_output_file(self):
        with tempfile.TemporaryDirectory() as td:
            target = self.make_target(Path(td))
            output = Path(td) / "result.json"
            process = subprocess.run(
                [
                    str(ROOT / "bin/leos-first-run"),
                    "plan",
                    "--target-root", str(target),
                    "--runtime-profile", "local-standard-nvidia",
                    "--generated-at", "2026-07-20T00:00:00+00:00",
                    "--output", str(output),
                ],
                cwd=ROOT, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertTrue(output.is_file())

    def test_plan_result_contract(self):
        docs = self.docs(state="planned")
        result = first_run.render_result(
            command="plan",
            target=Path("leos-first-run-example"),
            documents=docs,
            apply_record=None,
        )
        self.assertEqual(result["contract_version"], "leos.first-run-result.v1")

    def test_readiness_is_ready(self):
        docs = self.docs()
        readiness = docs["state/first-run-readiness.json"]
        self.assertEqual(readiness["status"], "ready")
        self.assertEqual(readiness["blockers"], [])

    def test_session_is_resume_safe(self):
        docs = self.docs()
        session = docs["state/first-run-session.json"]
        self.assertTrue(session["resume_safe"])
        self.assertTrue(session["requires_confirmation"])


if __name__ == "__main__":
    unittest.main()
