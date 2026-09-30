# Verification — Lumen 1.1.0

- Full native suite: 61 tests pass with isolated XDG configuration and a real desktop D-Bus.
- Real WebDAV: connection, navigation, preview, copy/move, tab close and reopen pass.
- Shutdown regression: 24 separate real-engine launches closed at 0/150/500 ms pass for both window close and application quit. Deferred QObject disposal runs after shutdown slots and before interpreter shutdown.
- Native workflow end-to-end: persisted scheduled task creates a real Markdown file; its indexed source is placed in visible chat context.
- Local-model guard: a remote provider is rejected before POST; the installed engine confirms forced main model, small model and provider allowlist through its actual `/config` API.
- KWin: harmless script loads, runs and unloads through the actual D-Bus interface. User windows were not rearranged during verification.
- All eight native pages rendered and inspected. Existing file-manager tests pass.
- Injection, changed-file/permissions undo, workflow approval, leases, recovery, deduplication, secret filenames and canonical root revocation covered by regression checks.
- Independent foundation and integration review completed; reproduced findings fixed and rechecked.
- Python/Bash syntax, JSON metadata and git whitespace checks pass. Arch package builds successfully.
- Legacy installation migrated without its destructive uninstall scriptlets; captured service enabled/active states compare equal afterward. New jobs timer remains disabled.
- Upgrade checks distinguish the actual legacy package from the new package providing its compatibility name; regression reproduces and prevents mistaken removal.
- Optional speech pipeline requires a local Whisper installation/model; dependency error behavior is present. No microphone recording or inference model download was performed during automated verification.
