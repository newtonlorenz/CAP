# Content access and confidentiality

Account administration and content access are separate. Being a company administrator
or installation operator does not grant permission to open confidential applications
through CAP. For resources with an access policy, business owner and reviewer
assignments do not grant access. The resource's access owner and explicit grants
control its audience.

## Visibility

- **Organisation** preserves the existing organisation-wide workflow and role checks.
- **Restricted** limits content to its access owner and explicitly granted people or
  owner-managed teams.
- **Highly confidential** limits access to its access owner and named people. Team
  grants are not accepted, so adding someone to a team cannot reveal this material.

New licence applications, standalone preparation forms and shared-evidence records
start highly confidential. Existing records retain their previous organisation
visibility until their access owner changes it. Review existing sensitive records
before inviting additional users; the migration cannot infer their confidentiality.

Users with no access must not see names, existence, counts, search matches, activity,
attachments or direct-link details. A separately granted application summary shows
only the limited status information needed for oversight. It does not grant access
to answers, supporting information, authority correspondence or approved packs.

## Permissions

View summary, view contents, edit, approve, export and manage access are separate
permissions. Existing workflow roles and stage checks still apply. A permission to
manage access is powerful: it allows changing the audience and should only be given
to trusted content custodians. Assigning an operational owner does not transfer this
power. Access changes require a reason and are recorded in the audit trail.

Application forms and evidence can inherit a confidential workspace's restrictions.
A child can be narrower than its parent. Removing its application link does not
remove its privacy restriction. A source already protected by a different workspace
must be copied into a separately controlled record instead of being reparented.
Organisation-visible source requirements remain shared library material; private
review commentary must remain inside the restricted project review.

Approved application downloads contain immutable historical bytes. Current export
and source access must still be checked when downloading a past version. Granting
summary or view access alone does not grant export access. A user who cannot access
all required contents cannot obtain an unredacted full pack.

Teams have their own access owner. Account administrators cannot change membership
simply because they administer accounts. Highly confidential work does not use teams.
Administrators can deactivate accounts, but cannot replace another confidential
user's password or sign-in address to impersonate that user. Identity-verified
credential recovery requires a separate controlled operational process.

## Requirement evidence library

Requirement evidence items (`/evidence-items`) use a separate participant policy.
Only the creator, assigned owner and assigned reviewer can read an item or its
validation history. Creators and owners with contributor, manager or admin roles
can edit content and assignments. Participants with approver or admin roles can
approve, reject, withdraw approval and record validations. Reviewer assignment
alone does not permit content edits. An edit to approved content invalidates its
previous approval. Account administrators have no access to unrelated evidence.

This policy applies to existing and new items, including items without assignments.
Evidence lists, filtered counts and audit entries omit inaccessible items entirely.
There are no summary grants or team grants for this library. Assignment changes
change its audience, so only authorized content editors can make them. CAP checks
mutation authority after locking the evidence row. Evidence in preparation forms
continues to use the resource access and inheritance policy described above.

## Protection boundary

These controls protect access through the application, its APIs and exports. They
are not end-to-end encryption against people who control the host, database, backup
files or application signing secrets. Those infrastructure operators remain trusted
and require separate operational restrictions. CAP does not claim formal security
classification or certification for the "Highly confidential" label.

Permission revocation stops subsequent authorised requests. It cannot recall a file
already downloaded, an email already delivered or information already read. API
responses use `Cache-Control: private, no-store`; the interface clears its state after
an access change rather than retaining earlier confidential results.
