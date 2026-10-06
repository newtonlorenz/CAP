# Interface guidelines

CAP presents requirements, evidence and decisions together. Keep source text readable,
make work status explicit, and preserve the user's place when saving or navigating.

## Appearance

- Use the self-hosted Manrope family. Keep its licence with the font files.
- Use semantic tokens from `frontend/src/index.css` and `frontend/tailwind.config.js`.
  Components must support light and dark themes without changing document or evidence colours.
- Keep primary and secondary text at least 4.5:1 against the surfaces where it appears.
  Dark mode uses neutral charcoal surfaces with clear input borders; avoid low-opacity
  body copy. Check real controls, including icon size, rather than token values alone.
- Name every status in text. Colour can reinforce meaning but cannot carry it alone.
- Prefer borders for ordinary surfaces and elevation for menus and dialogs.
- Provide visible keyboard focus and respect reduced-motion preferences.

## Navigation and editing

- Keep desktop navigation persistent and the mobile drawer keyboard accessible.
  Provide a skip link. Page search searches permitted navigation, not document content.
- Preserve the selected requirement and unsaved draft through routine view changes.
  Distinguish pending changes, a successful save and a failed save.
- Keep assessment and evidence fields visible beside the requirement at desktop widths.
  Keep filters available and reflect their state in the URL.
- On mobile, show the assessment task before secondary reports and filters. Keep
  active filters indicated when their controls are collapsed.
- Browse reusable templates and evidence before opening their editors; preserve
  drafts when returning to the collection and guard navigation away from them.
- Group long readiness lists by form and issue type, with direct links to the affected
  fields and an explicit return to the original pack section.
- Show current and proposed baseline versions separately. Require an explicit version
  selection and confirmation for upgrades; unchanged sets retain their versions.
- Use the server's completion rules for review readiness. Excluded and informational
  rows must not inflate applicable-control counts.
- Keep hierarchy editing scoped to the full source tree. Never infer a missing parent
  from a filtered subset. Make the full requirement list available from focused editing.
- Provide one hierarchy-depth control for both the outline and list, and remember
  the preference between pages. Put Show levels above the outline heading, retain it
  when filters change or return no matches, and apply depth to the full hierarchy.
  Keep focused items available; bulk actions must
  never include requirements hidden by the chosen depth.
- Keep dialogs and menus within the viewport. Restore focus after closing a dialog
  and preserve scroll locking when dialogs are nested.
- Show failed requests as errors with recovery actions, not empty results.
- Display unambiguous dates, such as `28 Feb 2026`, and use the device's local time
  for timestamps. Keep API values and export data unchanged.

## Verification

Use populated synthetic fixtures to check both themes, a mobile viewport, long
requirement text, menus and dialogs. Check keyboard navigation, failed saves and
restoring the selected item. The [contribution guide](../../CONTRIBUTING.md) describes
the isolated browser test environment.
