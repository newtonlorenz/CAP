"""Browser batching preserves full coverage and rejects unsafe seed targets."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "run-e2e.py"
SPEC = importlib.util.spec_from_file_location("run_e2e", SCRIPT)
run_e2e = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_e2e)


class BrowserBatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.specs = self.root / "frontend" / "e2e"
        self.specs.mkdir(parents=True)
        self.env = {
            "APP_ENV": "test",
            "CAP_ALLOW_TEST_SEED": "1",
            "DATABASE_URL": "postgresql+asyncpg://cap_test:fixture@127.0.0.1:25489/cap_e2e",
        }
        self.env["E2E_DATABASE_URL"] = self.env["DATABASE_URL"]

    def create_specs(self, count):
        paths = [f"workflow-{index:02}.spec.ts" for index in range(count)]
        for name in [*paths, "product_tour.spec.ts", "section_product_tours.spec.ts"]:
            (self.specs / name).touch()
        return [f"e2e/{name}" for name in paths]

    def test_full_suite_runs_every_workflow_once_with_separate_failure_artifacts(self):
        expected = self.create_specs(11)
        with patch.object(run_e2e.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as execute:
            self.assertEqual(run_e2e.run_browser_checks(self.env, [], root=self.root), 0)
        covered = []
        outputs = []
        for invocation in execute.call_args_list:
            args = invocation.args[0][4:]
            workflow_args = [arg for arg in args if not arg.startswith("--output=")]
            self.assertLessEqual(len(workflow_args), 4)
            covered.extend(workflow_args)
            outputs.extend(arg for arg in args if arg.startswith("--output="))
            self.assertEqual(invocation.kwargs["env"], self.env)
        self.assertEqual(covered, expected)
        self.assertEqual(len(outputs), len(set(outputs)))
        self.assertEqual(len(outputs), 3)

    def test_failed_batch_does_not_hide_failures_or_omit_remaining_workflows(self):
        self.create_specs(9)
        outcomes = [SimpleNamespace(returncode=0), SimpleNamespace(returncode=1), SimpleNamespace(returncode=0)]
        with patch.object(run_e2e.subprocess, "run", side_effect=outcomes) as execute:
            self.assertEqual(run_e2e.run_browser_checks(self.env, [], root=self.root), 1)
        self.assertEqual(execute.call_count, 3)

    def test_explicit_playwright_selection_and_options_are_preserved(self):
        self.create_specs(9)
        selection = ["redesign_journeys.spec.ts", "--grep", "concurrent-edit", "--project=chromium"]
        with patch.object(run_e2e.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as execute:
            self.assertEqual(run_e2e.run_browser_checks(self.env, selection, root=self.root), 0)
        execute.assert_called_once_with(
            ["npm", "run", "test:e2e", "--", *selection], cwd=self.root / "frontend", env=self.env
        )

    def test_non_disposable_database_is_rejected_before_playwright_or_seeding(self):
        self.create_specs(1)
        unsafe = dict(self.env, DATABASE_URL="postgresql+asyncpg://example@127.0.0.1:5432/production")
        unsafe["E2E_DATABASE_URL"] = unsafe["DATABASE_URL"]
        with patch.object(run_e2e.subprocess, "run") as execute, self.assertRaisesRegex(RuntimeError, "Refusing to seed"):
            run_e2e.run_browser_checks(unsafe, [], root=self.root)
        execute.assert_not_called()

    def test_missing_suite_fails_instead_of_reporting_success(self):
        with patch.object(run_e2e.subprocess, "run") as execute, self.assertRaisesRegex(RuntimeError, "No browser workflow"):
            run_e2e.run_browser_checks(self.env, [], root=self.root)
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
