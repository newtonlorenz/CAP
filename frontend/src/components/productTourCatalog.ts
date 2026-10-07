/** Static orientation: tours explain the work without changing records or navigating. */
export type ProductTourStep = { target?: string; title: string; description: string }
export type ProductTourDefinition = { id: string; title: string; summary: string; steps: ProductTourStep[] }

type Guidance = readonly [title: string, description: string, target?: string]
const anchor = (name: string) => `[data-tour="${name}"]`
const surface = (...names: string[]) => names.map(anchor).join(', ')
const nav = (label: string) => `nav[aria-label="${label}"]`
const make = (id: string, title: string, summary: string, guidance: readonly Guidance[]): ProductTourDefinition => ({
  id, title, summary, steps: guidance.map(([stepTitle, description, target]) => ({ title: stepTitle, description, ...(target ? { target } : {}) })),
})
const primary = (name: string) => `[data-testid="primary-nav"] ${anchor(name)}`

export const PRODUCT_OVERVIEW_TOUR = make('overview', 'CAP overview', 'Understand how compliance work moves from obligations to evidence and recorded decisions.', [
  ['Start with your work', 'My work brings together assigned forms, assessment items, and authority queries. Open an item to continue its workflow.', primary('overview')],
  ['Prepare licence applications', 'Organize forms and documents, obtain internal approval, and record submission through the authority’s own channel.', primary('licences')],
  ['Coordinate certifications', 'Agree the project scope, assess the selected requirements, record testing, and prepare a reviewed submission package.', primary('certifications')],
  ['Control changes', 'Connect proposed changes to affected components, assessments, approvals, and release evidence.', primary('changes')],
  ['Start from requirements', 'Requirements describe the obligations you need to assess. Check their source and use approved versions for certification assessments.', primary('requirements')],
  ['Make evidence-based decisions', 'Contributors explain the assessment and provide evidence. Reviewers record a separate decision against the selected requirement versions.', primary('assessment')],
  ['Reuse supporting materials', 'Resources holds blank form templates, existing forms, and evidence. Shared materials support work; they do not establish acceptance.', primary('evidence')],
  ['Retain the recorded outcome', 'Reports bring together recorded work and evidence. Internal readiness and approval remain distinct from a provider’s or authority’s decision.', primary('reports')],
])

