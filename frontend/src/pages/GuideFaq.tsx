import './workflow-pages.css'
import { useState } from 'react'
import { Link } from 'react-router-dom'

type QuickLink = {
  to: string
  label: string
}

type PlatformFlowStep = {
  id: string
  title: string
  detail: string
}

type FaqItem = {
  question: string
  answer: string
}

type ModuleSection = {
  id: string
  title: string
  summary: string
  keyActions: string[]
  links: QuickLink[]
  faqItems: FaqItem[]
}

const platformFlow: PlatformFlowStep[] = [
  { id: '1', title: 'Start with the work you need to do', detail: 'Choose Licence Applications for an application pack, Certifications for a test or audit engagement, or Change Management for a controlled change. These are separate journeys; you do not have to complete one to start another.' },
  { id: '2', title: 'Set up the contents, owners and access', detail: 'Choose the market and scope, add the required forms or approved requirement versions, and assign the work. Check sharing separately: naming an owner does not give them access.' },
  { id: '3', title: 'Complete, review and maintain the record', detail: 'Use the stage and next action in your workspace. Complete answers and evidence, obtain the appropriate internal decisions, and record external submissions or outcomes separately. Return to the same workspace for queries, reassessment and history.' },
]

const moduleSections: ModuleSection[] = [
  {
    id: 'licence-applications', title: 'Licence Applications',
    summary: 'Start a licence pack, complete its application forms and annexes, obtain internal approval and record submission and authority queries.',
    keyActions: [
      'Select the jurisdiction, choose New licence pack, then work through the creation view: Applicant and activities, Market questions, Proposed contents, then Owners and access. Confirm the proposed checklist before creating the pack.',
      'Use Overview for the stage, next action and sharing. New packs start Highly confidential; grant access to the people who will prepare, accept and approve the work.',
      'In Forms and documents, set up each application form or annex and attach supporting documents. You can include several application forms and a separate declaration for each relevant person. One form editor opens at a time.',
      'Create and attach a form in one save using manual questions, a saved blank form, a reviewed question import or an eligible existing form. Keep the original authority document with the form for reference.',
      'Complete the answers and evidence, wait for autosave to finish, then have the required answers explicitly accepted. Use Add another blank for another annex without copying personal answers or files.',
      'In Approval and submission, resolve blockers, request review and obtain internal pack approval. Download the approved version, submit through the authority’s channel, then record the submission date and reference.',
      'Manage authority queries and responses in the pack. Return to draft with a reason when revisions are needed, and obtain a new approval. History retains earlier decisions and versions.',
    ],
    links: [{ to: '/licence-applications', label: 'Licence Applications' }],
    faqItems: [
      { question: 'Do I need an approved requirement set to start an application?', answer: 'No. Licence preparation starts with the forms and documents you need. You may use reviewed draft requirement sources as form questions, with their source status visible. An approved baseline is required for certification requirement assessments.' },
      { question: 'What is the difference between a pack and a form?', answer: 'The pack organises one application: its forms, annexes, supporting documents, approval versions and authority correspondence. Each form holds its own questions, answers and evidence. A form can also be prepared independently and linked into an eligible pack later.' },
      { question: 'Can I prepare only annexes, or use several application forms?', answer: 'Yes. Review and adjust the proposed contents to the work you need. Existing annex-only and partial application packs remain usable. Include or exclude individual items explicitly; the checklist is a starting point, not a legal completeness decision.' },
      { question: 'How do I prepare Annex A for several people?', answer: 'Enter the people needing declarations during market setup, or add separate annex forms to the pack. Once an annex has questions, Add another blank copies those questions and source references. It does not copy answers, personal documents or attachments.' },
      { question: 'Will setup survive a refresh?', answer: 'Non-personal setup choices can be resumed in the same browser session. Applicant details, activities and personal names are kept only on the page until creation, so re-enter them after refreshing. A failed create request keeps the current entries for retry.' },
      { question: 'Does Ready mean the application is approved?', answer: 'No. Readiness checks required answers, their acceptance and supporting evidence. Form completion, answer acceptance, internal pack approval, recorded submission and an authority decision are separate steps.' },
      { question: 'Does CAP submit the application or issue the licence?', answer: 'No. Submit through the authority’s required channel yourself, then record what was sent, when and under which reference. Record the authority’s actual outcome and conditions separately. Internal approval is not a licence decision.' },
      { question: 'Will edits change an approved pack or its export?', answer: 'No. Approval freezes the pack version and its supporting files. Return to draft for corrections and obtain a new approval before recording a revised submission. Earlier approved versions and submission records remain available.' },
      { question: 'Can I download a completed authority PDF in its original layout?', answer: 'CAP exports readable records of the approved pack and its files. It does not automatically fill the authority’s original PDF or Word layout. Check the required submission format and transfer your reviewed answers where necessary.' },
    ],
  },
  {
    id: 'certification-projects', title: 'Certifications',
    summary: 'Organise a test or audit engagement around its scope, approved requirements, evidence, findings, provider reports and submission package.',
    keyActions: [
      'Create a project for the engagement, with a market, scope and owners. You can set it up and record the provider before the approved requirement baseline is ready.',
      'Use Overview for the stage and next action. In Requirements and evidence, select approved requirement versions to pin the baseline, then start or open the requirement assessment.',
      'Complete assessment items, evidence and supporting forms in Requirements and evidence. Choose Add form to create a project form; its editor opens separately. One engagement can cover several approved requirement sets.',
      'Use Testing and findings to record the lab or audit provider, engagement reference, system version, scope and test dates. Maintain milestones and follow links to assessment findings.',
      'In Reports and submission, record the provider report reference, issued date, outcome and link. Complete the submission package checklist, obtain internal approval and lock the package.',
      'Use History for previous results and maintenance. Review baseline changes explicitly; use a maintenance plan and Run due plans when you are ready to create the next assessments.',
    ],
    links: [{ to: '/certification-projects', label: 'Certifications' }, { to: '/program-workspace', label: 'Certification overview' }],
    faqItems: [
      { question: 'Can I set up a certification before requirements are approved?', answer: 'Yes. Prepare the engagement, provider, owners and milestones first. Before starting its requirement assessments, select the approved requirement versions that define the project baseline.' },
      { question: 'What is a pinned baseline?', answer: 'It is the exact set of approved requirement versions selected for the project. Source updates do not silently change the scope being assessed. Review the differences and choose an explicit migration when the project needs a new baseline.' },
      { question: 'Where are the forms, evidence and assessments?', answer: 'Open the project’s Requirements and evidence section. Supporting forms collect answers and documents; a requirement assessment records decisions against the pinned obligations. They serve different purposes and can be used together.' },
      { question: 'Does advancing the project stage mean we are certified?', answer: 'No. Stage and readiness checks help organise internal work and remain advisory. A completed assessment or approved submission package is not a laboratory result, audit opinion or authority decision.' },
      { question: 'How do I record the lab or audit result?', answer: 'Use Reports and submission to record the actual provider report reference, date, outcome and link. Keep the report distinct from CAP’s internal package approval and any external authority decision.' },
      { question: 'When should baseline migration be used?', answer: 'Use it after reviewing a scope change that should apply to the project. Preview the changed requirements and carry-forward or reset decisions before confirming. Frozen completed results and previously approved packages remain historical records.' },
      { question: 'Are periodic assessments created automatically?', answer: 'No. In History, add a maintenance plan with its cadence and first due date, then choose Run due plans to create due assessments. Project plans use the pinned project baseline and link to previous assessments. Pause or resume plans as needed.' },
      { question: 'Does CAP track certificate renewal or expiry automatically?', answer: 'There is no new automatic certificate renewal tracking or assessment scheduling in this release. Evidence validity dates are checked separately. Use the project’s milestones, history and manual maintenance plans to manage ongoing work.' },
    ],
  },
  {
    id: 'change-management', title: 'Change Management',
    summary: 'Work from the Change Register: save a draft, resolve readiness checks, and record approval, implementation and verification against a fixed component scope.',
    keyActions: [
      'Select or create a component register for the current jurisdiction. Maintain component inventory with CIAA classification, hosting, geographic location and checksum or hash details where applicable.',
      'Use New change to save a title-only draft. Add affected components, planned versions and hashes, impact evaluation and schedule before approval. Details shows the complete record and the next available action.',
      'In Requirement impact and assessments, add approved requirement versions or individual requirements, optionally with a certification project, and save the impacts.',
      'Select saved impacts and create a change assessment when reassessment is useful. Mark an assessment as required before change completion when it is a prerequisite; otherwise it remains advisory.',
      'For Denmark, record organisation responsibility and Programme assurance. SCP.06 version 3.1 separates internal approval, ATO evaluation and certification. Code-3 RNG/game changes need certification before implementation; other code-3 changes can use an agreed during/direct-continuation schedule or qualified ATO-approved quarterly deferral. Record actual component versions and notifications, then complete post-implementation integration checks.',
      'Record the initial whole-platform certified baseline and renew it annually for Denmark. Keep manual comparison snapshots separate, compare changes and retain verification history. Use Reports for inventory and change reporting.',
    ],
    links: [{ to: '/change-management', label: 'Change Management' }],
    faqItems: [
      { question: 'What is the difference between the Component Register and the Change Register?', answer: 'The Component Register describes the systems and components in scope. The Change Register records proposed modifications, decisions, implementation and verification of those components.' },
      { question: 'What does a change assessment cover?', answer: 'It covers the approved versions or individual requirements selected from the saved impact links. Project context is retained; separate project contexts produce separate assessments. Selecting a few requirements does not imply assessment of the whole project.' },
      { question: 'Must the linked assessment be completed before change verification?', answer: 'Linked assessments remain advisory unless a manager explicitly marks them required before change completion. Required assessments must resolve their compliance decisions and evidence before the change can progress; their pinned scope is retained.' },
      { question: 'Why can’t I see a project linked to a change?', answer: 'Project access is checked separately. A visible change does not reveal restricted project details or grant access to its assessments. Updating the impacts you can see preserves hidden links you cannot access.' },
      { question: 'When should we create a component baseline?', answer: 'For Denmark, record a whole-platform certified baseline before implementation, with its date, report, evidence and accredited testing organisation, and renew it annually. Manual snapshots are useful at other checkpoints but do not establish certification. Baseline comparisons show changes without approving them.' },
    ],
  },
  {
    id: 'overview', title: 'Dashboard and finding your work',
    summary: 'Use My work for your assignments and the workspace’s next action to continue the right task.',
    keyActions: [
      'Choose the jurisdiction before working on its packs, certification projects, requirements or change registers.',
      'Open assigned forms, authority queries and requirement assessments from Dashboard’s My work. Links return you to the relevant pack, project or assessment item.',
      'Use Resources in the top navigation to open requirements, form templates, evidence and existing forms. The current resource is highlighted. Use Find a page to search navigation, including secondary Resources pages. On a small screen, open the menu to change jurisdiction or workspace.',
      'Use the certification overview for project readiness and blockers. Check the individual project before making a stage or package decision.',
    ],
    links: [{ to: '/', label: 'Dashboard' }, { to: '/program-workspace', label: 'Certification overview' }],
    faqItems: [
      { question: 'Why is work missing from my dashboard or search?', answer: 'Results depend on your organisation, assignments, jurisdiction filters and access. Being named as an owner does not grant access. Ask the work’s access owner to check sharing if an expected item is missing.' },
      { question: 'Is a dashboard snapshot the same as an approved pack or assessment?', answer: 'No. Manual dashboard snapshots summarise current approved requirements across your organisation. Each completed assessment and approved pack or package has its own separate frozen record.' },
    ],
  },
  {
    id: 'market-setup', title: 'Markets and proposed pack contents',
    summary: 'Denmark and Finland have published starter checklists. Confirm the proposed contents for each application; existing packs keep their original configuration.',
    keyActions: [
      'For Denmark, review the proposed main application, repeated Annex A declarations, Annex B, conditional representative form and supporting documents. Use the linked authority instructions to confirm the people and contents needed.',
      'For Finland, answer the domestic or foreign applicant and responsible-person questions so the wizard can propose the relevant conditional attachments. Keep licence preparation separate from operational audit readiness.',
      'For Sweden, prepare a custom blank pack while the built-in market checklist remains unpublished.',
      'Managers and organisation administrators use Market setup to review and maintain profile versions, source references and submission guidance. Check configuration changes before publishing.',
    ],
    links: [{ to: '/market-setup', label: 'Market setup' }],
    faqItems: [
      { question: 'Does the market checklist prove the application is complete?', answer: 'No. It proposes contents based on the saved profile and your setup answers. Review the current authority instructions and confirm the checklist for the particular application. A checklist is not a legal or regulatory determination.' },
      { question: 'Will a market profile update change packs already in progress?', answer: 'No. Each pack retains its original profile version, setup answers and checklist. Later published configuration applies to future packs; changes to an existing pack require an explicit review.' },
      { question: 'Why are licence preparation and testing guidance separate?', answer: 'Forms and supporting documents prepare the licence application. Technical testing, certification and audits are handled in their own engagement. Denmark’s starter guidance covers certification before licence issue; Finland’s covers audits and integrations before operation. Check the linked market sources for the applicable timing. These are guidance, not CAP stage gates or an authority decision.' },
    ],
  },
  {
    id: 'requirements', title: 'Shared requirements',
    summary: 'Requirements describe obligations. Maintain their source versions here, then use approved versions for certification or reviewed source questions for a form.',
    keyActions: [
      'Open Requirements under Resources, from a project or through Find a page. Create a manual draft or import a source PDF, then review the extraction and original references.',
      'Use Show levels at the top of the outline to browse only the top level, two or more levels, or the full hierarchy. Search and filters keep your depth choice and the original hierarchy. Your browser remembers the choice; focused editing keeps the selected requirement open.',
      'Approve a requirement version before selecting it as a certification assessment baseline. Preserve draft warnings when using source wording to prepare licence form questions.',
      'Use the contextual actions Use in a certification project or Use as form questions. Confirm the selected scope and question wording before saving.',
      'Create a new version for an updated source in the same lineage. Archive obsolete sources without removing their historical links.',
    ],
    links: [{ to: '/requirements', label: 'Requirements' }],
    faqItems: [
      { question: 'Are requirements only for certifications?', answer: 'Approved requirements define certification assessment obligations. Their source wording can also help prepare licence form questions, including reviewed draft sources. You do not need to approve a requirement set simply to prepare an application form.' },
      { question: 'Should we create a new requirement set or a new version?', answer: 'Use a new version for an update to the same source lineage. Create a separate set when the source or scope should be tracked independently. Projects keep their selected versions until you explicitly change the baseline.' },
      { question: 'Who approves requirement sets?', answer: 'A designated approver or administrator with the necessary access checks the source and scope before approval. Extracted or AI-suggested content still requires human review.' },
      { question: 'What happens when a source is archived?', answer: 'It is removed from active choices while retained historical references remain available to authorised users. Archiving does not rewrite a completed assessment or an approved pack.' },
    ],
  },
  {
    id: 'resources', title: 'Blank forms, imports and existing forms',
    summary: 'A saved blank form defines questions. A completed form contains answers and evidence. Reuse them deliberately from the work you are preparing.',
    keyActions: [
      'Start in your pack’s Forms and documents or the project’s Requirements and evidence. Add manual questions, use a saved blank form, import reviewed questions or link an eligible existing form.',
      'Use Form templates under Resources when you want to maintain questions for repeated use. Illustrative starters help organise a form; replace example wording with the questions you actually need.',
      'Review spreadsheet headings and mappings before adding questions. Use imported requirements to select source wording and retain references. Retain an original PDF or other document for reference rather than assuming an upload creates a reviewed form.',
      'Open the collapsed Existing forms section in Licence Applications, or Resources → Existing forms, to find earlier and independently prepared forms. Existing links and saved answers are preserved.',
      'Use explicit answer reuse where questions have matching reuse keys. Review the source, evidence access and suitability, then obtain fresh acceptance in the destination form.',
    ],
    links: [{ to: '/library?section=templates', label: 'Form templates' }, { to: '/library?section=forms', label: 'Existing forms' }],
    faqItems: [
      { question: 'What is the difference between requirements, templates and completed forms?', answer: 'Requirements describe obligations or source questions. A template is a reusable blank question definition. A completed form holds answers and evidence for particular work. Sharing a blank definition does not copy private answers or attachments.' },
      { question: 'Do I have to start in the Library or create a template first?', answer: 'No. Start with a licence pack or certification project and create its form directly. Resources holds reusable material and existing forms when you need them; it is not another required workflow.' },
      { question: 'Do edits to a saved blank form change forms already in progress?', answer: 'No. Each form keeps the questions and source version copied when it was created. Later template edits apply to new forms. Repeating an annex copies blank questions, not the earlier person’s answers or files.' },
      { question: 'Can I reuse an answer in another application or jurisdiction?', answer: 'When matching reuse keys and access make the source eligible, explicitly select the answer to reuse. CAP retains the source and copies the answer and evidence references, not its acceptance or approval. Check that the information and evidence remain appropriate for the new question and market.' },
      { question: 'Is Jev required for question imports or requirements extraction?', answer: 'No. Normal imports and manual preparation work without Jev. When an enabled Jev preview check is offered, confirm external processing first, then review its suggestions for missing metadata or mappings. Question preview checks exclude applicant answers and unused columns. Suggestions do not approve requirements or accept answers.' },
    ],
  },
  {
    id: 'evidence', title: 'Answers, evidence and saving your work',
    summary: 'Complete and save answers, check supporting evidence, then explicitly accept the responses needed for readiness.',
    keyActions: [
      'Watch the save status when completing a form. Wait for pending saves before accepting answers, requesting approval or leaving the page.',
      'Attach uploaded files, links or notes to the relevant answer or assessment. Keep originals and supporting documents with the work they belong to.',
      'Have required answers reviewed and accepted by an authorised manager or administrator. Give a reason when marking a question not applicable; that response still needs acceptance.',
      'Replace expired or outdated evidence with a new item and update the affected responses. Recheck readiness after meaningful answer or evidence changes.',
      'For failed saves, keep the page open and retry. If another person has changed the form, compare the latest saved answers with your draft before choosing how to continue.',
    ],
    links: [{ to: '/library?section=evidence', label: 'Evidence library' }],
    faqItems: [
      { question: 'Are answers saved automatically?', answer: 'Yes. Form answers save after a short pause or when you leave a field, with a visible save status. Acceptance, sharing, imported-question confirmation, approval and submission actions are explicit. Keep the form open until saves finish.' },
      { question: 'Why did an accepted answer need review again?', answer: 'A meaningful answer change clears its previous acceptance. The changed response must be checked and accepted again. An unchanged save does not reset acceptance, and prior approved exports remain unchanged.' },
      { question: 'What can prevent evidence readiness?', answer: 'Missing, future-dated, expired or archived evidence, inaccessible attachments, and failed file integrity checks can block readiness. Check the visible reasons on the form or pack. Valid-until dates are inclusive UTC calendar dates.' },
      { question: 'Does adding a web link preserve the document?', answer: 'No. A link records a reference; CAP does not fetch or verify its contents. Upload the file when you need to preserve its bytes for review and historical export.' },
      { question: 'What should I do after a save conflict or failed upload?', answer: 'Keep your draft open. Retry a failed request, or reload and compare the latest saved version when another person has edited the work. Do not assume that a visible draft or selected file has been saved. CAP warns before leaving with unsaved changes.' },
      { question: 'Can I edit evidence that is already in an approved record?', answer: 'Replace the evidence with a new item for current work, rather than overwriting its content or validity. Frozen approved records retain their original files. Archiving old evidence does not remove that history.' },
    ],
  },
  {
    id: 'reviews', title: 'Requirement assessments',
    summary: 'Assess evidence against an exact requirement scope, resolve findings and comments, then complete the assessment while retaining its results.',
    keyActions: [
      'Normally open the assessment from its certification project or linked change. The Assessment overview under Resources also retains standalone assessments.',
      'Assign items, record decisions and rationale, and attach evidence against the locked requirement versions. Resolve the visible completion blockers before completing the assessment.',
      'Use Show levels at the top of the outline to control the outline and document view. Filters keep the chosen levels; increase the depth to show deeper matches. Expand a branch for detail; bulk actions apply only to visible rows. The depth setting does not change the assessment scope or completion rules.',
      'Use comments for questions and discussion. Mention colleagues when their input is needed, and attach supporting files to the relevant comment instead of relying only on a link.',
      'Complete the assessment to freeze its result. Use the overview’s project and change filters to find related work, and open previous results from their history links.',
    ],
    links: [{ to: '/review-cycles', label: 'Requirement assessments' }],
    faqItems: [
      { question: 'What happened to Reviews?', answer: 'That work is now called Requirement assessments. Existing assessment records and review links still work. Answer acceptance, internal application approval, requirement assessment and change verification remain separate decisions.' },
      { question: 'When should we create a new requirement assessment?', answer: 'Create one for a new submission milestone, a selected change impact or a periodic control check. Use the project or change context when applicable; standalone assessments remain available for other preparation and review work.' },
      { question: 'What happens if requirement sets are updated after an assessment is created?', answer: 'The assessment keeps its locked versions. Review new scope through a subsequent assessment or an explicit project baseline migration. Updating a source does not silently replace frozen completed results.' },
      { question: 'What do active, closed and archived mean?', answer: 'Active work is in progress. Closed assessments retain the completed result and its frozen history. Archived assessments are retained for reference but removed from the active queue. These statuses do not record an external certification or licence outcome.' },
      { question: 'Will mentioning someone send them an email?', answer: 'Mention emails depend on the installation’s email configuration and the recipient’s notification settings. Select a colleague who can access the work; a mention does not grant access. A sent email links to the relevant assessment comment. Turning off email does not remove the comment or assignment.' },
    ],
  },
  {
    id: 'access-teams', title: 'Teams and sharing',
    summary: 'Share work deliberately with named people or an owner-managed team. Work assignment and permission to access it are separate.',
    keyActions: [
      'Open Teams from the workspace navigation or the sharing controls on an application. Select a team to open its editor; only one team editor is open at a time.',
      'The team owner manages membership and remains selected. Search the scrolling member checklist, check the selected-member count, then choose Save or Cancel. Filtering does not clear existing selections.',
      'In the work’s sharing controls, choose people or eligible teams and the view, edit, approval and export permissions they need. Save sharing explicitly.',
      'Use named-person access for Highly confidential work. Review existing team grants before adding a new member, because membership changes can grant access to work already shared with that team.',
    ],
    links: [{ to: '/access-teams', label: 'Teams' }],
    faqItems: [
      { question: 'Does assigning an owner give them access?', answer: 'No. A work owner identifies responsibility. The access owner controls sharing. Grant the required permissions separately to owners, contributors and approvers; a role alone does not bypass confidential access.' },
      { question: 'What do Organisation, Restricted and Highly confidential mean?', answer: 'Organisation follows organisation-wide roles. Restricted uses explicit people or eligible team grants. Highly confidential uses its access owner and named people only, so team membership cannot reveal that material. New licence packs start Highly confidential; existing records retain their saved access settings.' },
      { question: 'Who can change a team’s membership?', answer: 'Only its owner can edit membership, and the owner cannot be removed from their own team. Being an account administrator does not let someone edit another owner’s team.' },
      { question: 'Can someone see the pack summary without its personal answers?', answer: 'A separately granted application summary provides limited oversight information. It does not provide answers, attachments, authority correspondence or approved pack files. Give full resource permissions only where needed.' },
      { question: 'What happens when access or team membership changes?', answer: 'CAP refreshes access and clears earlier interface state. Revocation blocks subsequent authorised requests, but cannot recall material already read, downloaded or emailed. Resolve a conflicting team edit against the latest saved membership before saving again.' },
    ],
  },
  {
    id: 'reports', title: 'Reports and exports',
    summary: 'Export the record that matches the work: an approved licence pack, a certification package, an assessment result, a form or a change report.',
    keyActions: [
      'Download the approved licence version from its Approval and submission section. Prepare and lock certification packages in Reports and submission within the project.',
      'Use Reports → Assessment reports for an assessment’s reports and evidence outputs. Check the selected jurisdiction and assessment before exporting.',
      'Use Reports → Change management for component and change reporting, and Audit trail for permitted activity exports.',
      'Export an individual form when a point-in-time answer and evidence record is useful. Review the included readiness and source details before handing it over.',
    ],
    links: [{ to: '/reports', label: 'Reports' }],
    faqItems: [
      { question: 'Does an export approve work or submit it?', answer: 'No. A form export can include incomplete work with its readiness recorded. Approved pack exports use the frozen approved version. Exporting does not accept answers, approve a package, send an application or record an external outcome.' },
      { question: 'Why can’t I download or export a record?', answer: 'Your role and resource permissions must allow export, and required evidence must remain accessible and pass integrity checks. Read the displayed blocker or ask the access owner to check the grant; assignment and viewing rights alone are not export permission.' },
      { question: 'Can later edits change an old approved export?', answer: 'No. Approved packs and locked submission packages retain their versions and files. Export the appropriate historical version when you need to show what was approved or sent at that time.' },
    ],
  },
  {
    id: 'account', title: 'Your account and notifications',
    summary: 'Use the profile menu for your name, password, email preferences, appearance and logout.',
    keyActions: [
      'Open Profile options using your name or initials, then choose Account settings. Save a full-name change explicitly; contact an administrator for a sign-in email or role change.',
      'To change your password, enter the current password, a new password of at least eight characters, and its confirmation. Other sessions are signed out; the current browser remains signed in.',
      'Choose Notification settings to enable or disable mention emails and manager-sent assessment reminders, then save. Preferences apply across devices.',
      'Use Appearance for light, dark or system theme, and Logout when you finish. Appearance choices do not change other users’ settings.',
    ],
    links: [{ to: '/account?section=account', label: 'Account settings' }, { to: '/account?section=notifications', label: 'Notification settings' }],
    faqItems: [
      { question: 'Why did an email not arrive?', answer: 'Check that the relevant notification preference is enabled and saved, and that the installation is configured to send email. Muted emails do not cancel your assignments or remove comments. Ask the installation operator about email delivery if needed.' },
      { question: 'Are notification settings the same as automatic scheduling?', answer: 'No. They control whether you receive supported review emails. Assessment reminders are sent by a manager, and maintenance assessments are created with Run due plans; saving email preferences does not schedule either action.' },
      { question: 'Can I change another person’s account from my profile menu?', answer: 'No. My account changes only your own profile, password and email preferences. Account administration and access to confidential work have separate permissions.' },
    ],
  },
  {
    id: 'administration', title: 'Roles and administration',
    summary: 'Organisation administration, content access and installation operations are separate responsibilities.',
    keyActions: [
      'Managers organise work and, with the required resource permission, accept form answers. Contributors complete assigned answers and evidence. Approvers and administrators approve licence packs within their access.',
      'Use User Management to maintain local accounts and roles. Deactivate an account to remove access while retaining its historical attribution.',
      'Managers and organisation administrators maintain market profiles and reusable blank forms. Installation operators handle installation-wide email, optional Jev, backups and external integrations.',
    ],
    links: [],
    faqItems: [
      { question: 'Why can’t an administrator open confidential work or configure every setting?', answer: 'An account role does not grant access to Restricted or Highly confidential resources. Their access owners control sharing. Installation operations such as backups and external credentials also require designated installation-operator permission.' },
      { question: 'What happens when an account is deactivated?', answer: 'Access is revoked and historical attribution is retained. Deactivation does not delete that person’s compliance records, decisions or evidence.' },
      { question: 'Who enables Jev or email delivery?', answer: 'The designated installation operator manages installation settings and external credentials. Users still review suggested content and explicitly confirm supported external preview processing. Disabled or unavailable Jev leaves normal preparation available.' },
    ],
  },
]

