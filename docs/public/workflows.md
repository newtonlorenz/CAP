# Workflows and shared materials

CAP has three main workspaces: Licence Applications, Certifications and
Change Management. Start with the outcome you are preparing. Reusable requirements, saved blank forms and evidence are secondary resources.
Existing forms remain accessible without creating duplicate work.

Requirements describe obligations or source questions. A template defines reusable
form questions. A completed form contains answers and supporting evidence. These
are separate records: importing questions does not copy answers or decisions.

## Licence applications

Choose the application scope, required forms, supporting information, owners and
access. Complete the forms, attach valid evidence and obtain acceptance for required
answers. Request internal pack approval, then record the manual submission.

An application does not need an approved requirement baseline. A form can start
blank, from a template or spreadsheet, or from requirements including a draft PDF
extraction. Check draft source warnings and the imported wording before saving.
Jev enhancement is optional and does not replace source checking or acceptance.

After submission, manage authority queries and responses. If the pack needs changes,
return it to draft and obtain a new approval. Each approved pack preserves its own
version; later edits do not rewrite that history. A recorded authority outcome is
reported by the user. CAP does not issue a licence.

## Compliance certification

Start a test or audit engagement and record its scope, provider and owners. Choose
approved requirement versions before assessment; these form the pinned baseline. Work through requirement assessments, complete
supporting forms and evidence, then approve and lock the submission package.

A requirement assessment records compliance status, evidence and reviewer decisions
against a fixed baseline. It is different from internal package approval. Standalone
assessments remain available through the assessment overview.

Use maintenance plans in the project’s History section to set a cadence and manually run due assessments.
Project maintenance assesses the project's pinned baseline and retains links to the
previous assessment. Review source updates and explicitly migrate the baseline when
appropriate. This release does not automatically schedule runs or track certificate
expiry and renewal. Project stage checks remain advisory; they do not certify a system.

## Change management

The Change Register is the day-to-day entry point. Use **New change** to save a draft
with a title. Complete the component scope, planned versions and hashes, impact
assessment and schedule before approval. Details contains the full proposal, recorded
decisions and a readiness list for the next action. Desktop and mobile use the same
record and actions. Failed requests preserve entries; dismissing an unsaved editor
requires a discard decision, and navigation warns about unsaved changes.

Components, Baselines, Programme assurance and Reports support this workspace.
Record CIAA relevance as 1 (no relevance), 2 (some) or 3 (substantial); the highest
controls. Approval freezes the component identity, classification, version, checksum,
regulatory scope, responsibility and required assessments. Component reclassification
cannot weaken an approved change. Record the actual implemented versions and hashes;
deviations require revising and reapproving the scope.

Denmark uses **SCP.06.00.DK.3.1**, 18 March 2026 (checked 2 October 2026).
[The Danish programme](https://spillemyndigheden.dk/media/mmqn3qkz/scp0600dk31-program-for-styring-af-systemaendringer.pdf)
is authoritative; the [English version](https://spillemyndigheden.dk/media/xjoatyja/scp0600en31-change-management-programme.pdf)
supports the interface. CAP records external decisions and evidence; it does not
certify software, obtain authority approval, or submit reports.

- Internal change approval and accredited testing organisation (ATO) evaluation are
  separate decisions. Scope determines the relevant external checks.
- Code-3 RNG or game/game-platform changes require certification before implementation
  and use. They cannot use the quarterly deferral.
- Other code-3 changes require certification during or directly following implementation.
  Record the agreed timing and schedule. A maximum three-calendar-month postponement
  requires ATO permission and qualified QA organisationally separate from implementation,
  and is available to licensed operators or licensed game suppliers.
- Applicable code-2 changes require ATO evaluation approval; certification follows the
  evidenced annual cycle. Pending evaluation or an expired deadline is unresolved.
- RNG changes require five Danish working days of prior notification. Record whether
  game changes require authority approval and the decision or applicability basis.
  Identified or suspected errors require immediate notification. Emergency labels do
  not bypass these checks.
- Record supplier recommendations, the operator's whole-system evaluation and reasons
  for delay or rejection where applicable. Rejected recommendations require the ATO
  attestation specified in the programme.
- Complete relevant integration checks after implementation, under the annually
  ATO-approved procedure, with requirement references and evidence before verification.

Programme assurance holds the senior-management-approved change plan, responsible
personnel, accredited certification body, latest SCP.06 report, and regulator submission.
Certification is annual (twelve calendar months) and the report is due within two
calendar months. A programme renewal can be postponed by up to two months with prior
DGA notification; renewal and report share the extended deadline and the following
renewal retains the original cadence. This differs from a per-change quarterly deferral.
Use the authority's current Games register submission guidance outside CAP.

Create structured requirement impacts from approved versions or individual requirements,
optionally linked to a certification project. Assessments remain advisory unless explicitly
marked required before change completion. Their scope freezes with approval. Restricted
project links remain permission filtered. Inventory, history, integration and programme
exports retain evidence and frozen identifiers; deleted checks are excluded from active
results while their audit history remains available.

Existing records retain their status and history. Missing regulatory scope or evidence is
flagged rather than invented. Reject and reapprove an approved legacy proposal to establish
its scope. For already implemented historical records, a manager can record a one-time
scope attestation backed by contemporaneous evidence. This does not grant retrospective
approval. Record rollback outcome and follow-up; software recovery requiring a new
approved change must complete that workflow independently.

## Teams and personal work

Teams is a shared workspace destination. Only a team's owner can change membership,
and the owner is always included. Adding a member shares the resources already granted
to that team. Highly confidential resources continue to use named-person access.

Find assigned forms, authority queries and requirement assessments in Dashboard's
My work. Open an item to return to its application, project or change context.

## Returning to work

The Dashboard shows Recent Activity alongside everyday work. Events with a direct
workspace destination link to that item; child events without enough context
remain readable. This is activity across accessible work, not a browsing history.
Resources uses the sidebar for navigation, with page titles for each destination.
**Assessment overview** retains standalone and project assessments; normally open
an assessment from its project or linked change.

For Denmark, record the initial whole-platform certified component baseline and renew it annually, separately from the SCP.06 programme certificate. Supply its certification date, report reference, evidence and accredited testing organisation. Manual snapshots and legacy references remain comparisons with unresolved certification. Approved changes retain their baseline lineage; subsequent versions may differ. For new components outside that baseline, record the explicit baseline scope assessment before implementation.
