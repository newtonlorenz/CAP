# Security

See the [source candidate security status](docs/public/security-status.md) for the
current dependency findings and container distribution restrictions.

This is the first public source candidate; no supported container release is
established by publishing this source. Use
[GitHub private vulnerability reporting](https://github.com/newtonlorenz/CAP/security/advisories/new)
on the publication repository when enabled. Maintainers must enable and verify
that channel before source publication. If it is unavailable, do not put a
sensitive report in a public issue; request a private contact route without
including vulnerability details. Do not post credentials, customer records,
evidence files or exploitable private deployment details in public issues.

Include the affected source revision or image digest, a minimal reproduction
using synthetic data, the impact and any suggested fix. No response-time or
long-term support commitment is established for this initial candidate.

Run CAP behind HTTPS, restrict allowed hosts and origins, use independent strong
credentials and maintain verified backups. External AI, email, Jira and feedback
are opt-in integrations with their own data-handling implications. PDF parsing is
bounded, but untrusted files still require patched application and OS dependencies.

Security-sensitive contributions must preserve tenant boundaries, session revocation,
authorization, audit trails, file/path validation and backup integrity. Add meaningful
regression tests for changes to those boundaries. Never test against production data.

Dependency lockfiles and CI checks are reviewed inputs, not guarantees that every
vulnerability has been identified. Review runtime and container advisories before
publishing each release and document the supported upgrade path.

Installation operators are explicitly listed by user UUID in
`INSTALLATION_OPERATOR_IDS`; a tenant administrator is not an installation operator.
Only those operators can manage whole-installation backups and Jira configuration.
Restore only backups from a trusted source: PostgreSQL restore can execute SQL and
client commands. Archive hashes detect corruption and changes after import, but do
not authenticate the original author. The backend runs as UID/GID 10001; this does
not make arbitrary restore scripts safe. Keep backups and staging storage on a
quota-controlled volume and size `BACKUP_EXPANDED_MAX_MB` for that capacity. This
limit covers the combined outer archive payload and expanded upload contents;
allow additional capacity for staging and pre-restore snapshots.

Login limits share account and source counters in the database. The source is
Uvicorn's resolved client address. Set `FORWARDED_ALLOW_IPS` to the actual ingress
proxy IPs or narrowly scoped CIDRs, and restrict direct backend access. Do not
trust all forwarded headers with `*`. If another proxy or tunnel sits before
Nginx, establish and verify the trusted chain there too. Test that two external
clients have distinct source addresses and that forged forwarding headers cannot
change the resolved source. Until this is configured, requests through an
untrusted proxy share its source quota; per-account throttling still applies.

Jira requests use HTTPS, tenant credentials bound to their site/account, no
redirects and no environment-proxy overrides. `JIRA_ALLOWED_HOSTS` is an operator
trust decision. Restrict outbound traffic to approved Jira destinations at the
network boundary as well; hostname validation alone cannot constrain DNS routing.

Upload bodies are limited while streaming, before multipart parsing, to the
configured document/evidence/backup file limit plus 1 MiB of form overhead. File
limits still apply inside the handlers. The Nginx template streams API requests
to allow early rejection; keep an edge body limit and storage quotas too. PDF
preprocessing runs in a separate process group with a wall-clock deadline, page
limit, CPU/output limits and Linux address-space limit. Timeout or cancellation
terminates that group and cleans its staging directory.
