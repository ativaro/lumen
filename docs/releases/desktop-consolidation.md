# Desktop consolidation candidate

Status: integrated source candidate for independent review and isolated installation tests; not yet published.

The candidate starts from published GitHub commit `1054da56acc0c1e3ba9aa4b9d63d66d2fa0e4ff4`.
Forgejo commit `17cd13630bd82351d398fd5dd20808cf7b9a750b` has the same tree
`6666736c4e87092590486b4418845167a7ab0da6`. Development branch history is not imported.

| Area | Preserved source | Integration boundary |
| --- | --- | --- |
| Reader and PDF | Published source with changes from `3681b27`, `84b1bb7`, `a60a07b`; verified against installed code | Preserve current engine and annotation migration; no old PyMuPDF path |
| Cloud accounts | Published cloud modules and the maintained Search-QML cloud integration | Merge navigation, mount and property guards into current Files; retain transfer/menu behavior |
| Notes | Installed rich editor, scaling and table-menu evidence from October 13–15 | Source and licensed icons only; bring corresponding tests and packaging assets |
| Projects | Installed project detail, picker, folder and dialog evidence from October 15 | Preserve materials/conversations/tasks and current dialogs |
| Transfers | Verified October 15 transport optimization and earlier KIO/resume fixes | Preserve checksum, cancellation, account binding and scoped HTTPS lifetime |
| Files/Drive menu | Reviewed freeze `03bbee5c16513ef49823f686ac313b5951ab7f4f` | Preserve one menu path, references and preview; reconcile cloud context explicitly |
| Installers | Published user installer, bootstrap and Arch package definitions | Add only required dependencies/assets; validate source-only installation separately |

## Integration order

1. Record source hashes and installed evidence before changing the candidate.
2. Incorporate approved Notes/Projects/Drive sources in bounded feature slices.
3. Merge cloud navigation and mount safeguards into the current Files/menu code.
4. Bring matching regression tests and required asset/dependency packaging.
5. Check for missing imports, obsolete product workspaces and private development data.
6. Produce an immutable source freeze for independent review and isolated installer/UI tests.

No existing dirty worktree is changed. Runtime OAuth client configuration,
credentials, model files, environments, personal app data and deployment logs
are excluded. Tests and documentation must use synthetic paths and identities.
The coordinator owns final review, release versioning, publication and deployment.
Publication for this release is Forgejo only. GitHub branches, tags and releases
must remain unchanged. The existing GitHub commit is used only as a source base.

## Resolved source conflicts

The installed Files/Drive menu and transfer changes are integrated with the
maintained cloud-account navigation, inline rename, and unmounted-account write
and properties guards. Reader continues to open inside Files. Project draft and
saved-conversation CLI entry points are included with their native callers.

Published startup diagnostics, database compatibility handling, disconnect and
pairing controls, background synchronization, native PDF text extraction and
Vault mutation classification are retained. Older runtime copies of those
features must not replace this candidate. Note synchronization uses the existing
account-scoped `scope_parts` migration contract; legacy coordinates remain only
for preserving existing data bindings.

The updater records and checks the installed source URL. Forgejo installs follow
Forgejo, while existing GitHub installs keep their existing origin. Mixed origins
or a cache belonging to another origin fail explicitly. Credential-bearing source
URLs are rejected. Review and publication remain separate from these source edits.

## Validation boundaries

Product regression tests use disposable HOME/XDG profiles, offscreen Qt, and
candidate-local imports. Native UI modules run in separate processes because
QApplication themes are global. The suites cover transfers, Drive references and
menus, Notes editing/table/layout, project dialogs and material search, Cloud
account isolation, Reader/PDF, setup, Vault access, and source-aware updates.
Test fixtures were updated for the current nested menu, native properties dialog,
shared settings, and engine model-discovery API; production validation was not
relaxed to accommodate older fixtures.

No personal desktop runtime, device data, live account configuration, or models
are modified by this consolidation. Clean archive installation, simulator
acceptance, independent review, and publication are coordinator-owned release
gates. Synthetic transfer measurements do not establish performance on a user's
SMB/NAS workload.
