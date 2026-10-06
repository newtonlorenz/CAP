# Danish change management: regulatory and workflow review

Online checked: **2 October 2026**. Controlling source:
[SCP.06.00.DK.3.1, 18 March 2026](https://spillemyndigheden.dk/media/mmqn3qkz/scp0600dk31-program-for-styring-af-systemaendringer.pdf).
The [English 3.1 document](https://spillemyndigheden.dk/media/xjoatyja/scp0600en31-change-management-programme.pdf)
was cross-checked with Danish text. The authority's PDF page metadata still mentions
3.0; the document cover and version history identify 3.1.

## Verdict and boundary

**Allowed with controls; high confidence in the identified software gaps.** The
pre-change CAP workflow could not substantiate compliance with the current programme.
Its UI suggested a complete lifecycle, but implementation checked internal approval
without enforcing several external prerequisites. This review concerns an internal
compliance workspace for Danish licensed betting/casino operators and game suppliers,
including outsourced base-platform work. CAP stores decisions and evidence; no player
transaction or gaming system is deployed by a CAP workflow action.

These changes improve evidence capture and progression controls. They do not constitute
DGA or ATO approval of CAP, an operator's change-management plan, or any individual
system change. Responsible personnel must enter genuine external decisions, scope and
references. No actor-separation policy is presented as a universal statutory rule.

## Evidence before the repair

Read-only live review covered Denmark's existing component register and draft change,
all four workspace sections, the full proposal and details, desktop, 390px and 320px,
light/dark themes, keyboard interaction and accessible names. No real work records were
changed. Two independent UI assessments agreed on missing proposal context, scattered
actions and excess form burden. The deterministic design detector returned zero
findings; manual findings remained valid. Baseline usability score: 20/40 across the
ten Nielsen heuristics. Positive findings: stable deep links, CIAA-derived relevance,
permission-filtered project scope and pinned requirements.

Disposable endpoint probes demonstrated:

1. An approved high-relevance change could be implemented with no evidenced ATO release
   decision. Testing validation ran only at verification.
2. Downgrading a linked component's current CIAA values could bypass its original
   testing obligation because verification read current inventory instead of approved scope.
3. A pending code-2 evaluation with an annual deadline in 2000 could still be verified.

Other confirmed gaps: weak version binding; absent regulatory and supplier decisions;
no programme-renewal evidence; mutable identifiers in historical exports; deleted checks
included as active integration results; unsaved proposal loss on navigation; details
omitting the proposal and decisions; workflow actions failing to name their target;
and mobile actions hidden beyond a horizontally scrolling list.

## Direct requirements and implementation

| Source | Required behaviour | CAP control |
|---|---|---|
| SCP.06 3.1–3.2 | Responsible operator/supplier and an approved documented change plan | Register responsibility and Programme assurance hold personnel, senior-management approval, evidence and accreditation |
| 3.3–3.5 | Component inventory, CIAA relevance, checksums, geographical records, baselines and dated history | Explicit regulatory scope; frozen proposal identity/classification/version/hash; evidenced baseline reference; observed implementation versions; full metadata audit |
| 4.1–4.3 | Describe/evaluate changes and retain formal internal approval | Title-only drafts; complete evaluation before approval; approval target and original scope preserved |
| 4.3.1 | Whole-system operator assessment of applicable supplier recommendations; justified delay/rejection and individual ATO rejection attestation | Structured recommendation, evaluation, delay and rejection evidence, applied to its Danish responsibility/scope |
| 4.4.1 | ATO evaluation for code 3; RNG/game certification before implementation/use; other code-3 timing and conditional postponement | Readiness and HTTP transition gates; version/hash-bound certification; explicit during/direct-continuation evidence or licensed-party independent qualified QA with ATO permission and max three calendar months |
| 4.4.2 | Applicable code-2 ATO evaluation and annual certification | Pending evaluations block progression; separately evidenced annual certification anchor and deadline, independent from SCP.06 programme renewal |
| 4.4–4.5 | Verify approved versus actual change and post-implementation integration under an annually ATO-approved procedure | Explicit observed versions/hashes; checks occur after actual implementation, retain references/evidence, and exclude deleted checks from active outcomes |
| 5 | Export inventory, history, locations, period verification and integration evidence | Frozen historical identifiers, certification/notification evidence and programme assurance exports |
| 6–6.2 | Immediate error notification, five working days' RNG notice and applicable prior game approval | Actual notification dates/references, explicit immediacy attestation, Copenhagen working-day calendar and recorded approval applicability/basis |
| 2.1 | Annual SCP.06, report within two months; qualified programme postponement preserves original cadence | Calendar-month deadlines, prior-notice evidence, max two-month programme postponement, renewed report deadline and original cadence retained |

Source references above are to **SCP.06.00.DK.3.1**, PDF pp. 2–21
(printed pp. 1–20); individual section numbers identify the precise rule.
The [March update notice](https://spillemyndigheden.dk/en-us/news-articles/updated-certification-program)
confirms the code-3 timing distinction. The current
[operator certification table](https://spillemyndigheden.dk/en-us/businesses-and-associations/games-which-require-a-licence/betting/certification-programme)
identifies Games register submission and the SCP.06 report deadline. CAP directs users
to the authority rather than claiming to submit on their behalf. Relevant current Danish
legal framework and technical requirements were checked; the detailed workflow rules
above derive from SCP.06, not an invented statutory requirement.

## Product interpretations and acceptance criteria

These are software controls chosen to implement the source requirements, rather than
verbatim legal obligations:

- Freeze approved scope to prevent reclassification or mutable inventory weakening a
  decision. A stale component baseline requires revision and reapproval.
- Keep optional requirement assessments advisory. An explicitly designated prerequisite
  must have resolved compliance decisions and evidence; its scope freezes at approval.
- Keep missing historical attestations unresolved. Existing records/statuses survive the
  additive migration. An approved legacy proposal is rejected/reapproved to establish
  scope; an implemented/verified legacy record can receive a one-time evidenced scope
  attestation without inventing retrospective approval.
- Record internally verified changes separately from outstanding annual/deferred
  certification. Managers can append evidenced certification completion while retaining
  the original evaluation, approval and implementation attestations.
- Record a rollback's observations, outcome and follow-up. CAP does not silently deploy
  recovery software or bypass a separately required approved recovery change.
- Use progressive disclosure, a focused editor, named action dialogs and a complete
  read-only record. Preserve failed requests and confirm unsaved dismissal/navigation.
  Mobile exposes the same primary actions without horizontal exploration of the register.

Acceptance is demonstrated at HTTP decision boundaries, real navigation boundaries,
CSV exports and populated browser workflows. Negative release tests satisfy independent
prerequisites before asserting the intended rejection; positive paths cover lawful
certification timing and supplementing a verified record. Fresh PostgreSQL migration,
existing-data continuity, role/access restrictions, frontend tests, lint/build and full
repository Verify are release gates. Browser success alone is not regulatory approval.

## Audit and delivery evidence

Workflow audit events retain proposal/approval scope, observed component changes,
external attestations and their updates, notification references, integration amendments,
historical scope attestation and rollback observations. Evidence references point to
operator-controlled documents; CAP does not authenticate an ATO signature merely from
entered text. Monitoring deadlines supports work prioritisation; notifications and
regulator submission are operational actions outside this change.

Private live snapshots, authentication material, source PDFs, runtime fingerprints,
backups and detailed test logs are excluded from the public source snapshot. Release
results must separately report local checks, PR/merge, deployed source/schema revision
and post-deployment health and data continuity. A fresh quiesced backup and retained
previous application images provide recovery while preserving database, uploads and
unrelated applications.
