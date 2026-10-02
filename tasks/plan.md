# Lumen: native everyday tools

Approved order: offline NAS → content/image search → file versions → continuous voice → reusable actions → document workshop.

Use existing Qt widgets, KIO credentials, Store, OpenCode sessions, workflow validation and setup wizard. Local private state stays outside Git. Each feature is a separate verified commit. Install and publish the combined release after integration verification; do not restart Plasma/KWin or interrupt running tasks.

1. Offline: explicit pin creates a private local working folder; three-way, hash-based sync with per-file conflict choices and archived replaced/deleted contents. Reconnect in background while Files runs; all filesystem/network work outside GUI. No automatic conflict winner; interrupted scans never mean deletions.
2. Search: extend existing content search with local OCR (images/scanned PDF pages), and opt-in image descriptions through the configured vision-capable model. Results show file, page and matching passage; cloud image analysis requires explicit UI selection. Reuse the setup wizard for dependencies.
3. Versions: explicitly watched folders are sampled by an independent user process, including changes from other apps. Private content-addressed snapshots, retention controls, compare and guarded restore. Explain that versions begin at activation and very brief intermediate edits can escape sampling.
4. Voice: local microphone capture, silence detection, existing Whisper transcription, local speech output; reuse one OpenCode conversation. Visible recording/processing/speaking states, interruption, stop and clear failures. Existing text/permission flows stay intact. Optional dependencies through setup.
5. Actions: save successful task as named manual workflow, expose it in Files context menus with current selection; preview/validate targets before native execution. Reuse existing workflow storage and runner, avoid a second action engine.
6. Documents: native PDF page preview, select/reorder/merge/extract, OCR, rectangle redaction that removes content. Always export a new file atomically; verify output and never overwrite source PDFs silently.

Verification: focused data-integrity tests per feature; offscreen native UI event-loop smoke checks; final isolated full suite; committed-source package build, installation/source comparison. No real personal NAS files modified during tests.
