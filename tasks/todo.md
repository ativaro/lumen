# Ordered implementation

- [x] 1. Offline NAS: pin/open local copy; reconcile add/edit/delete; conflict comparison; reconnect; integrity + UI checks; commit.
- [x] 2. Search: OCR documents/images; natural image descriptions; source/page results; dependency UI; focused + UI checks; commit.
- [x] 3. Versions: watched folders and durable snapshots; compare/restore; retention; external-edit + UI checks; commit.
- [x] 4. Voice: continuous local audio pipeline; shared conversation; interruption/stop; setup; pipeline + UI checks; commit.
- [x] 5. Actions: completed task → workflow; context-menu selection; preview + execution checks; commit.
- [x] 6. Document workshop: preview/order/merge/extract/OCR/redact; safe export; content-removal + UI checks; commit.
- [x] Final: 125 tests passed in an isolated profile; native UI rendered on KDE; package 1.2.0-26 built and installed with source comparison. Portable source published; local system/sync notes updated.

Runtime note: the older resident search was restarted with the user's permission after installing the microphone update. Existing main-app sessions are preserved. Audio synthesis/recognition was tested with a generated German sentence; live microphone input and cloud image inference were not sent during verification.

## Top-panel microphone

- [x] Add a theme-aware, keyboard-accessible microphone to the existing search capsule.
- [x] Route the click through the panel helper and singleton search to the existing voice conversation; repeated activation keeps an active microphone running, hiding stops it.
- [x] Verify 10 focused Python tests and 12 QML checks, including icon alignment and keyboard activation.
- [x] Install package 1.2.0-27, compare installed sources, reload role widgets without restarting Plasma, verify cold/warm voice activation in an isolated session and the new live search interface.

## Voice activity

- [x] Shared native activity strip in search and Files: theme colors, reactive blob, waveform at wider widths, explicit microphone state.
- [x] Feed capture RMS through the existing worker; playback envelope from the local WAV after player start; separate preparation from speaking.
- [x] Stop animation and playback metering on hide/stop; reject malformed meter values and decay stale levels.
- [x] Render listening/thinking/speaking on KDE in all four themes and verify the 350px Files layout.
- [x] Full isolated suite: 128 tests passed, including real capture-worker output using synthetic PCM and fragmented QProcess meter output.
- [x] Package 1.2.0-28 installed and sources compared; idle search restarted after verifying no draft/messages/session or active subprocess, with a local checkpoint backup.

## Recognition quality

- [x] Share explicit language, vocabulary and GPU preferences across dictation, microphone tests and voice conversation; native editable settings.
- [x] Add opt-in, checksum-verified Large v3 Turbo Q8 installation; preserve the smaller model.
- [x] Compare locally generated German samples with the previous configuration; verify the Vulkan build on local hardware without recording the microphone.
- [x] Provide checkpoint restoration on a fresh search start, without resending any restored prompt, so updates preserve an existing conversation.
- [x] Full isolated suite: 131 tests passed; native setup and recognition settings rendered on KDE.
- [x] Package 1.2.0-29 installed and sources compared; local quality model/GPU runtime selected with backups; current search conversation restored without sending. Installed recognition verified with synthetic speech.

## Eigenständige Desktop-Werkzeuge

- [ ] Gemeinsame private Speicherung, abbrechbare Jobs, Audio und native Oberfläche.
- [ ] Meeting-Werkstatt mit Transkript, Zeitstellen und strukturierten Ergebnissen.
- [ ] Digitaler Haushalt mit Geräten/Verträgen, Belegen und Fristen.
- [ ] Projekt-Werkbank mit Dateien, Links, Notizen und Fragen.
- [ ] Persönliches Radio mit Quellen, Hörskript und lokaler Audio-Ausgabe.
- [ ] Native UI, reale Sprachpipeline, Fehlerpfade, Persistenz, vollständige Tests.
- [ ] Portable Installation und Paket, Git-Veröffentlichung, lokale Dokumentation.
