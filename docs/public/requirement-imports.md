# Creating and maintaining requirement sets

Create a set manually or import a source PDF. Both paths produce editable drafts.
Submission and approval create the versioned baseline used by compliance reviews.
Manual sets do not need a PDF or an extraction run. Their source controls are hidden.
Existing uploaded PDFs and historical versions are retained.

In PDF review, compare the extracted wording with the source, check the numbered
hierarchy and resolve review flags. A **Modified** label identifies wording changed
since extraction. The original extracted text remains available for comparison.
It is machine output and does not certify the source text.
Approved baseline requirements remain separate from subsequent extraction edits.
Clone an approved baseline to a draft when making a new version.

## Browsing hierarchy levels

Use **Show levels** at the top of the outline in the editor or assessment, or
above the requirement library in the requirement-set view, to show
**Top level**, **2 levels**, a deeper level available in that hierarchy, or
**All levels**. The browser remembers the choice between pages. The same setting
controls the outline and the main list. You can still expand individual outline
branches; opening a deeper item reveals it in the list.

Search and filters work together with the selected levels. They keep the original
hierarchy and do not change your depth choice, even when no results match.
Parents shown only for context cannot open an editor or clear your filters.
If matching requirements sit below the chosen depth, select a deeper level or
**Show all levels** to see them. On mobile, open the requirement outline to change
levels.

Focused editing keeps the selected requirement available. In assessments,
**Select visible** and bulk actions include only rows visible at the chosen depth.
This view setting does not change the underlying requirements, assessment scope,
completion rules or export contents.

## Optional local structured extraction

The OpenDataLoader adapter accepts source PDFs from any jurisdiction or document category.
It uses numbered headings and table rows to build explicit parent relationships,
including nested levels and source continuations. It does not invent numbered
controls for unnumbered explanatory paragraphs. Editorial subdivisions may be
added during review. Every local candidate requires human source review.

Enable the optional image for both the API and Celery worker:

```sh
docker compose -f docker-compose.yml -f docker-compose.structured.yml up --build
# For the production base, substitute docker-compose.prod.yml.
```

For a Python installation, install `backend/requirements-structured.lock` with
hash verification, provide Java 17 or later on PATH, and set
`PDF_STRUCTURE_ENGINE=opendataloader` in both API and worker environments. The
structured dependency is pinned to 2.5.11. The base installation retains its native
reader and does not require Java. The capability endpoint reports the selected
engine and basic installation availability; import verifies the actual runtime.

The adapter runs locally with the PDF worker's page, CPU, output and wall-clock
limits, plus a bounded Java heap. It does not use OpenDataLoader's hybrid server or
send document data to an AI service. A selected structured run fails explicitly if
the engine is missing, fails, or produces unusable output. If numbered structure
is ambiguous, the run creates an editable recovery draft. This includes duplicate
references, corrupt table markers, missing table numbers, and orphan continuations.
Open **Resolve source structure** in extraction QA. Use the source-page link to
check each candidate. Correct its source reference and immediate parent, attach
an unnumbered continuation to a numbered row, or exclude the candidate. A
correction can change the current draft text. The original extracted text and
source excerpt remain in the extraction record. An attached continuation also
remains as an excluded source row. Review the target text after attachment.

Recovery uses an opaque `unresolved-*` draft key. It is not a source number.
Submission and approval reject unresolved keys, flagged rows, duplicate references,
missing parents, and inconsistent numeric hierarchies. A correction cannot assign
a parent that is absent from the active extraction. Correct the source hierarchy
before resolving its child. Resolve source candidates before preparing a version.
If a draft version already exists, open **Edit Requirements** after source recovery
or extraction feedback. The **Reconcile source changes before approval** panel
shows each source/draft difference and any new source rows. Review the PDF and
the proposed differences, then use **Add missing rows and confirm reviewed
differences**. Existing draft wording is retained; new source rows are added.
Deactivate stale draft rows or repair a conflicting hierarchy before retrying.
Submission and approval reject the draft until its current source and draft
fingerprints have been reconciled. Any later source or draft edit requires a
fresh review.
For a run rejected by an older
installation, start a new structured extraction to create the recovery draft.
The system does not substitute another parser without notice. The queued run
records the selected pipeline. Diagnostics record the engine version, source
checksum, locations, and recovery reason.
The installation setting selects the engine for all PDF categories. The native
pipeline is recorded as `born_digital_v4`. Pending runs from retired parsers fail
with an instruction to start a new run. Completed extraction records are retained. Categories do not select a parser.
The native parser uses English obligation words and numbered sections. It can miss
requirements in other languages or layouts. A category or jurisdiction does not
guarantee extraction support. Use manual entry and review where extraction is incomplete.

