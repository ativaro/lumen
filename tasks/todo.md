# Ordered implementation

- [x] 1. Offline NAS: pin/open local copy; reconcile add/edit/delete; conflict comparison; reconnect; integrity + UI checks; commit.
- [x] 2. Search: OCR documents/images; natural image descriptions; source/page results; dependency UI; focused + UI checks; commit.
- [x] 3. Versions: watched folders and durable snapshots; compare/restore; retention; external-edit + UI checks; commit.
- [x] 4. Voice: continuous local audio pipeline; shared conversation; interruption/stop; setup; pipeline + UI checks; commit.
- [x] 5. Actions: completed task → workflow; context-menu selection; preview + execution checks; commit.
- [x] 6. Document workshop: preview/order/merge/extract/OCR/redact; safe export; content-removal + UI checks; commit.
- [x] Final: 125 tests passed in an isolated profile; native UI rendered on KDE; package 1.2.0-26 built and installed with source comparison. Portable source published; local system/sync notes updated.

Runtime note: an older resident search without checkpoints is left running until the user authorizes its restart. Existing main-app sessions are preserved. Audio synthesis/recognition was tested with a generated German sentence; live microphone input and cloud image inference were not sent during verification.

## Top-panel microphone

- [x] Add a theme-aware, keyboard-accessible microphone to the existing search capsule.
- [x] Route the click through the panel helper and singleton search to the existing voice conversation; repeated activation keeps an active microphone running, hiding stops it.
- [x] Verify 10 focused Python tests and 12 QML checks, including icon alignment and keyboard activation.
