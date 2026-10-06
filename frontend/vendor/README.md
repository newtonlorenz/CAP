# Page Feedback widget

`page-feedback-react-0.1.1.tgz` is a versioned build of the independent
`page-feedback/widget` React package, licensed under MIT. It contains only the
reusable widget, not CAP code or credentials. The exact integrity is recorded in
`../package-lock.json`. It is deliberately vendored so CAP builds do not require
a sibling checkout, symlink, unpublished npm package or access to a private Git host.

The source link and licence are in `../../THIRD_PARTY_NOTICES.md`.
Its source and licence match this 0.1.1 archive;
the compiled files were compared byte-for-byte with a fresh build from that public
commit. The companion service remains unpublished, so CAP's optional feedback
integration is unsupported in the first public release. The archive does not
provide a service. To update the archive, run
`bash scripts/update-feedback-widget.sh /path/to/page-feedback` from the CAP
repository root. Keep package version changes deliberate. The screenshot engine
remains an ordinary locked npm dependency and a separate lazy build chunk.