const work = make('work', 'Work overview', 'Find the next action and understand who needs to do it.', [
  ['Begin with assigned work', 'Use My work for your assignments. Team work and Programmes provide broader views when your role has access.', nav('Overview views')],
  ['Find what needs attention', 'Look for unresolved work, overdue dates, or missing owners. Choose the relevant work type before opening an item.', `${anchor('my-work')}, section[aria-label="Team work queue"], section[aria-label="Certification programme readiness"]`],
  ['Continue in its workspace', 'Open the item to work on its form, requirement, assessment, or authority query. The linked pack or project supplies context.'],
  ['Follow the handoff', 'Preparing an answer or assessment can still require a reviewer’s decision. Check the next action and its owner before treating work as complete.'],
  ['Use readiness as a guide', 'Programme readiness identifies outstanding preparation checks. It does not establish regulatory approval.', `section[aria-label="Certification programme readiness"], ${anchor('work-insights')}`],
])
const packSection = `${nav('Licence pack sections')}, ${surface('licence-list', 'licence-create')}`
const licences = make('licences', 'Licence applications', 'Prepare a coherent pack and keep internal review separate from the authority’s decision.', [
  ['Understand the pack', 'A licence pack organizes the forms and supporting documents for an application. Its stage tracks preparation, review, submission, and follow-up.', surface('licence-heading', 'licence-list', 'licence-create')],
  ['Agree scope and responsibility', 'Confirm the market, applicant, scope, owner, and deadline before starting. Where a proposed checklist exists, verify it against authority instructions.', surface('licence-metadata', 'licence-list', 'licence-create')],
  ['Prepare forms and evidence', 'Complete the included forms and attach relevant evidence. Sweden starts a blank custom pack; add its required contents after creation.', `${surface('licence-components', 'licence-create')}, ${nav('Licence pack sections')}`],
  ['Obtain internal approval', 'Resolve readiness issues and obtain reviewer acceptance for required answers. An authorized approver then approves a preserved pack version.', `${surface('licence-readiness', 'licence-list')}, ${nav('Licence pack sections')}`],
  ['Record actual submission', 'Download the approved version and submit through the authority’s channel. Record the actual date and reference after submission.', `${surface('licence-snapshots', 'licence-list')}, ${nav('Licence pack sections')}`],
  ['Follow up and retain the outcome', 'Assign and resolve authority queries, then record the actual decision and conditions. Completing the record does not mean a licence was issued.', `${surface('licence-queries', 'licence-history')}, ${packSection}`],
])
const projectSection = `${nav('Project sections')}, ${anchor('certification-list')}`
const certifications = make('certifications', 'Certifications', 'Coordinate requirements, assessment, testing, and a controlled submission package.', [
  ['Start with the project scope', 'Agree what needs certification, the jurisdiction, provider, owner, and target date. The project brings that preparation work together.', surface('certification-heading', 'certification-list')],
  ['Keep the selected requirements fixed', 'Choose approved requirement sets. Each assessment retains its selected versions, so later source changes do not silently change the work under review.', `${anchor('certification-baseline')}, ${projectSection}`],
  ['Assess evidence against obligations', 'Contributors assess the requirements and provide evidence. Reviewers make separate decisions; unresolved gaps remain work to complete.', `${anchor('certification-assessments')}, ${projectSection}`],
  ['Address testing and findings', 'Record the provider engagement and resolve findings in the linked assessment. Retain the actual provider report and result when available.', `${anchor('certification-testing')}, ${projectSection}`],
  ['Prepare a reviewed package', 'Complete the assessment and required documents before package review. The package preserves the assessment snapshot; its approval is an internal decision.', `${anchor('certification-reports')}, ${projectSection}`],
  ['Maintain the evidence over time', 'Retain earlier assessments and packages, and plan later maintenance. Project completion or a recorded test result does not establish an authority’s decision.', `${anchor('certification-history')}, ${projectSection}`],
])
const changes = make('changes', 'Controlled changes', 'Show how a proposed change affects the compliant system and its recorded evidence.', [
  ['Understand the change record', 'Change Management connects affected components, planned changes, assessment work, approvals, and release evidence.', surface('change-detail', 'changes-page')],
  ['Define the affected scope', 'Confirm the market, component register, affected components, and intended change before deciding which checks are needed.', nav('Change management sections')],
  ['Assess the impact', 'Link the relevant requirements and evidence. Give contributors and reviewers clear responsibility for the checks before release.', surface('change-detail', 'changes-page')],
  ['Review before release', 'Resolve outstanding readiness checks and obtain the required internal decisions. Record actual release activity separately from the plan.', surface('change-detail', 'changes-page')],
  ['Preserve the trail', 'Keep baseline comparisons and release records together. Follow any required external notification or certification process separately.', nav('Change management sections')],
])
const requirementContext = surface('requirements-list', 'requirement-source', 'requirement-editor', 'requirement-import', 'requirement-wording', 'library-requirements')
const requirements = make('requirements', 'Requirements', 'Establish a clear, controlled record of the obligations you need to assess.', [
  ['Start from the obligation', 'Requirement sources hold the wording, references, and jurisdiction of the obligations. They are the basis for assessment, not assessment decisions.', requirementContext],
  ['Find the relevant source', 'From Resources, use Open requirements. In the collection, choose the source set for the intended market and scope.', `${anchor('library-requirements')}, ${anchor('requirements-filters')}, ${requirementContext}`],
  ['Check wording and context', 'Compare imported or edited wording with the original source. Resolve uncertain references and preserve the surrounding requirement hierarchy.', requirementContext],
  ['Review before reuse', 'Use approved requirement sets for certification assessments. Draft sources can help prepare form questions while source review continues.', requirementContext],
  ['Handle changes explicitly', 'Keep the requirement versions used by an assessment clear. Review a proposed project baseline upgrade before changing its selected versions.', requirementContext],
])
const assessmentContext = surface('assessments-page', 'assessment-detail')
const assessments = make('assessments', 'Requirement assessments', 'Connect each applicable requirement to evidence and a reviewer’s decision.', [
  ['Understand the assessment', 'An assessment applies selected requirement versions to a project or change. It retains that scope for its recorded decisions.', assessmentContext],
  ['Agree ownership and applicability', 'Confirm who prepares each item and who reviews it. Explain why an obligation applies or why an exclusion is justified.', assessmentContext],
  ['Provide an evidenced assessment', 'Read the obligation, explain the assessment, and attach supporting evidence. A completed contributor assessment still needs the required review.', `${anchor('assessment-filters')}, ${assessmentContext}`],
  ['Resolve the review handoff', 'Reviewers record their decisions and identify gaps. Contributors address the requested work before the item can be complete.', assessmentContext],
  ['Close a complete record', 'Use completion checks before closing the assessment. Its preserved snapshot supports reports and submission packages; it does not replace authority approval.', assessmentContext],
])
const forms = make('forms', 'Forms', 'Collect clear answers and supporting evidence for review.', [
  ['Understand a completed form', 'A form contains answers and evidence for saved questions. It can support a licence pack, certification project, or standalone preparation work.', surface('form-detail', 'forms-list')],
  ['Start with the right context', 'Choose the relevant form and confirm its market, owner, and parent workflow. A blank template supplies questions for a new form.', surface('form-detail', 'forms-list')],
  ['Answer with supporting evidence', 'Read the question and guidance, give a complete answer, and attach evidence that supports that answer.', `${anchor('form-answers')}, ${anchor('forms-list')}`],
  ['Follow reviewer feedback', 'Keep the form open until changes are saved. Address returned answers and obtain the required acceptance.', `${anchor('form-readiness')}, ${anchor('forms-list')}`],
  ['Return to the wider workflow', 'Check required-answer readiness before handing the form back. Form acceptance, pack approval, and authority decisions are separate.', surface('form-readiness', 'forms-list')],
])
const templates = make('templates', 'Blank forms', 'Prepare reusable questions before collecting answers.', [
  ['Understand the template', 'A saved blank form defines reusable questions and guidance. It does not contain a particular application’s answers.', anchor('templates-library')],
  ['Choose a suitable starting point', 'Browse an existing template before creating another. Confirm its purpose and kind match the form you need.', anchor('templates-collection')],
  ['Check the question source', 'Review prepared or imported questions against the original source. Make required answers and supporting guidance clear.', anchor('templates-library')],
  ['Hand off to a working form', 'Save the reusable questions, then create a form in the appropriate workflow. Existing forms retain the questions saved with them.', anchor('templates-library')],
])
const evidence = make('evidence', 'Evidence', 'Keep supporting material useful, traceable, and connected to the question being reviewed.', [
  ['Understand shared evidence', 'The library holds reusable files, notes, and links. Evidence supports an answer or decision; saving it does not establish compliance.', anchor('evidence-library')],
  ['Find before adding', 'Search for relevant existing material and inspect its contents. Confirm its source and suitability before reusing it.', anchor('evidence-collection')],
  ['Attach evidence in context', 'Attach the material to the relevant form answer. Reviewers need to see which question the evidence supports.', anchor('evidence-library')],
  ['Keep assessment records distinct', 'Evidence supporting requirement assessment decisions stays with that assessment and its controlled history. Use the assessment workspace for that work.', anchor('evidence-library')],
])
const answerReview = make('answer-review', 'Answer review', 'Decide whether a form answer and its evidence are ready to accept.', [
  ['Understand the reviewer’s role', 'Answer review brings together accessible answers needing a decision. Acceptance covers the answer and its attached evidence.', anchor('answer-review-queue')],
  ['Choose the work to review', 'Find the relevant answer and check its form context. Prioritize returned work, changed evidence, or overdue assignments where appropriate.', anchor('answer-review-queue')],
  ['Read the complete record', 'Check the question, answer, guidance, and evidence before deciding. A populated answer alone does not establish readiness.', anchor('answer-review-detail')],
  ['Make the handoff clear', 'Accept a sufficient answer or return it with actionable feedback. The contributor needs to know what must change.', anchor('answer-review-detail')],
  ['Keep acceptance current', 'Changed answers or evidence can need another review. Follow the new saved record before accepting it again.', anchor('answer-review-detail')],
])
const teams = make('teams', 'Teams and access', 'Give the right colleagues access to the work they need.', [
  ['Understand a team', 'A team groups colleagues for sharing. Its owner maintains membership; the team itself does not grant access to every record.', anchor('teams-list')],
  ['Agree membership and responsibility', 'Create or use a team with a clear purpose. Check who owns it and who belongs to it.', anchor('teams-list')],
  ['Share in the workspace', 'Use the pack, project, or form’s access controls to share with the team. Confirm the intended permissions before saving.'],
  ['Keep roles and sharing distinct', 'Roles and record permissions together control viewing, editing, approval, and export. Review access when responsibilities change.'],
])
const assurance = make('assurance', 'Project readiness', 'Turn outstanding preparation checks into clear next actions.', [
  ['Understand readiness', 'This workspace brings together internal preparation checks for certification projects. It helps identify what is still needed for the next stage.', anchor('readiness-page')],
  ['Choose the project', 'Select the project in the intended jurisdiction. Read its current stage before reviewing the outstanding work.', anchor('readiness-page')],
  ['Follow the next action', 'Use the listed actions and blockers to reach the relevant assessment, form, testing engagement, or package.', anchor('readiness-page')],
  ['Complete work at its source', 'Make the correction in its own workspace, with the responsible contributor or reviewer. Readiness summarizes those saved records.'],
  ['Separate readiness from acceptance', 'A passed preparation check does not establish a provider’s certification or regulator approval. Retain those actual decisions separately.', anchor('readiness-page')],
])
const reports = make('reports', 'Reports', 'Use the recorded work and evidence appropriate to your review.', [
  ['Choose the reporting purpose', 'Assessment reports, controlled-change records, and audit history answer different questions. Start with the category that matches your review.', nav('Report categories')],
  ['Confirm scope and access', 'Select the relevant assessment, change, or history scope. Export availability depends on your role and record access.', anchor('reports-choice')],
  ['Use the right supporting record', 'Assessment reports show recorded decisions; evidence packages contain saved supporting files. A package manifest records controlled document references.', nav('Report categories')],
  ['Check the recorded version', 'Confirm which assessment or snapshot the export represents. A closed snapshot does not include later work automatically.'],
  ['Keep external outcomes distinct', 'Use reports to explain the internal work performed. They do not replace a provider’s report or the authority’s actual decision.'],
])
const account = make('account', 'My account', 'Keep your identity and personal preferences current.', [
  ['Understand your account', 'Your profile identifies you in assignments and recorded actions. Your role works alongside record-level permissions.', surface('account-profile', 'account-notifications')],
  ['Check your identity', 'Keep your displayed name accurate. Contact an administrator if your sign-in email or role needs to change.', nav('Account settings sections')],
  ['Choose personal preferences', 'Use Notifications to choose review-mention and reminder emails. Delivery also depends on the installation’s configured email service.', nav('Account settings sections')],
  ['Confirm saved changes', 'Check the success message after an update. Changing your password signs out your other sessions.', surface('account-profile', 'account-password', 'account-notifications')],
])
const marketSetup = make('market-setup', 'Market setup', 'Maintain a reviewed starting point for licence preparation.', [
  ['Understand the proposed checklist', 'Market setup supplies proposed contents for new licence packs where configured. It is preparation guidance, not a legal form definition.', surface('market-sources', 'market-items')],
  ['Start from authority sources', 'Confirm the jurisdiction and retain the authority instructions and source references used to prepare the checklist.', anchor('market-sources')],
  ['Review the starting contents', 'Check that setup questions and proposed items fit the intended applications. Confirm what remains application-specific.', surface('market-questions', 'market-items')],
  ['Hand off a checked proposal', 'Save reviewed changes and verify the authority’s current instructions before starting a pack. Existing packs retain their own selected contents.', anchor('market-items')],
])
const jurisdictions = make('jurisdictions', 'Jurisdictions', 'Keep compliance work in the correct market and authority context.', [
  ['Understand market context', 'Jurisdictions connect requirements, licence packs, projects, and assessments to the relevant market and authority.', anchor('jurisdictions-page')],
  ['Choose the intended market', 'Check the jurisdiction before starting or reviewing work. The selected market limits many collections and work queues.', anchor('jurisdictions-page')],
  ['Maintain the authority context', 'Use the available management controls to keep market details accurate. Open Market setup for the proposed licence checklist.', anchor('jurisdictions-page')],
  ['Continue in the right workflow', 'Open the market’s requirements, licence applications, or certification work. Confirm scope against current authority instructions.'],
])
const settings = make('settings', 'Administration settings', 'Understand which shared services need an administrator’s attention.', [
  ['Understand the administration boundary', 'Company admins manage their company’s Jira connection. System admins also manage shared email, AI, and installation backups.', nav('Settings sections')],
  ['Start with the service need', 'Choose the relevant settings area and check its current state. Agree the intended change with the responsible administrator.', nav('Settings sections')],
  ['Verify the configured service', 'A saved setting does not prove delivery. Administrators use the available service checks and review the result before relying on it.', surface('settings-jira', 'settings-email', 'settings-ai', 'settings-backups')],
  ['Keep recovery and preferences separate', 'Backups cover installation data and uploads. Personal notification preferences belong in My account; account roles belong in User Management.', nav('Settings sections')],
])
const users = make('users', 'User Management', 'Align account access with each colleague’s responsibilities.', [
  ['Understand account access', 'User Management holds organization accounts and roles. Roles determine available actions alongside permissions on individual records.', anchor('admin-users')],
  ['Confirm the colleague’s responsibility', 'Review the correct account and intended duties before changing its role or access.', anchor('admin-users')],
  ['Use teams for sharing', 'Teams organize colleagues for record sharing. Manage pack, project, and form permissions in their own workspaces.'],
  ['Verify the saved result', 'Check confirmation after an account change. Review access again when a colleague’s responsibilities change.', anchor('admin-users')],
])
const feedback = make('feedback', 'Product feedback', 'Turn reported problems and ideas into a clear development handoff.', [
  ['Understand the feedback record', 'The inbox holds organization reports when the feedback service is enabled. A report describes an issue; it does not verify a fix.', anchor('admin-feedback')],
  ['Check the reported context', 'Read the message, affected page, and available screenshot or element reference before deciding what needs investigation.', anchor('admin-feedback')],
  ['Prepare an actionable handoff', 'Use the brief controls to capture the problem, expected behavior, and useful context. Review the text before sharing it.', anchor('admin-feedback')],
  ['Track actual progress', 'Use status to reflect investigation and completed work. Confirm the reported behavior is fixed before treating the issue as resolved.', anchor('admin-feedback')],
])

