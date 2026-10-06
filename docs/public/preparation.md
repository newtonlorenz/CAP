# Prepare applications, audits and evidence requests

Use **Existing forms** or **Resources → Existing forms** to collect information for an annex, certification questionnaire, pre-audit, audit or evidence request. Use **Licence Applications** to organise a submission pack. Form preparation can start before an approved requirement baseline exists. **Certifications** uses requirement assessments against approved, pinned versions. A standalone form can link to a certification project in the same jurisdiction. See [Workflows and shared materials](workflows.md) for the complete journeys.

## Licence applications

Use **Licence Applications** for a pack containing the main application, repeated annex forms and supporting documents.
You can prepare annexes alone, a licence application, or a full pack.
Add a blank form, import reviewed questions, use a saved blank form, or link an existing form.
The [application guide](applications.md) explains review, approval, submission records and follow-up.

Existing forms remain available independently of a licence pack.
Both views use the same saved form records and shared evidence.
Form readiness describes preparation for handover; it does not record submission or regulatory approval.

## Work across jurisdictions

Create separate forms for each jurisdiction and application or assessment. **Existing forms** shows saved work across jurisdictions; filter it by jurisdiction, work type and status. Each form has an owner, a due date and its own readiness checks. Shared information does not imply shared legal obligations or transfer approval between jurisdictions.

Saved blank forms and the evidence library are shared within your organisation. They are not shared with other organisations. Installation operators define jurisdictions; managers and administrators manage reusable forms and completed forms. Contributors can provide responses and evidence. Managers and administrators accept individual responses.

## Build and reuse a form

Start with a blank form, import reviewed questions, or open **Form templates** to save questions for repeated use. You can also adapt an illustrative starter. Add sections, instructions and required or optional questions. Supported answer types are text, long text, yes/no, date, number, choice and supporting evidence. Starters are examples of how to organise work, not official authority forms or jurisdiction-specific legal requirements.

When you use a saved blank form, CAP copies its questions and version into the new form. Later changes to the saved blank form affect new forms only, so work already in progress keeps its original questions.

For questions whose answers may be reused, set the same **reuse key** in the relevant forms. Use a stable key such as `applicant_registered_name`. CAP offers matching answers with their source form and jurisdiction; a user must explicitly choose to reuse one. The answer and evidence references are copied, and the new form requires its own acceptance. A matching key is a reuse aid, not a declaration that two authorities have equivalent requirements.

When importing questions from Excel, CSV or TSV, optional **Enhance preview**
uses Jev to suggest column mappings, missing answer types and required flags, and
possible duplicates. Confirm external processing first. Only the selected source
questions, help text and relevant headings are sent; applicant answers are not
part of this request. Explicit spreadsheet values and your edits take precedence.
Confident suggestions can fill missing metadata; review column mappings and
duplicates yourself. Questions are added only when you choose to add them and
save the template. Disabled, unavailable or cancelled enhancements leave ordinary
question import available.

## Collect and review evidence

The **Evidence library** holds uploaded documents, notes and links. Give each item a useful title and, where applicable, a validity period. A link is a reference; CAP does not fetch the remote page or verify its contents. Upload a file when you need to preserve the actual bytes.

Attach library items to responses without uploading duplicate copies. Evidence content and validity dates are immutable: upload or create a new item for a replacement, then update the affected responses. Archive obsolete items to prevent them being treated as current evidence. Archived evidence remains available in the historical record.

Answers save automatically after a short pause or when you leave a field, with a visible save status. Each meaningful saved change is audited and clears its previous acceptance; saving an unchanged answer does not. Acceptance remains an explicit action by a manager or administrator after pending saves finish. Marking a question not applicable requires a reason and acceptance. No/false and zero are valid answers.

If another person changes a form while you are editing, autosave pauses and preserves your drafts. Review the latest saved answers before choosing to use them or explicitly resume saving your own. Failed requests show a retry action. CAP warns before navigation while a draft is unsaved; drafts are kept in memory, not browser storage.

CAP checks required responses, acceptance and evidence validity. Missing, future-dated, expired or archived evidence prevents readiness. File integrity is checked for readiness, acceptance, downloads and exports. Validity dates use UTC calendar dates and include the valid-until date. A form without required questions cannot become ready.

## Export a completed form

Export a form to download a ZIP containing:

- `preparation.json`: the questions, answers, template version, jurisdiction, readiness, acceptance and evidence metadata.
- `responses.csv`: a readable response register, with spreadsheet formula protection.
- `evidence/`: the uploaded files referenced by responses.
- `manifest.json`: SHA-256 checksums and byte counts for the exported files.

An individual form can be exported while work is incomplete; its readiness state remains visible. Exporting never accepts an answer or submits an application. The ZIP is a point-in-time form record, not a regulator submission, licence, certificate or audit opinion. Links are included as metadata, not downloaded attachments. Exports are limited to 200 MB; larger evidence can be downloaded separately.

CAP provides its own structured forms and portable outputs. It does not automatically fill an authority's PDF/Word form or submit information to an external licensing portal. Confirm the authority's current format and submission process before transferring your reviewed responses.

Use **Use imported requirements** in the template builder to select question text from requirement versions or a completed PDF extraction in the current space. Source status and original references remain visible; review unapproved extraction text before using it. This copies blank questions and their source provenance, without importing answers or compliance decisions. Choose up to 500 points for each form.

**Download Excel template** provides recognised headings and illustrative examples. Replace those rows before uploading your own blank questions. Licence packs and their forms inherit the current space's jurisdiction.
