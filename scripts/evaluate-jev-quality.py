#!/usr/bin/env python3
"""Compare recorded Jev findings with reviewed expectations, offline unless --live is explicit.

The bundled English/Danish fixtures are synthetic, unreviewed harness examples.
Their recorded results are illustrative, not evidence of Jev accuracy or calibrated confidence.
Live mode sends fixture source text to TypeSafe and may incur charges; it never writes CAP data.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "backend/tests/fixtures/jev-quality/evaluation.json"


def matches(actual, expected):
    return (
        actual.get("kind") == expected["kind"]
        and actual.get("requirement_id") == expected.get("requirement_id")
        and all(
            actual.get("after", {}).get(k) == v
            for k, v in expected.get("after", {}).items()
        )
        and actual.get("auto_eligible", False) == expected.get("auto_eligible", False)
    )


def metrics(case, result):
    expected = case["expected"]
    meaningful = [
        finding for finding in result.get("findings", []) if finding.get("after")
    ]
    found = [
        item for item in expected if any(matches(actual, item) for actual in meaningful)
    ]
    false_flags = [
        finding
        for finding in meaningful
        if not any(matches(finding, item) for item in expected)
    ]
    harmful = []
    for finding in meaningful:
        if not finding.get("auto_eligible"):
            continue
        allowed = [
            item
            for item in expected
            if item.get("auto_eligible")
            and item["kind"] == finding.get("kind")
            and item.get("requirement_id") == finding.get("requirement_id")
        ]
        if not any(
            all(
                key in item.get("after", {}) and item["after"][key] == value
                for key, value in finding["after"].items()
            )
            for item in allowed
        ):
            harmful.append(finding)
    baseline_met = 0
    for item in expected:
        candidates = [
            row
            for row in case["rows"]
            if item.get("requirement_id") is None or row["id"] == item["requirement_id"]
        ]
        baseline_met += int(
            any(
                all(
                    row.get(key) == value
                    for key, value in item.get("after", {}).items()
                )
                for row in candidates
            )
        )
    return {
        "baseline_expected_met": baseline_met,
        "enhancement_gain": len(found) - baseline_met,
        "case_id": case["id"],
        "expected": len(expected),
        "matched": len(found),
        "missed": len(expected) - len(found),
        "false_flags": len(false_flags),
        "harmful_automatic_changes": len(harmful),
        "corrections_matched": sum(item["kind"] == "accuracy" for item in found),
        "omissions_matched": sum(item["kind"] == "omission" for item in found),
        "type_repairs_matched": sum(
            item["kind"] == "accuracy" and "requirement_type" in item.get("after", {})
            for item in found
        ),
        "parent_repairs_matched": sum(
            item["kind"] == "accuracy" and "parent_id" in item.get("after", {})
            for item in found
        ),
        "coverage": result.get("coverage", {}),
        "usage": result.get("usage", {}),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "status": result.get("status"),
    }


async def evaluate(args):
    fixture = json.loads(Path(args.fixture).read_text())
    cases = fixture["cases"]
    recorded = (
        json.loads(Path(args.recorded).read_text())
        if args.recorded
        else fixture.get("recorded_results", {})
    )
    if args.live:
        if args.recorded:
            raise ValueError("Choose live evaluation or recorded results, not both.")
        sys.path.insert(0, str(ROOT / "backend"))
        from app.config import settings
        from app.services.jev_provider import JevConfig
        from app.services.requirement_quality import evaluate_requirements

        config = JevConfig.from_settings(settings)
        if not config.enabled or not config.api_key:
            raise ValueError(
                "Live evaluation requires JEV_ENABLED=true and TYPESAFE_API_KEY configured externally."
            )
        recorded = {}
        for case in cases:
            started = time.monotonic()
            result = await evaluate_requirements(case["rows"], case["pages"], config)
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            recorded[case["id"]] = result
    missing = [case["id"] for case in cases if case["id"] not in recorded]
    if missing:
        raise ValueError(f"Missing recorded cases: {', '.join(missing)}")
    languages = {}
    for language in sorted({case["language"] for case in cases}):
        results = [
            metrics(case, recorded[case["id"]])
            for case in cases
            if case["language"] == language
        ]
        totals = {
            key: sum(result[key] for result in results)
            for key in (
                "baseline_expected_met",
                "enhancement_gain",
                "expected",
                "matched",
                "missed",
                "false_flags",
                "harmful_automatic_changes",
                "corrections_matched",
                "omissions_matched",
                "type_repairs_matched",
                "parent_repairs_matched",
            )
        }
        totals["input_tokens"] = sum(
            result["usage"].get("input_tokens", 0) for result in results
        )
        totals["output_tokens"] = sum(
            result["usage"].get("output_tokens", 0) for result in results
        )
        totals["estimated_cost"] = None
        if (
            args.input_cost_per_million is not None
            and args.output_cost_per_million is not None
        ):
            totals["estimated_cost"] = (
                totals["input_tokens"] * args.input_cost_per_million
                + totals["output_tokens"] * args.output_cost_per_million
            ) / 1_000_000
        languages[language] = {"totals": totals, "cases": results}
    report = {
        "mode": "live" if args.live else "offline_recorded",
        "synthetic": fixture.get("synthetic", False),
        "expectation_review": fixture.get("expectation_review", "unspecified"),
        "limitation": "Synthetic examples and illustrative recordings do not establish model accuracy, confidence calibration or production cost.",
        "cost_currency": args.currency,
        "languages": languages,
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(encoded)
    if args.live and args.save_recorded:
        Path(args.save_recorded).write_text(
            json.dumps(recorded, ensure_ascii=False, indent=2) + "\n"
        )
    print(encoded, end="")
    return int(
        any(
            value["totals"][key]
            for value in languages.values()
            for key in ("missed", "false_flags", "harmful_automatic_changes")
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument(
        "--recorded", help="JSON map from fixture case id to recorded evaluator result"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicitly allow paid TypeSafe calls using externally configured credentials",
    )
    parser.add_argument(
        "--save-recorded", help="Save actual live results for later offline comparison"
    )
    parser.add_argument("--output", help="Save bilingual metrics JSON")
    parser.add_argument("--input-cost-per-million", type=float)
    parser.add_argument("--output-cost-per-million", type=float)
    parser.add_argument("--currency", default="USD")
    try:
        raise SystemExit(asyncio.run(evaluate(parser.parse_args())))
    except (ValueError, KeyError) as exc:
        parser.exit(2, f"Evaluation input error: {exc}\n")
