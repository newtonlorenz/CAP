# Jev quality evaluation fixtures

`evaluation.json` contains synthetic English and Danish source cases, proposed expectations, and illustrative recorded findings. **No human review or live Jev evaluation has validated these examples.** Their purpose is to exercise the report harness. Passing them establishes neither model accuracy nor calibrated confidence.

Run without network access:

```sh
.venv/bin/python scripts/evaluate-jev-quality.py
.venv/bin/python scripts/evaluate-jev-quality.py --recorded /path/to/results.json --output /path/to/report.json
```

A fixture has `cases`, each containing `id`, `language`, evaluator-compatible `rows` and `pages`, and `expected` findings. An expected finding states its `kind`, `requirement_id`, required `after` values and `auto_eligible`. Reviewers should include correct unchanged controls, negation, conditional scope, exceptions, OCR uncertainty and supported parent relationships. Replace `expectation_review` with review status and reviewer/date evidence after human review; do not relabel the bundled examples as reviewed.

Recorded results are a JSON object keyed by case ID, each holding the evaluator's `findings`, `status`, `coverage`, `usage` and optional `elapsed_seconds`. The fixture's recordings are illustrative; their zero usage and missing latency are not production estimates. Accuracy findings with no proposed `after` change are normal check results and do not count as false flags. Explicitly expected review-only `source_gap` and duplicate findings can be assessed using the same shape. `before` is audit context, not a predicted correction.

The report separates each language's corrections, omissions, type and parent repairs, missed expectations, unexpected suggestions, harmful automatic proposals, coverage, latency and token usage. Baseline counts compare expected values with input rows. Automatic proposals containing any unapproved field/value are reported as harmful even when a subset matches an expected repair. Exit status is 1 for missed expectations, false flags or harmful proposals; 2 for invalid inputs. Cost remains unknown unless both operator-supplied token rates are given.

Live evaluation requires an explicit `--live` plus externally configured `JEV_ENABLED=true` and `TYPESAFE_API_KEY`. It sends fixture source text to TypeSafe and can incur charges. It does not edit CAP data. Use `--save-recorded /path/to/results.json` to retain responses for repeatable offline evaluation. Live mode was not run when these fixtures were created.