/** One orientation per main section, independent of record IDs, tabs, and filters. */
export function getProductTour(pathname: string, search: string, _hash = ''): ProductTourDefinition {
  void _hash
  const path = pathname.replace(/\/+$/, '') || '/'
  const params = new URLSearchParams(search)
  if (path === '/') return work
  if (path === '/licence-applications') return params.get('case') ? forms : licences
  if (path === '/certification-projects') return certifications
  if (path === '/library') {
    if (params.get('section') === 'requirements') return requirements
    if (params.get('section') === 'forms') return forms
    if (params.get('section') === 'evidence') return evidence
    return templates
  }
  if (path === '/preparation') {
    if (!params.get('case') && params.get('tab') === 'templates') return templates
    if (!params.get('case') && params.get('tab') === 'evidence') return evidence
    return forms
  }
  if (path === '/requirements' || path.startsWith('/requirements/')) return requirements
  if (path === '/review-cycles' || path.startsWith('/review-cycles/')) return assessments
  if (path === '/answer-review') return answerReview
  if (path === '/change-management') return changes
  if (path === '/program-workspace') return assurance
  if (path === '/reports') return reports
  if (path === '/access-teams') return teams
  if (path === '/account') return account
  if (path === '/admin/settings') return settings
  if (path === '/admin/users') return users
  if (path === '/admin/feedback') return feedback
  if (path === '/jurisdictions') return jurisdictions
  if (path === '/market-setup') return marketSetup
  return PRODUCT_OVERVIEW_TOUR
}
