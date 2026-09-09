"""Regression coverage for the four post-merge workbench review findings."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

import psutil

from hippo_eval import cli
from hippo_eval.bootstrap import select_artifact_root
from hippo_eval.cli import (LOCK_SCHEMA, acquire_inference_lock,
                            release_inference_lock, main)
from hippo_eval.contracts import load_json, write_json


ROOT = Path(__file__).resolve().parents[1]


class CompareExitTests(unittest.TestCase):
    def invoke(self, comparison, report=True):
        before, after = {"run_id": "before"}, {"run_id": "after"}
        analysis = {"valid": True}
        argv = ["compare", "before.json", "after.json", "--out", "comparison.json"]
        if report:
            argv += ["--report-out", "comparison-report"]
        with patch("hippo_eval.cli.read_fixtures", return_value=({}, {}, {})), \
             patch("hippo_eval.cli.load_json", side_effect=[before, after]), \
             patch("hippo_eval.metrics.score_bundle", return_value=analysis) as scorer, \
             patch("hippo_eval.metrics.compare_runs", return_value=comparison), \
             patch("hippo_eval.cli.write_json") as writer, \
             patch("hippo_eval.reporting.write_reports") as reporter:
            code = main(argv)
        self.assertEqual(scorer.call_count, 2)
        writer.assert_called_once_with(Path("comparison.json"), comparison)
        if report:
            reporter.assert_called_once_with(after, analysis, Path("comparison-report"), comparison)
        else:
            reporter.assert_not_called()
        return code

    def test_compatible_non_regression_succeeds(self):
        self.assertEqual(self.invoke({"compatible": True, "regressed": False}), 0)

    def test_compatible_regression_fails_after_writing_artifacts(self):
        self.assertEqual(self.invoke({"compatible": True, "regressed": True,
                                      "reasons": ["quality decreased"]}), 1)

    def test_incompatible_comparison_fails_after_writing_artifacts(self):
        self.assertEqual(self.invoke({"compatible": False, "regressed": None,
                                      "reasons": ["fixture differs"]}), 1)

    def test_compatible_unknown_comparison_does_not_claim_success(self):
        self.assertEqual(self.invoke({"compatible": True, "regressed": None}), 1)


class SmokeDiscoveryTests(unittest.TestCase):
    def run_case(self, source: str | None, pattern: str | None = None, nested=False):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tests = root / "tests"
            tests.mkdir()
            if source is None:
                selected_pattern = pattern or "missing_*.py"
            else:
                name = f"test_generated_{uuid.uuid4().hex}.py"
                destination = tests
                if nested:
                    destination = tests / f"package_{uuid.uuid4().hex}"
                    destination.mkdir()
                    (destination / "__init__.py").write_text("", encoding="utf-8")
                (destination / name).write_text(source, encoding="utf-8")
                selected_pattern = pattern or name
            receipt = root / "receipt.json"
            with patch("hippo_eval.cli.ROOT", root), \
                 patch("hippo_eval.cli.source_identity", return_value={"source_digest": "fixed"}):
                code = main(["smoke", "--pattern", selected_pattern,
                             "--out", str(receipt)])
            return code, load_json(receipt)

    def test_unmatched_pattern_fails_without_fallback(self):
        code, receipt = self.run_case(None, "definitely_missing_*.py")
        self.assertEqual(code, 1)
        self.assertFalse(receipt["passed"])
        self.assertEqual(receipt["status"], "DISCOVERY_FAILED")
        self.assertEqual(receipt["failure_reason"], "NO_TEST_FILES_DISCOVERED")
        self.assertEqual(receipt["pattern"], "definitely_missing_*.py")
        self.assertEqual(receipt["test_files_discovered"], 0)
        self.assertEqual(receipt["tests_run"], 0)

    def test_matching_file_with_no_tests_fails(self):
        code, receipt = self.run_case("# deliberately contains no tests\n")
        self.assertEqual(code, 1)
        self.assertEqual(receipt["failure_reason"], "NO_TEST_CASES_DISCOVERED")
        self.assertEqual(receipt["test_files_discovered"], 1)
        self.assertEqual(receipt["tests_discovered"], 0)
        self.assertEqual(receipt["tests_executed"], 0)

    def test_normal_discovery_executes_and_succeeds(self):
        source = ("import unittest\n"
                  "class Passing(unittest.TestCase):\n"
                  "    def test_ok(self):\n"
                  "        self.assertEqual(2 + 2, 4)\n")
        code, receipt = self.run_case(source)
        self.assertEqual(code, 0)
        self.assertTrue(receipt["passed"])
        self.assertEqual(receipt["status"], "PASSED")
        self.assertEqual(receipt["tests_discovered"], 1)
        self.assertEqual(receipt["tests_run"], 1)
        self.assertEqual(receipt["tests_executed"], 1)

    def test_executed_failure_is_distinct_from_discovery_failure(self):
        source = ("import unittest\n"
                  "class Failing(unittest.TestCase):\n"
                  "    def test_bad(self):\n"
                  "        self.fail('synthetic failure')\n")
        code, receipt = self.run_case(source)
        self.assertEqual(code, 1)
        self.assertEqual(receipt["status"], "TEST_FAILURES")
        self.assertEqual(receipt["failure_reason"], "TESTS_FAILED")
        self.assertEqual(receipt["tests_run"], 1)
        self.assertEqual(receipt["failures"], 1)

    def test_all_skipped_cases_do_not_claim_execution(self):
        source = ("import unittest\n"
                  "class Skipped(unittest.TestCase):\n"
                  "    @unittest.skip('synthetic skip')\n"
                  "    def test_skipped(self):\n"
                  "        pass\n")
        code, receipt = self.run_case(source)
        self.assertEqual(code, 1)
        self.assertEqual(receipt["status"], "ZERO_TESTS_EXECUTED")
        self.assertEqual(receipt["tests_run"], 1)
        self.assertEqual(receipt["tests_executed"], 0)

    def test_fixture_setup_error_is_reported_as_test_failure(self):
        source = ("import unittest\n"
                  "class BrokenSetup(unittest.TestCase):\n"
                  "    @classmethod\n"
                  "    def setUpClass(cls):\n"
                  "        raise RuntimeError('synthetic setup failure')\n"
                  "    def test_never_runs(self):\n"
                  "        pass\n")
        code, receipt = self.run_case(source)
        self.assertEqual(code, 1)
        self.assertEqual(receipt["status"], "TEST_FAILURES")
        self.assertEqual(receipt["tests_run"], 0)
        self.assertEqual(receipt["errors"], 1)

    def test_nested_package_discovery_and_manifest_agree(self):
        source = ("import unittest\n"
                  "class Nested(unittest.TestCase):\n"
                  "    def test_ok(self):\n"
                  "        self.assertTrue(True)\n")
        code, receipt = self.run_case(source, nested=True)
        self.assertEqual(code, 0)
        self.assertEqual(receipt["test_files_discovered"], 1)
        self.assertEqual(receipt["tests_executed"], 1)

    def test_module_level_skip_cannot_make_executed_count_negative_or_pass(self):
        source = ("import unittest\n"
                  "raise unittest.SkipTest('synthetic module skip')\n")
        code, receipt = self.run_case(source)
        self.assertEqual(code, 1)
        self.assertEqual(receipt["status"], "ZERO_TESTS_EXECUTED")
        self.assertGreaterEqual(receipt["skipped"], 1)
        self.assertEqual(receipt["tests_executed"], 0)

    def test_fixture_skip_does_not_cancel_an_executed_passing_test(self):
        source = ("import unittest\n"
                  "class Passing(unittest.TestCase):\n"
                  "    def test_ok(self):\n"
                  "        self.assertTrue(True)\n"
                  "class SkippedFixture(unittest.TestCase):\n"
                  "    @classmethod\n"
                  "    def setUpClass(cls):\n"
                  "        raise unittest.SkipTest('synthetic fixture skip')\n"
                  "    def test_not_started(self):\n"
                  "        pass\n")
        code, receipt = self.run_case(source)
        self.assertEqual(code, 0)
        self.assertTrue(receipt["passed"])
        self.assertEqual(receipt["tests_executed"], 1)
        self.assertEqual(receipt["skipped"], 1)


class InferenceLockTests(unittest.TestCase):
    def make_record(self, supervisor, worker=None, phase="STARTING"):
        return {"schema": LOCK_SCHEMA, "claim_id": uuid.uuid4().hex,
                "workspace_id": cli._workspace_id(), "plan_digest": "a" * 64,
                "phase": phase, "created_at": cli.now(),
                "boot_time": float(psutil.boot_time()),
                "supervisor": supervisor, "worker": worker}

    def dead_pid(self):
        pid = 2**31 - 1
        while psutil.pid_exists(pid):
            pid -= 1
        return pid

    def test_live_owner_remains_protected(self):
        with tempfile.TemporaryDirectory() as td:
            lock = Path(td) / "inference.lock"
            claim = acquire_inference_lock(lock, psutil, "a" * 64)
            original = lock.read_bytes()
            with self.assertRaisesRegex(ValueError, "remains protected"):
                acquire_inference_lock(lock, psutil, "b" * 64)
            self.assertEqual(lock.read_bytes(), original)
            release_inference_lock(lock, claim, psutil)

    def test_live_orphan_worker_protects_claim(self):
        with tempfile.TemporaryDirectory() as td:
            lock = Path(td) / "inference.lock"
            current = cli._process_reference(psutil, os.getpid())
            stale_supervisor = {"pid": self.dead_pid(), "create_time": 1.0}
            write_json(lock, self.make_record(stale_supervisor, current, "RUNNING"))
            original = lock.read_bytes()
            with self.assertRaisesRegex(ValueError, "remains protected"):
                acquire_inference_lock(lock, psutil, "b" * 64)
            self.assertEqual(lock.read_bytes(), original)

    def test_boot_time_drift_never_overrides_a_live_process_identity(self):
        with tempfile.TemporaryDirectory() as td:
            lock = Path(td) / "inference.lock"
            current = cli._process_reference(psutil, os.getpid())
            record = self.make_record(current)
            record["boot_time"] -= 10.0
            write_json(lock, record)
            original = lock.read_bytes()
            with self.assertRaisesRegex(ValueError, "AMBIGUOUS"):
                acquire_inference_lock(lock, psutil, "b" * 64)
            self.assertEqual(lock.read_bytes(), original)

    def test_dead_owner_is_safely_reclaimed(self):
        with tempfile.TemporaryDirectory() as td:
            lock = Path(td) / "inference.lock"
            stale = {"pid": self.dead_pid(), "create_time": 1.0}
            write_json(lock, self.make_record(stale))
            claim = acquire_inference_lock(lock, psutil, "b" * 64)
            self.assertEqual(load_json(lock)["claim_id"], claim)
            release_inference_lock(lock, claim, psutil)
            self.assertFalse(lock.exists())

    def test_pid_reuse_identity_is_reclaimed(self):
        with tempfile.TemporaryDirectory() as td:
            lock = Path(td) / "inference.lock"
            reused = cli._process_reference(psutil, os.getpid())
            reused["create_time"] += 1.0
            write_json(lock, self.make_record(reused))
            claim = acquire_inference_lock(lock, psutil, "b" * 64)
            release_inference_lock(lock, claim, psutil)

    def test_zombie_owner_is_safely_reclaimed(self):
        with tempfile.TemporaryDirectory() as td:
            lock = Path(td) / "inference.lock"
            zombie_pid = self.dead_pid()
            zombie_created = 12345.0
            write_json(lock, self.make_record(
                {"pid": zombie_pid, "create_time": zombie_created}))
            real_process = psutil.Process

            class SyntheticZombie:
                def create_time(self):
                    return zombie_created

                def is_running(self):
                    return True

                def status(self):
                    return psutil.STATUS_ZOMBIE

            def process_for(pid):
                if pid == zombie_pid:
                    return SyntheticZombie()
                return real_process(pid)

            with patch.object(psutil, "Process", side_effect=process_for):
                claim = acquire_inference_lock(lock, psutil, "b" * 64)
                self.assertEqual(load_json(lock)["claim_id"], claim)
                release_inference_lock(lock, claim, psutil)
            self.assertFalse(lock.exists())

    def test_zombie_supervisor_does_not_override_a_live_worker(self):
        zombie_pid = self.dead_pid()
        zombie_created = 12345.0
        current = cli._process_reference(psutil, os.getpid())
        record = self.make_record(
            {"pid": zombie_pid, "create_time": zombie_created},
            current, "RUNNING")

        class SyntheticZombie:
            def create_time(self):
                return zombie_created

            def is_running(self):
                return True

            def status(self):
                return psutil.STATUS_ZOMBIE

        class SyntheticLive:
            def create_time(self):
                return current["create_time"]

            def is_running(self):
                return True

            def status(self):
                return psutil.STATUS_RUNNING

        def process_for(pid):
            if pid == zombie_pid:
                return SyntheticZombie()
            if pid == current["pid"]:
                return SyntheticLive()
            raise psutil.NoSuchProcess(pid)

        with patch.object(psutil, "Process", side_effect=process_for):
            self.assertEqual(cli._lock_owner_state(record, psutil)[0], "LIVE")

    def test_process_disappearing_during_status_read_is_stale(self):
        reference = {"pid": self.dead_pid(), "create_time": 12345.0}

        class DisappearingProcess:
            def create_time(self):
                return reference["create_time"]

            def is_running(self):
                return True

            def status(self):
                raise psutil.NoSuchProcess(reference["pid"])

        with patch.object(psutil, "Process", return_value=DisappearingProcess()):
            self.assertEqual(cli._process_reference_state(reference, psutil), "STALE")

    def test_unreadable_live_status_is_ambiguous_and_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            lock = Path(td) / "inference.lock"
            owner_pid = self.dead_pid()
            created = 12345.0
            write_json(lock, self.make_record(
                {"pid": owner_pid, "create_time": created}))
            original = lock.read_bytes()

            class UnreadableProcess:
                def create_time(self):
                    return created

                def is_running(self):
                    return True

                def status(self):
                    raise psutil.AccessDenied(owner_pid)

            with patch.object(psutil, "Process", return_value=UnreadableProcess()):
                with self.assertRaisesRegex(ValueError, "AMBIGUOUS"):
                    acquire_inference_lock(lock, psutil, "b" * 64)
            self.assertEqual(lock.read_bytes(), original)

    def test_nonterminal_process_status_remains_live(self):
        reference = {"pid": self.dead_pid(), "create_time": 12345.0}

        class SleepingProcess:
            def create_time(self):
                return reference["create_time"]

            def is_running(self):
                return True

            def status(self):
                return psutil.STATUS_SLEEPING

        with patch.object(psutil, "Process", return_value=SleepingProcess()):
            self.assertEqual(cli._process_reference_state(reference, psutil), "LIVE")

    def test_pid_reuse_is_stale_without_needing_status_access(self):
        reference = {"pid": self.dead_pid(), "create_time": 12345.0}

        class ReusedProcess:
            def create_time(self):
                return reference["create_time"] + 1.0

            def is_running(self):
                return True

            def status(self):
                raise AssertionError("status must not be read for a reused PID")

        with patch.object(psutil, "Process", return_value=ReusedProcess()):
            self.assertEqual(cli._process_reference_state(reference, psutil), "STALE")

    def test_malformed_state_fails_closed_and_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            lock = Path(td) / "inference.lock"
            malformed = b'{"schema":"hippo-eval-inference-lock/v2"'
            lock.write_bytes(malformed)
            with self.assertRaisesRegex(ValueError, "unsafe to reclaim"):
                acquire_inference_lock(lock, psutil, "b" * 64)
            self.assertEqual(lock.read_bytes(), malformed)

    def test_ambiguous_workspace_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            lock = Path(td) / "inference.lock"
            record = self.make_record({"pid": self.dead_pid(), "create_time": 1.0})
            record["workspace_id"] = "0" * 64
            write_json(lock, record)
            original = lock.read_bytes()
            with self.assertRaisesRegex(ValueError, "ambiguous workspace"):
                acquire_inference_lock(lock, psutil, "b" * 64)
            self.assertEqual(lock.read_bytes(), original)

    def test_legacy_pid_only_lock_fails_closed_even_when_pid_is_dead(self):
        with tempfile.TemporaryDirectory() as td:
            lock = Path(td) / "inference.lock"
            original = str(self.dead_pid()).encode("ascii")
            lock.write_bytes(original)
            with self.assertRaisesRegex(ValueError, "AMBIGUOUS"):
                acquire_inference_lock(lock, psutil, "b" * 64)
            self.assertEqual(lock.read_bytes(), original)

    def test_normal_finally_cleanup_removes_exact_claim(self):
        with tempfile.TemporaryDirectory() as td:
            lock = Path(td) / "inference.lock"
            with self.assertRaisesRegex(RuntimeError, "synthetic interruption"):
                claim = acquire_inference_lock(lock, psutil, "a" * 64)
                try:
                    raise RuntimeError("synthetic interruption")
                finally:
                    release_inference_lock(lock, claim, psutil)
            self.assertFalse(lock.exists())

    def test_cleanup_never_removes_a_replacement_claim(self):
        with tempfile.TemporaryDirectory() as td:
            lock = Path(td) / "inference.lock"
            claim = acquire_inference_lock(lock, psutil, "a" * 64)
            original = lock.read_bytes()
            with self.assertRaisesRegex(ValueError, "replacement"):
                release_inference_lock(lock, uuid.uuid4().hex, psutil)
            self.assertEqual(lock.read_bytes(), original)
            release_inference_lock(lock, claim, psutil)


class NondefaultArtifactRootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.working = Path(cls.temporary.name) / "working directory"
        cls.working.mkdir()
        cls.output_root = ROOT / ".scratch" / f"review-fixes-{uuid.uuid4().hex}"
        cls.output_root.mkdir(parents=True)
        cls.artifacts = cls.working / "custom artifacts"
        cls.site = cls.artifacts / "site"
        cls.site.mkdir(parents=True)
        source_site = ROOT / ".artifacts" / "site"
        for package in ("apsw", "psutil"):
            shutil.copytree(source_site / package, cls.site / package)
            matches = list(source_site.glob(f"{package}-*.dist-info"))
            if len(matches) != 1:
                raise AssertionError(f"Expected one staged {package} distribution, found {matches}")
            shutil.copytree(matches[0], cls.site / matches[0].name)
        marker = cls.site / "hippo_bootstrap_marker-1.0.dist-info"
        marker.mkdir()
        (marker / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: hippo-bootstrap-marker\nVersion: 1.0\n",
            encoding="utf-8")
        semantic_marker = cls.site / "sentence_transformers-999.0.dist-info"
        semantic_marker.mkdir()
        (semantic_marker / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: sentence-transformers\nVersion: 999.0\n",
            encoding="utf-8")
        cls.pth_sentinel = cls.working / "pth-executed.txt"
        (cls.site / "must_not_execute.pth").write_text(
            f"import pathlib; pathlib.Path({str(cls.pth_sentinel)!r}).write_text('unsafe')\n",
            encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.output_root)
        cls.temporary.cleanup()

    def run_workbench(self, method: str, output_name: str):
        output = self.output_root / output_name
        command = [str(Path(getattr(sys, "_base_executable", sys.executable)).resolve()),
                   "-I", "-S", str(ROOT / "workbench.py"), "run",
                   "--methods", method, "--max-seconds", "60",
                   "--out", str(output), "--artifacts", "custom artifacts"]
        completed = subprocess.run(command, cwd=self.working, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   timeout=90, check=False)
        diagnostics = []
        for name in ("execution.txt", "failure.json", "resource.json"):
            path = output / name
            if path.is_file():
                diagnostics.append(f"\n--- {name} ---\n{path.read_text(encoding='utf-8')}")
        completed.stdout += "".join(diagnostics)
        return completed, output

    def test_abbreviated_artifact_option_is_rejected(self):
        with self.assertRaises(SystemExit) as raised:
            main(["run", "--art", str(self.artifacts), "--out", "unused"])
        self.assertEqual(raised.exception.code, 2)

    def test_bootstrap_stops_at_positional_terminator(self):
        selected = select_artifact_root(
            ["freeze", "--artifacts", "selected", "--", "--artifacts=other"],
            "default")
        self.assertEqual(selected, (Path.cwd() / "selected").resolve())

    def test_bootstrap_accepts_exact_equals_form(self):
        selected = select_artifact_root(
            ["run", f"--artifacts={self.artifacts}"], "default")
        self.assertEqual(selected, self.artifacts.resolve())

    def assert_selected_identity(self, output: Path):
        plan = load_json(output / "execution-plan.json")
        worker = load_json(output / "worker-result.json")
        self.assertEqual(plan["identity"]["dependencies"]["hippo-bootstrap-marker"], "1.0")
        self.assertEqual(plan["identity"]["dependencies"]["sentence-transformers"], "999.0")
        self.assertEqual(plan["identity"]["dependency_digest"],
                         worker["identity"]["dependency_digest"])
        self.assertEqual(worker["execution_runtime"]["artifact_site"], "<ARTIFACTS>/site")
        self.assertTrue(worker["execution_runtime"]["isolated"])
        self.assertTrue(worker["execution_runtime"]["no_site"])
        self.assertNotIn("DEPENDENCIES_CHANGED_DURING_RUN", worker["integrity_errors"])
        self.assertFalse(self.pth_sentinel.exists())
        return worker

    def test_nondefault_root_bootstraps_lexical_worker_before_identity(self):
        completed, output = self.run_workbench("lexical", "lexical output")
        self.assertEqual(completed.returncode, 0, completed.stdout)
        worker = self.assert_selected_identity(output)
        self.assertEqual(worker["methods"][0]["status"], "EXECUTED")
        self.assertFalse((ROOT / ".scratch" / "inference.lock").exists())

    def test_nondefault_root_semantic_not_run_does_not_mutate_identity(self):
        completed, output = self.run_workbench("bge", "semantic output")
        self.assertEqual(completed.returncode, 1, completed.stdout)
        self.assertTrue((output / "worker-result.json").is_file(), completed.stdout)
        worker = self.assert_selected_identity(output)
        self.assertEqual(worker["methods"][0]["status"], "NOT_RUN")
        self.assertIn("MODEL_NOT_STAGED", " ".join(worker["methods"][0]["errors"]))
        self.assertFalse((ROOT / ".scratch" / "inference.lock").exists())


if __name__ == "__main__":
    unittest.main()
