# Documentation register

Open **Resources → Documentation register** to keep a jurisdiction's document list in one table.
Choose a register and a section tab, or use **All sections**. Each row has the same
four main columns:

| Document / record required | SCP reference | Comment/explanation | Document |
| --- | --- | --- | --- |
| Material the team needs | Supplied source reference | Explanation or condition | Current draft or document name |

Long text remains available in its original column. **Details** opens the row's
supporting information: evidence, approved requirement links, owner, applicability,
coverage review, project scope, references and import provenance. A document name
can be recorded before a file is uploaded. It does not imply that CAP has verified
or received that document.

## Add rows and sections

Create a register, choose its jurisdiction and audience, then add a section or a
row. Use the four main fields to describe the required material. Put additional
interpretation, responsibility and review information in **Details**. Existing
rows without a section remain available under **All sections** until you assign
one. Creating a row does not create an approved regulatory requirement or a
compliance result.

## Import a document list

Import Excel, CSV or TSV and check the preview. CAP reads text locally, ignores
formula cells and shows all worksheets. Banner rows can precede the headings.
Review or change the column mappings before confirming.

Each recognised documentation worksheet becomes a section, in workbook order.
The complete first-column wording is retained as **Document / record required**;
**Comment/explanation** stays separate, including when the required wording is
long. The original fourth-column draft label becomes **Document**. Notes and source
aliases remain metadata. Additional columns such as Location remain available in
**Details** with the original sheet, row, headings and cell values. The file
fingerprint is retained in the import record.

Choose which rows to create, update or skip. Updating needs an explicit existing
row and its current revision. Similar wording offers a candidate for review and
does not merge records automatically. Repeating the same original file, sheet and
row is idempotent, including confirmation in several batches. Existing sections
are reused. A revised workbook receives a new fingerprint and needs a fresh review.

Unresolved source references remain references. Link approved requirement versions
explicitly in **Details**. Project-scoped links must match the project's pinned
baseline. CAP does not invent missing legal text.

## Connect an existing process

A register can optionally link to an existing review or licence application in the
same jurisdiction. This connection provides context; it does not create another
review, application or evidence library. Certification work uses its existing
concrete review. This is the register's default process.

Different documents can use different certification reviews. In a row's process
settings, choose its own existing review, or inherit the register default. Choosing
a review does not create or copy evidence. Changing the register default preserves
rows with their own review. Before changing a row's review, explicitly remove its
current matches; their original documents and review decisions stay with the owner.

For each row, choose the existing requirement collection to use. CAP checks the
actual approved requirement and version behind the selected review item or form
question. An SCP reference helps find candidates but does not bind them by itself.
If an application has several forms or questions for the same requirement, choose
the intended question explicitly. A row can refer to more than one collection.

Linked collections show their owner's existing documents and evidence. Adding or
removing a document through either view changes that same collection. Existing
independent register coverage stays separately labelled; CAP does not move or copy
it silently. Answers, not-applicable reasons, owner approval and review decisions
retain their original workflow. Archived forms and completed reviews remain
read-only. Return a licence application to draft before changing its linked
collection through the register. Independent live-form changes after approval
make the current pack need review again; the previously approved archive is unchanged.

The register, process, form or review item, and source evidence each retain their
access restrictions. A missing permission hides the protected content and prevents
an edit that would discard hidden links. Open the original process from its link
to continue its normal workflow. Unlinking a row or changing the register's process
removes only the connection; it does not delete the owner's answers or evidence.

## Add evidence and review coverage

Use shared library files, notes and links without repeatedly uploading the same
material. Record the relevant page or section, scope, period and rationale for each
row. Evidence groups identify successive versions. Selecting a replacement does
not rewrite historical associations or review decisions.

Review coverage separately for each row. A sufficient decision needs a rationale
and valid current evidence. Changes to documentation content or its associations
clear the previous coverage review. Moving a row to another section alone preserves
its review. Expiry, archival, unavailable files and superseded versions cause
coverage to need review. Shared evidence does not transfer approval between rows.
Links are references only; CAP does not fetch their target pages.

**Details** can also reference components, managed changes and Jira issues. Those
records retain their owning workflows and access restrictions.

## Reconcile an auditor's request list

Use an existing audit form linked to a certification project in the same
jurisdiction. Import reviewed requests into that form or map existing questions.
Retain the original identifier, wording and list revision; record the period, due
date and whether it requests operator input or auditor output. Link documentation
rows and evidence to each request. Reconciliation shows unmatched requests and
documentation gaps for internal follow-up.

This uses existing CAP accounts and permissions. It does not create external
auditor accounts or send a pack to an auditor.

## Optional assistance

Manual editing, spreadsheet parsing and reference matching work without an external
provider. Optional Jev checks suggest categories, approved references and possible
duplicates across selected rows. Optional AI explains possible support in selected
evidence excerpts.

Preview the exact bounded content before confirming an external run. CAP sends
selected row text, a locally selected candidate shortlist and, for explanations,
selected supplied excerpts. It does not fetch links or send the evidence library.
Runs retain source fingerprints, model, settings revision, policy version and
progress. Resume processes the next bounded batch, including lists larger than
100 rows. Cancellation and source, access or provider-setting changes stop further
processing. Provider failure leaves retry, cancellation and manual review available.

Apply, edit or dismiss each suggestion. Requirement links need explicit selection
and validation against an approved version and project baseline. Explanations stay
draft interpretation. Suggestions do not accept coverage, determine applicability
or record a legal failure. “Not found in supplied content” describes only the
supplied excerpts.

## Freeze an internal handover

Freeze the register with selected shared-evidence versions. Linked process
collections are also captured with their current metadata and evidence bytes,
including reviews chosen independently by individual rows. The capture keeps each
review's original audience and reads each shared collection consistently once;
selected extra library items are additional attachments. Project-scoped records
include that project's rows and general rows linked to its pinned baseline or
auditor requests. Other unlinked general rows are excluded. A whole-register
snapshot includes its complete authorised scope.

The ZIP preserves the sections and four document columns, coverage and request
metadata, selected evidence and a SHA-256 manifest. The CSV uses the four main
headings plus Section. Identical selected file bytes share one frozen stored copy.
Notes retain their frozen text and links are labelled references only. Later edits
do not alter a historical snapshot; older snapshots retain their original format.
This is an internal handover, not a submission, certificate or audit opinion.

Historical downloads require current export rights to the register, every original
project/form/review-item scope and all referenced or selected source evidence,
even when the live register connection is later changed or removed. Missing rights
or invalid frozen bytes prevent an unredacted download. A snapshot can be attached
to the existing certification package workflow, with its normal approval and lock
controls.