The structured image does not include Tesseract. If you need both local
capabilities, use `docker-compose.structured-ocr.yml` with one base Compose
file. It builds the API and worker from the combined image target.
Synthetic image-only and mixed-page PDFs passed runtime checks in the native and
combined images. Scanned sources still need human source review. These checks do
not establish numbering or wording accuracy on real regulatory documents.

## Optional Jev source checks

An installation operator can enable **Jev enhancement** in Settings independently
of OpenAI or Anthropic. Jev accepts extracted text only; PDF reading and OCR still
run locally. Select the enhancement and confirm external processing for each
import. Leave it unselected to use the existing extraction workflow.

Baseline extraction finishes before its background source check. Provider outages,
limits or configuration changes leave that baseline available. The source-check
panel shows the requirements and source blocks actually checked, incomplete
coverage and findings. A completed check is not proof that every obligation was
found or that a product complies with it.

Jev checks wording, classification, parent relationships and possible missing or
duplicate obligations. Confident repairs apply only to untouched new extraction
drafts. Every changed or added row still needs human review. Original extracted
wording is retained; findings show source pages and before/after values. Possible
duplicates are suggestions and are not automatically merged or deleted. Ambiguous
source continuations, including exceptions across page boundaries, require review.

Use **Check against source** to inspect a completed extraction or explicitly
selected requirement-set version. Rechecks produce findings without rewriting
reviewed or approved requirements. Sets without a source PDF remain usable, but
source verification is unavailable. Cancelling a check prevents further provider
requests and discards unapplied results; requests already sent cannot be recalled.

The initial automatic-change threshold is 0.98 for both selected-option probability
and Choice confidence, with a further source-fidelity check. These are conservative
starting values, not a measured guarantee. Jev model and question-policy versions
are recorded with each run. Pin the model when evaluating a policy. Assess English
and Danish wording separately using reviewed source examples before relying on its
domain accuracy.

## Validation and fixtures

Public tests use synthetic source fragments. Regulatory documents and live review
exports are excluded from the publication manifest. A local regression can compare
an operator-supplied PDF with a reviewed reference tree, but the reviewed wording
must itself be checked against the source. Correct numbering alone does not prove
complete wording or regulatory compliance.

For Jev, run `.venv/bin/python scripts/evaluate-jev-quality.py` to check the
offline evaluation harness. Its bundled English and Danish examples and recorded
findings are synthetic and have not been reviewed as regulatory expectations.
Use `--fixture` and `--recorded` for your own reviewed corpus and captured findings;
the report separates language, missed repairs, false flags, harmful automatic
changes, coverage and token usage. Add `--live` only when deliberately testing
source text with an externally configured, enabled Jev key; it sends text to
TypeSafe and may incur charges. The evaluator never changes CAP requirements.

For a repeatable local comparison after installing the optional dependencies:

```sh
.venv/bin/python scripts/evaluate-structured-import.py --pdf /path/to/source.pdf \
  --baseline-jsonl /path/to/reviewed-references.jsonl --output /path/to/metrics.json
```

The optional JSONL baseline needs a `reference_id` on each line. The evaluator
compares numbered references and immediate parents. It reports editorial rows separately
and returns a failing exit code for a hierarchy mismatch. It does not score wording
as correct merely because it matches an edited baseline. Its metrics contain no
extracted wording; source files and baseline exports remain operator supplied.
