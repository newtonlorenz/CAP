# App change notes

Signed-in users can open **Help → Change notes** at `/change-notes`.
The page shows feature changes for each app version, newest first.
It does not require an active jurisdiction.

## Add notes for a deployment

1. Add a release entry to `frontend/src/content/releaseNotes.ts` before deployment.
2. Use a calendar app version such as `2026.10.03` and an ISO date such as `2026-10-03`.
3. If several feature releases ship on one day, append a sequence such as `2026.10.03.2`.
4. Put the new entry first. The page labels that entry **Current version** and opens it by default.
5. Give the release a short title and a summary of its user-visible result.
6. Describe each feature in a short title and one or two sentences.
7. Preserve earlier entries. Correct factual errors without inventing releases or historical capabilities.
8. Run the focused change notes and navigation tests, then include the page in release checks.
9. If deployment moves to another date or its scope changes, update the entry before shipping.

App versions identify the feature history shown in the interface.
They do not replace container image tags, Git revisions or deployment evidence.
Do not describe a prepared feature as deployed in an earlier version.
Use user-facing language; keep internal reviews, private data and operational details out of the content.

The initial history contains the feature release of 2 October 2026 and the release that adds this page.
Older releases are not reconstructed.