export default function GuideFaq() {
  const [search, setSearch] = useState('')
  const query = search.trim().toLowerCase()
  const visibleSections = moduleSections.filter((section) => !query || [section.title, section.summary, ...section.keyActions, ...section.faqItems.flatMap((item) => [item.question, item.answer])].join(' ').toLowerCase().includes(query))
  return (
    <div className="workflow-page guide-page min-w-0 space-y-4">
      <header className="py-1">
        <h1 className="text-2xl font-bold text-ink">User Guide & FAQ</h1>
        <p className="mt-3 max-w-3xl text-sm text-muted">
          Choose the work you need to do, follow its workspace sections, or search for a question. The guidance below covers setup, completion, approval and ongoing work.
        </p>
        <label className="mt-5 block max-w-xl text-sm font-medium">Search the guide<input type="search" className="mt-2 w-full px-3 py-2" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Annex A, baseline, evidence, Jev, sharing…" /></label>
        {query && <p role="status" className="mt-2 text-sm text-muted">{visibleSections.length} matching {visibleSections.length === 1 ? 'section' : 'sections'}</p>}
      </header>

      {!query && <nav aria-label="Main workflows" className="grid gap-3 sm:grid-cols-3">
        {[{ to: '/licence-applications', label: 'Licence Applications', detail: 'Prepare forms and documents in a licence pack.' }, { to: '/certification-projects', label: 'Certifications', detail: 'Prepare and maintain a test or audit engagement.' }, { to: '/change-management', label: 'Change Management', detail: 'Approve, implement and verify controlled changes.' }].map((item) => <Link key={item.to} to={item.to} className="min-w-0 rounded-xl border border-line bg-surface p-4 hover:bg-canvas focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"><span className="font-semibold text-accent">{item.label}</span><span className="mt-2 block text-sm text-muted">{item.detail}</span></Link>)}
      </nav>}

      <details hidden={!!query} className="rounded-xl border border-line bg-surface p-4">
        <summary className="cursor-pointer font-semibold">Start here</summary>
        <ol className="mt-4 space-y-4">
          {platformFlow.map((step) => (
            <li key={step.id} className="py-2">
              <div className="flex items-start gap-3">
                <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand text-xs font-semibold text-white">
                  {step.id}
                </span>
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold text-ink">{step.title}</h3>
                  <p className="mt-1 text-sm text-muted">{step.detail}</p>
                </div>
              </div>
            </li>
          ))}
        </ol>
      </details>

      <h2 className="text-lg font-semibold">Workflows and help topics</h2>
      {query && !visibleSections.length && <p className="rounded-xl border border-line p-5 text-sm text-muted">No guidance matches this search. Try “annex”, “assessment” or “evidence”. <button className="underline" onClick={() => setSearch('')}>Clear search</button></p>}
      {visibleSections.map((section) => (
        <details
          open={!!query}
          id={section.id}
          key={section.id}
          className="rounded-xl border border-line bg-surface p-4 scroll-mt-24"
        >
          <summary className="cursor-pointer font-semibold text-ink">
            <h2 className="inline text-base">{section.title}</h2>
            <p className="mt-1 text-sm font-normal text-muted">{section.summary}</p>
          </summary>
          <div className="mt-4">
            <div className="flex flex-wrap gap-2">
              {section.links.map((link) => (
                <Link
                  key={`${section.id}-${link.to}-${link.label}`}
                  to={link.to}
                  className="rounded-md border border-line-strong px-2.5 py-1.5 text-xs font-medium text-ink hover:bg-canvas"
                >
                  Open {link.label}
                </Link>
              ))}
            </div>
          </div>

          <div className="mt-5 grid gap-6 md:grid-cols-2">
            <div>
              <h3 className="text-sm font-semibold text-ink">What to do</h3>
              <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-muted">
                {section.keyActions.map((action) => (
                  <li key={action}>{action}</li>
                ))}
              </ul>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-ink">FAQ</h3>
              <div className="mt-3 space-y-3">
                {section.faqItems.map((item) => (
                  <details key={item.question} open={!!query && [item.question, item.answer].join(" ").toLowerCase().includes(query)} className="border-t border-line py-3">
                    <summary className="cursor-pointer text-sm font-medium text-ink">
                      {item.question}
                    </summary>
                    <p className="mt-2 text-sm text-muted">{item.answer}</p>
                  </details>
                ))}
              </div>
            </div>
          </div>
        </details>
      ))}
    </div>
  )
}
