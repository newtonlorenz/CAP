#!/usr/bin/env python3
"""Evaluate an operator-supplied numbered PDF without uploading or changing a baseline."""

import argparse
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.pdf_worker import bounded_preprocess


async def evaluate(args):
    source = Path(args.pdf).resolve(strict=True)
    result = await bounded_preprocess(str(source), "dk", "scp_certification", structure_engine="opendataloader")
    rows = result.structured_requirements or []
    refs = {row["reference_id"] for row in rows}
    missing_parents = [row["reference_id"] for row in rows
                       if row["parent_reference"] and row["parent_reference"] not in refs]
    report = {
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "pages": len(result.pages), "nodes": len(rows), "unique_references": len(refs),
        "depth_counts": dict(sorted(Counter(ref.count(".") + 1 for ref in refs).items())),
        "missing_parent_references": missing_parents,
        "parser_flags": [{"reference_id": row["reference_id"], "reason": row["review_reason"]}
                         for row in rows if row["needs_review"]],
        "source": result.diagnostics.get("structured_source"),
        "wording_validated": False,
    }
    passed = bool(rows) and len(refs) == len(rows) and not missing_parents
    if args.baseline_jsonl:
        baseline = [json.loads(line) for line in Path(args.baseline_jsonl).read_text().splitlines() if line.strip()]
        expected = {row["reference_id"] for row in baseline
                    if re.fullmatch(r"\d+(?:\.\d+)*", row["reference_id"])}
        report["baseline"] = {
            "numeric_references": len(expected),
            "editorial_rows_excluded": sum(row["reference_id"] not in expected for row in baseline),
            "missing_references": sorted(expected - refs), "extra_references": sorted(refs - expected),
            # Deliberately derive immediate parents; legacy stored links can be incomplete.
            "parent_reference_mismatches": [row["reference_id"] for row in rows
                if row["parent_reference"] != (row["reference_id"].rpartition(".")[0] or None)],
        }
        passed = passed and refs == expected and not report["baseline"]["parent_reference_mismatches"]
    report["hierarchy_passed"] = passed
    output = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n")
    print(output)
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--baseline-jsonl", help="Optional local export with reference_id per row")
    parser.add_argument("--output", help="Write metrics only; no extracted document wording")
    raise SystemExit(asyncio.run(evaluate(parser.parse_args())))
