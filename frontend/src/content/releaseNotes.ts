export type ReleaseNote = {
  version: string
  date: string
  title: string
  summary: string
  features: { title: string; description: string }[]
}

// Calendar app versions, newest first. Add an entry for each deployed release.
// See docs/public/change-notes.md for the release procedure.
export const releaseNotes: ReleaseNote[] = [
  {
    version: '2026.10.07.3',
    date: '2026-10-07',
    title: 'Clearer introductions to each workspace',
    summary: 'Short guided tours explain each section’s purpose, its core principles and how to get started.',
    features: [
      { title: 'Licence application tours', description: 'Understand how a licence pack brings together forms and supporting evidence, how internal review works, and how to record actual submission and follow-up.' },
      { title: 'Certification project tours', description: 'Understand project scope, requirement baselines, assessments, testing findings and reviewed submission packages, with a clear starting point for new work.' },
      { title: 'Tours throughout CAP', description: 'Use Help → Product tour for a short introduction to the current section. Skip, resume or replay tours independently. Changing tabs within a section keeps its tour progress.' },
      { title: 'Requirement evidence access', description: 'Requirement evidence and validation history are visible to their creator, owner and reviewer. Content edits and approval decisions also require the appropriate role; account administrators cannot open unrelated evidence.' },
      { title: 'Feedback implementation brief', description: 'Copy or preview a brief from a product feedback report to investigate it in public CAP. Attached screenshots and private report details stay separate from public pull requests.' },
      { title: 'Account and notification guidance', description: 'The Guide explains profile changes, password changes, saved email preferences and how to check missing notifications.' },
    ],
  },
  {
    version: '2026.10.07',
    date: '2026-10-07',
    title: 'Guided onboarding and clearer team workflows',
    summary: 'Explore the main resources with a short product tour and keep answers, evidence and review work together.',
    features: [
      { title: 'Guided product tour', description: 'First-time users can choose a short tour of Requirements, Assessment overview, Evidence and Reports. Skip, resume or replay it from Resources → Help → Product tour.' },
      { title: 'Work and resources at the top', description: 'The top navigation keeps the main workspaces in view and groups reusable resources and Help in a dropdown. Smaller screens use the menu drawer.' },
      { title: 'Answers ready for review', description: 'Assign reviewers, follow answer history and open evidence beside the answer. Team work on the dashboard makes review assignments easier to find.' },
      { title: 'Clearer preparation and packs', description: 'Licence forms, certification work and controlled changes show focused sections, next actions and pack contents.' },
      { title: 'Bilingual form headings', description: 'Form headings retain their Danish and English labels when preparing answers.' },
    ],
  },
  {
    version: '2026.10.03',
    date: '2026-10-03',
    title: 'Clearer daily work and safer drafts',
    summary: 'Find your next action faster and move through licence, assessment, change and certification work with clearer guidance.',
    features: [
      { title: 'Work first on the dashboard', description: 'Assigned work and next actions appear before coverage totals. Active assessments open directly in the focused view.' },
      { title: 'Shorter licence setup', description: 'Creation skips steps that do not apply to the market. Add form questions before optional owners, deadlines, pack settings and source files.' },
      { title: 'Focused assessments', description: 'Continue an assessment with one requirement in view, clear progress and a direct return to its overview.' },
      { title: 'Clearer change proposals', description: 'Optional details are grouped by purpose. Approval explains missing information, and adding an impact item keeps your selected requirement set and version.' },
      { title: 'Certification package readiness', description: 'See approval blockers beside the selected package and follow direct links to its checklist, documents or assessment.' },
      { title: 'Safer drafts and uploads', description: 'Unsaved evidence prompts before you leave. Pending saves protect edits, and completing proposal details preserves an existing draft.' },
      { title: 'Change notes', description: 'Open Help → Change notes to see the feature changes in each app version.' },
    ],
  },
  {
    version: '2026.10.02',
    date: '2026-10-02',
    title: 'Contextual workspaces and account controls',
    summary: 'Navigation follows the work you are doing, with reusable resources and personal settings in clear locations.',
    features: [
      { title: 'Work and resources navigation', description: 'Licence applications, certifications and controlled changes have dedicated workspaces and creation flows. Reusable forms, evidence and requirement assessments sit under Resources.' },
      { title: 'Profile and account settings', description: 'Use the profile menu to update your name, change your password, choose appearance and manage mention and reminder emails.' },
      { title: 'Certification and requirement readability', description: 'Certification findings appear above testing details. Hierarchy depth controls make requirement outlines and lists easier to scan.' },
      { title: 'Danish change controls', description: 'Change management records approved component scope, certified baselines, implementation details and review evidence through an auditable workflow.' },
    ],
  },
]
