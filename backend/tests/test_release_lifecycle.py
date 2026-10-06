"""A rehearsal must compare content, not only row counts."""

import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "release_lifecycle", Path(__file__).resolve().parents[2] / "scripts/check-release-lifecycle.py"
)
lifecycle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lifecycle)


def test_migration_can_add_columns_without_changing_existing_evidence():
    before = {"tables": {"reviews": {"columns": ["id", "evidence"], "rows": [[1, "source text"]]}}, "uploads": {"evidence.txt": "original"}}
    after = copy.deepcopy(before)
    after["tables"]["reviews"]["columns"].append("new_flag")
    after["tables"]["reviews"]["rows"][0].append(False)
    lifecycle.compare_contents(before, after)
    after["tables"]["reviews"]["rows"][0][1] = "lost evidence"
    with pytest.raises(ValueError, match="stored content"):
        lifecycle.compare_contents(before, after)


def test_same_file_count_does_not_hide_replaced_uploads():
    before = {"tables": {}, "uploads": {"evidence.txt": "original"}}
    after = {"tables": {}, "uploads": {"evidence.txt": "changed"}}
    with pytest.raises(ValueError, match="uploaded file"):
        lifecycle.compare_contents(before, after)
