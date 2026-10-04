# Ordered implementation

- [x] Einzeiler: HTTPS-Download, Basisabhängigkeiten, Benutzerinstallation und Wizard-Start; Fehlerpfade prüfen.
- [x] Wizard: explizite Desktop-Aktivierung mit vorhandenem Backup und vier Themes; native UI prüfen.
- [x] Installation: isolierter vollständiger Durchlauf und native Wizard-Ansicht; 144 Tests bestanden. Desktop-Worker und wiederholte Einrichtung in virtueller Plasma-Sitzung geprüft; Einzeiler und Anleitung zur Veröffentlichung fertig.

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

- [x] Gemeinsame private Speicherung, abbrechbare Jobs, Audio und native Oberfläche.
- [x] Meeting-Werkstatt mit Transkript, Zeitstellen und strukturierten Ergebnissen.
- [x] Digitaler Haushalt mit Geräten/Verträgen, Belegen und Fristen.
- [x] Projekt-Werkbank mit Dateien, Links, Notizen und Fragen.
- [x] Persönliches Radio mit Quellen, Hörskript und lokaler Audio-Ausgabe.
- [x] Native UI, reale Sprachpipeline, Fehlerpfade, Persistenz, vollständige Tests.
- [x] Portable Installation und Paket, Git-Veröffentlichung, lokale Dokumentation.
- [x] Ohne Passwort: vier Werkzeuge im Benutzerprofil installiert, 68 Laufzeitdateien verglichen, alle Starter kalt und mit bestehendem Fenster geprüft. Systempaket bleibt 1.2.0-29; gebautes Paket30 ist optional für später.
# Foto- und Systemfunktionen

- [x] Persistente Vorschauen und schnelle Galerie mit sicherer Invalidierung.
- [x] Hardware-Anzeige und konfigurierbare Schonung bei Spielen/Aufnahmeprogrammen.
- [x] Lokale semantische Bildsuche, Einrichtung und reale Modellprüfung.
- [x] Foto-Aufräumhilfe mit Vorschau, Auswahl und bestehendem Papierkorb.
- [x] Integration, vollständige Tests, Dokumentation, Paket und Benutzerinstallation.
  149 Python-Tests, 12 QML-Checks, echte mehrsprachige CLIP-Inferenz, native Ansichten
  und virtueller Plasma-Installationslauf bestanden. Paket 1.2.0-33 gebaut;
  vollständige Benutzerinstallation mit Quellvergleich, gesicherten Startern und
  unveränderten Plasma-/KWin-Einstellungen. Laufende Fenster bleiben geöffnet.
# Vault und Inbox

- [x] Gemeinsamer Schlüsselbund, Vault-Sicherung und sichere Wiederherstellung.
- [x] Native Vault-Oberfläche, Ziele, Vorschau und Zeitpläne.
- [x] IMAP/SMTP/Proton-Bridge und CalDAV/ICS mit lokalen Protokolltests.
- [x] Native Inbox mit Nachrichten, Entwürfen, Kalender, Aufgaben und Vorschlägen.
- [x] Einrichtung, Starter, Paket, vollständige Prüfung und Benutzerinstallation.

Verifiziert: 155 Tests im vollständigen Python-Lauf (Kalender-Abhängigkeit dort
optional übersprungen), zusätzliche Zeitplanprüfung, 3 echte lokale TLS-Protokolltests
im Kalender-Environment und 12 QML-Prüfungen. Native Dialoge, Entwurferhalt und
Kalt-/Warmstart beider installierter Apps geprüft. Frische virtuelle Plasma-
Installation erfolgreich; Paket 1.2.0-34 gebaut und Quellen verglichen.
Benutzerinstallation ohne sudo und ohne Neustart laufender Fenster abgeschlossen.
Konten und Sicherungspläne bleiben benutzergeführt; keine echten Mails versendet.

# Reader und Sound

- [x] Reader: Import, Seiten/Text, Fortschritt, Markierungen/Notizen, Vorlesen/Wissen.
- [x] Sound: Stream-Mixer, Ausgänge, gespeicherte App-Regeln und Gesprächsabsenkung.
- [x] Reale Dokument- und isolierte Audiotests, native Oberflächen und Starter.
- [x] Paket, Benutzerinstallation, portable Git-Quellen und private Referenz.

Verifiziert: 162 Python-Prüfungen (161 bestanden, ein optionaler Kalendercheck
übersprungen), 12 QML-Prüfungen, reale PDF-/EPUB-/HTML-Verarbeitung und Piper-
Synthese. Private PipeWire-Sitzung: Routing, Stumm, Regeln, Gesprächsabsenkung,
Wiederherstellung und manuelle Änderungen. Native Sound-Bedienung einschließlich
Tastatur geprüft; acht installierte Starter kalt/warm, Reader-Dateiübergabe und
frische virtuelle Plasma-Installation erfolgreich. Ein verzögerter Offline-
Abgleich nach Fensterschluss wurde mit Regressionstest korrigiert.
Paket 1.2.0-35 gebaut und Laufzeitquellen verglichen; Benutzerbundle mit Sicherung
aktualisiert. Sound-Automatik bleibt aus. Laufende Benutzerfenster und
Desktop-Konfiguration bleiben erhalten; private Daten/Testprofile bleiben lokal.

# Lumen Wissen

- [x] Markdown-Speicher, Konflikt-/Entwurfschutz und verlustfreie Migration.
- [x] Native Bibliothek, Editor/Vorschau, Tags, Bilder, Links und Rückverweise.
- [x] Wissenskarte, Quellenfragen und Reader-/Inbox-/Lumen-Übernahme.
- [x] Integration, Tests, Paket, Benutzerinstallation, Git und private Referenz.

Abnahme: 168 Python-Prüfungen, davon 167 bestanden und ein optionaler
CalDAV-Check übersprungen; 12 QML-Prüfungen bestanden. Reader-Auswahl,
Inbox-Auswahl und Auftragsergebnis in den aktiven Markdown-Speicher geprüft.
Alle neun installierten Werkzeuge starten kalt/warm; Reader- und Wissen-
Dateiübergabe erreichen das vorhandene Fenster. Native Ansichten in vier
Themes, kompakter Ansicht, Quellenliste und Karte gerendert und geprüft.

Review: Konflikte/Entwürfe, wiederholte und späte Migration, Grenzen für Pfade,
Symlinks und Ressourcen, extern bearbeitete Quellen sowie Job-Lebensdauer
geprüft. Dateiarbeit läuft in abbrechbaren Unterprozessen. Modellauftrag verlangt
JSON, deaktiviert Werkzeuge und verwendet nur ausgewählte Auszüge; Antworten
wurden synthetisch geprüft, kein Live-Modellaufruf mit persönlichen Inhalten.

Paket 1.2.0-36 gebaut, relevante Laufzeit und Starter mit Paket verglichen.
Benutzerbundle mit Sicherung und konsistenter SQLite-Kopie aktualisiert;
installierte Python-/QSS-/SVG-Dateien entsprechen dem Repo. Bestehende optionale
Abhängigkeiten erhalten, Plasma/KWin-Konfiguration per Hash unverändert.
Persönliche Notizen, Bibliotheken, Sicherungen, Screenshots und Systemreferenz
bleiben außerhalb von Git. Systempaket-Upgrade gehört nicht zu dieser Installation.

# Persönliches Notizbuch und Lumen-Gedächtnis

- [x] Zwei native Bereiche, explizite Notiz-/Ordnerfreigaben und lokales Gedächtnis.
- [x] Herkunft, Zeitpunkt, Beleg, Projektbezug, Korrektur, Verlauf und Vergessen.
- [x] Gemeinsamer Gesprächskontext, begrenztes optionales Lernen und native Aktionen.
- [x] Integration, Abbruch, Konflikte, Freigabeentzug und Vergessen getestet.
- [x] Paket37, Benutzerinstallation und Starterprüfung abschließen.

Vollständige Prüfung: 173 Python-Prüfungen, davon 172 bestanden und ein optionaler
CalDAV-Check übersprungen; 12 QML-Prüfungen bestanden. Zusätzlicher fokussierter
Lauf prüft den Abbruch während der Kontextvorbereitung. Beide Bereiche in vier
Themes und kompakter Ansicht gerendert. Lokale Test-Engine mit synthetischen
Antworten für Lernen, späteren Kontext und frische Sitzung nach Freigabeentzug.

Review: Lumen ändert persönliche Notizen nicht automatisch. Korrigierte
Gedächtniseinträge bleiben geschützt, verspätete Lernvorschläge werden verworfen.
Vergessen entfernt aktive Datei, Entwurf und lokale Versionen; Hash-Sperren
erkennen bekannte identische Inhalte, keine beliebigen Umformulierungen.
Modellinterpretationen sind als automatisch markiert und korrigierbar.
Frische Profile starten ohne Nutzung/Lernen; Aktivierung hier ausdrücklich im
angenommenen Auftrag. Private Notizen, Register, Sicherungen und Screenshots
gehören nicht ins Git. Bedienung und Grenzen: WISSEN.md, Vertrag: SPEC-memory.md.

Paket 1.2.0-37 gebaut; Gedächtnis-/Gesprächsmodule und Wissen-Starter stimmen mit
Repo und Benutzerbundle überein. Vor Installation konsistente SQLite-Kopie und
Dateisicherung erstellt. Alle installierten Python-/QSS-/SVG-Dateien verglichen,
optionale Laufzeiten erhalten, Plasma-/KWin-Konfiguration per Hash unverändert.
Neun installierte Werkzeuge starten kalt/warm; Reader-/Wissen-Dateiübergabe
erreicht das bestehende Fenster. Gedächtnisnutzung und Lernen im angenommenen
Benutzerprofil aktiviert, ohne Beispielinhalte anzulegen. Laufende andere Apps
verwenden den neuen Gesprächscode nach ihrem nächsten Start. Systempaket bleibt
unverändert; die aktualisierte Laufzeit liegt im Benutzerbundle.

# Direktes Notizbuch — angenommener Bedienentwurf 1

- [x] Automatisch speichern, ohne neuere Eingaben, Cursor oder Undo zu ersetzen.
- [x] Drei Spalten, direkte Bereiche/Titel, Neu ohne Dialog und eingeklappte Details.
- [x] Sammlungen aus Ordnern/Tags, sichtbare Freigabe, bestehende Werkzeuge erhalten.
- [x] Verzögerte Schreibvorgänge, weitere Eingaben, Wechsel/Schließen, Frontmatter,
  Konflikte, neue Notizen, Freigaben und native Darstellung geprüft.
- [x] Paket38, Benutzerinstallation und installierte Starter geprüft.

175 Python-Prüfungen im vollständigen Lauf (174 bestanden, ein optionaler
CalDAV-Check übersprungen); bestehende QML-Themeprüfungen und fokussierte
Wissen-/Gedächtnisprüfungen. Vier native Themes und kompakte Ansicht gerendert.
Persönliche Daten bleiben außerhalb des Repos; Markdown, Dateipfade und
Freigaben werden bei der Umstellung nicht migriert oder neu angelegt.

Zusätzlich 13 fokussierte Wissen-/Gedächtnisprüfungen erfolgreich, einschließlich
Notizwechsel während laufenden Schreibens. 12 QML-Checks bestanden. Paket1.2.0-38
gebaut; UI/Speicher/QSS mit Paket und installiertem Benutzerbundle identisch.
Alle Python-/QSS-/SVG-Dateien der Benutzerinstallation verglichen. Vorher
Dateisicherung und konsistente SQLite-Kopie; optionale Laufzeiten erhalten,
Plasma-/KWin-Konfiguration per Hash unverändert. Alle neun installierten Tools
kalt/warm sowie Reader-/Wissen-Dateiübergabe geprüft. Neue Wissen-Oberfläche
geöffnet; es musste kein vorhandenes Benutzerfenster beendet werden.

# Bedienkorrektur: Sammlungen und Linktitel

- [x] Sichtbare Aktion „Neue Sammlung“; leere Ordner im Scan und nach Neustart.
- [x] Neue Notizen in gewähltem Ordner/Tag, Erinnerungen im gewählten Typ.
- [x] Auswahl mit tatsächlichem Titel und eindeutigem Pfad, relative Linkziele.
- [x] Vorschau mit aktuellem Zieltitel; vorhandene Dateinamen/Links bleiben stabil.
- [x] Regression für leere Sammlungen, neue Notizen, doppelte Titel, Links aus
  Unterordnern, Pfad-/Symlinkgrenzen und Autosave vor dem Sammlungswechsel.

176 Python-Tests bestanden, ein optionaler CalDAV-Check übersprungen; 12 QML-
Checks bestanden. Vier Themes, kompakte Ansicht und nativer Linkdialog gerendert.
Zusätzlicher Test bestätigt: Wechsel in eine leere Sammlung sichert den Text
und bleibt auch nach Scan leer. Keine Benutzernotizen für Tests verwendet.

# English localization and visible GitHub installation

- [x] Shared language setting, runtime API and catalog validation.
- [x] Main Lumen/Files/search interfaces in English and German.
- [x] Native companion tools, settings/setup and Plasma controls localized.
- [x] User text, storage keys, paths and commands remain unchanged.
- [x] German suite and English native checks, package/catalog installation.
- [x] README opening shows installation and accurate private access requirements.
- [x] Explain license/control tradeoffs; apply only the user's chosen direction.
- [x] Reviewed source pushed; remote and installed resources verified.

185 Python checks completed: 184 passed, one optional CalDAV integration check
skipped. All 12 QML checks passed. Native English main/Files/search/settings/
setup and nine companion apps checked with synthetic content, plus bilingual
panel smoke checks. Reviews caught and fixed cancellation routing and saved
context removal across language changes. Internal jobs keep the window language;
Qt-free calendar workers read the same setting without importing Qt.

Package 1.2.0-40 built; 186 runtime/catalog/panel resources match the package.
The user bundle and all five panel catalogs/helpers were compared with source;
optional runtimes were retained and existing windows left open. Installed English
main/Files/search/network/workshop/photo/version smoke checks passed. A consistent
SQLite and file backup precedes installation. No personal data, credentials,
backups or screenshots are included in Git.

Private GitHub main updated and visibility verified. README begins with the
working authenticated clone/local-bootstrap route, tested without public download.
Current LICENSE remains MIT; LICENSE-PLAN.md records the proposed noncommercial
and separately agreed commercial model, including unresolved PyQt constraints.

## Lumen interoperability

- [x] Shared reference/dispatch/history contract, validation and replay tests.
- [x] Files context actions and native source capture.
- [x] Target adapters, review and cold/warm delivery.
- [x] Wissen/Vault and application-aware backup paths.
- [x] Cross-app links, backlinks, tags, search, object activation.
- [x] Project, calendar, mail, reading and meeting specialized workflows.
- [x] Audio identity, interruption and routing.
- [x] Requirement-by-requirement acceptance, complete isolated suite, bilingual native checks and local installation.

334 Python checks: 332 passed, two optional calendar checks skipped in the system
runtime and covered by five passing Inbox-runtime checks. 25 English checks and
12 QML checks passed. The complete suite caught and fixed a Qt focus/event-filter
callback during window teardown; review also fixed fast snapshot activation.

Package 1.2.0-41 built. 42 production resources plus the URI launcher match source,
package and installed user bundle. All nine installed tools passed cold/warm
activation; installed URI/handoff/save-barrier/replay checks passed. Private
program backups and consistent copies of ten SQLite databases precede the update.
Optional runtimes and existing user windows were preserved. No push/publication.

The 100-item ledger documents remaining limits explicitly: offline backup status
requires exact-version checking; restored audio devices require manual assignment;
workspace context reopens up to eight references rather than a full desktop session.
Strict no-fallback audio is limited to the proven PipeWire/WirePlumber and device
configuration. Usage and evidence: docs/interop/USAGE.md and COVERAGE.md.

## Qt 6 / QML search pilot

- [x] Scope, isolated checkout, runtime and existing dependency boundaries.
- [x] Shared backend/job/voice compatibility with Qt 5 regression coverage.
- [x] QML search, conversation, permissions/questions, voice and theme handling.
- [x] Native runtime checks, visual inspection and reproducible comparison.
- [x] Optional installation, documentation and pilot delivery.


The combined source passes 333 of 338 Python checks; five optional CalDAV/Restic
integrations are skipped in the isolated system runtime. Four dedicated Qt 6
checks additionally cover real keyboard/mouse handling and local HTTP requests.
QML lint reports no warnings. Four themes, DE/EN, compact layout, approvals,
questions and voice states were rendered with synthetic content; the same QML
also rendered on the actual Wayland desktop. Installed cold/warm activation and
supervised restart restore a synthetic draft/session without re-sending it.

Package 1.2.0-42 includes the QML resources, shared services, translations and
optional native menu entry. A separate user bundle and optional Qt 6 runtime
provide the preview; production search, existing shortcuts and windows remain
available. Source/runtime assets were compared. SEARCH-PREVIEW.md documents
commands, boundaries and a five-sample benchmark: Qt 6 first frame 134.8 ms versus
109.4 ms, RSS 119.9 versus 91.1 MiB, completed search 267.8 versus 263.9 ms.
This is presentation flexibility with a measured startup/memory cost, not a
claimed speedup. No personal state, test captures or runtime wheels enter Git.

## Files startup responsiveness

- [x] Reproduce the standalone restored-folder stall on the native desktop.
- [x] Replace native per-file icon content detection with filename-only MIME
  matching and a bounded, theme-aware cache; retain link markers and bundled
  fallbacks for unavailable themes.
- [x] Use the same provider in listings, search and rebuilt network models.
- [x] Regression checks: three new tests, 16 focused tests passing; complete
  isolated suite: 335 passed, six optional CalDAV/Qt 6 checks skipped (341 total).

The native large-directory icon benchmark fell from 12.54 s to 0.11 s for roughly
9,500 entries. With restored settings the three-second window check now fires on
time with 22 GUI heartbeats, versus 13.19 s and one heartbeat before. The taskbar
launcher resolves to the current user bundle; the embedded Files page explicitly
starts at the assistant working directory instead of restoring the standalone
tabs. Diagnostic data and screenshots stay outside Git.

The three production files were installed into the existing user bundle after a
private program backup. The installed native window renders the affected folder
and responds normally (27 heartbeats by the three-second check). The exact command
used by the taskbar entry also starts successfully with the real profile and
records its first responsive-state checkpoint within one second. Existing user
settings and the optional search-preview bundle were preserved. No publication.

## Check crash reports with Lumen

- [x] Add an explicit “Mit Lumen prüfen” choice to the recovery dialog.
- [x] Open the native diagnosis action with report metadata and stderr only;
  keep recovery pending and discard inherited action prompts.
- [x] Start diagnosis in plan mode, treating logs as data and asking for evidence,
  uncertainty and next steps without changing files or replaying old work.
- [x] German/English translations and native desktop dialog-to-action checks.

Three new regression tests cover report selection, the recovery choice including
launch failure, and diagnosis mode/context. All 20 focused crash, assistant and
translation checks pass. A synthetic report was selected in the native recovery
dialog and passed through the actual application CLI parser to the action window
in both languages; its model boundary was intercepted, so no real report was sent.

The complete isolated suite passed 338 checks with six optional integrations
skipped (344 total). The existing local bundle received the action, translations
and required shared Qt adapter after a private program backup. The installed
German/English dialog and action flow passed the same native checks. Existing
windows need a restart to display the new choice. No push/publication.

### Diagnosis start regression

The installed action aborted when the real backend emitted its first working
status: the action-specific status table lacked `diagnose`, so its Qt callback
raised `KeyError`. The initial handoff smoke intercepted `send`, which hid this
missing transition. Add the diagnosis status and a generic fallback for future
actions. Replace that regression test's send mock with a local HTTP server so the
real request, status signals and completed result all run. Before the fix the
test captures `KeyError('diagnose')`; after it, all 20 focused checks pass.

The corrected resources are installed with a private program backup. Installed
German/English native checks now exercise recovery click, CLI parsing, the real
backend send/status path, HTTP and final result rendering. Only the external
model is replaced by the local test server; no personal report is transmitted.

Final isolated suite: 338 passed and six optional checks skipped (344 total).

## Contextual interoperability experience

- [x] Remove generic integration chrome; retain content actions and object drag.
- [x] Direct Files → Reader; focused Reader → Wissen review and source links.
- [x] Notebook → Vault setup, schedule and truthful status in existing controls.
- [x] German/English native flows, regression checks and local rollout.

Acceptance is recorded in SPEC-interop-experience.md.

Verified: 351 isolated tests (345 passed, six optional skips). Seven native
interaction checks pass in both German and English against the installed bundle:
context menu loading, direct Reader drops, Reader quote review/persistence/source
navigation, notebook edit flushing, backup status, new schedules and retry after
schedule failure. External backup commands/keyring calls use synthetic doubles in
the native setup checks; the suite also exercises real encrypted Restic backup and
restore. Native screenshots were inspected for both languages.

Reviewed source selection, unsaved edits, cancellation, idempotent schedule retry,
menu accessibility, translations and saved-data compatibility. Installed 18
runtime files with checksum verification and a private rollback copy under
`~/.local/state/lumen/manual-updates/contextual-interop-20261004-000203`.
Existing user windows were left open; reopening them loads the new UI.

# Qt 6 migration

- [x] All Lumen GUI modules and shared services use PySide6/Qt 6.
- [x] Production QML search behind existing launcher, panel and shortcuts.
- [x] Shared runtime selector, worker interpreters and installer/package dependencies.
- [x] Regression suite:349 tests,344 passed,5 optional integrations skipped.
- [x] Native DE/EN rendering, Wayland, cold/warm launches, crash/draft recovery.
- [x] Separate review of nonmechanical runtime and installation changes.
- [x] Package1.2.0-43 built;219 packaged entries and237 installed resources verified.
- [x] Current user bundle updated after program/settings/SQLite backups; native
  Lumen, Files and the production search run with PySide6. Search state and the
  preview alias were checked after handover. Existing desktop configuration kept.
- [x] Fresh-profile Plasma installation and repeated setup passed. Installed tools
  passed cold/warm activation, file forwarding, handoff, save and replay checks.
- [x] Setup/shortcut refresh and newly generated Sound/Vault services use the chosen
  interpreter; known existing service templates migrate with a backup. Their
  focused regression checks passed after the full349-test suite.

- [x] Personal learning: language-independent LLM contract, explicit correction metadata, confirmed solution references, bounded recall and existing consent/conflict protection.
- [x] Wissen: profile over global memories, correction and solution filters, same editor/history/forget actions, DE/EN native views.
- [x] Verify storage, backend, native UI, language, persona and MCP regressions; multilingual live-provider checks passed.
- [ ] Finish user/system package rollout and private GitHub update.


- [x] Recommended five-step setup with expandable customization; existing values preserved.
- [x] Explicit personality/memory choices, safe install/retry/skip flow and DE/EN copy.
- [x] 56 setup, privacy, persona, settings, speech-output and localization tests;
  native standard pages inspected at 780×690 and 600×540 in both languages.


- [x] Lumen Studio: selected reference implemented as native sidebar, conversation
  and optional preview, with actual sessions and shared asynchronous file workers.
- [x] Preserve CLI/D-Bus pages, permissions, voice, persona, memory, recovery and
  output actions; existing Files/Search surfaces stay intact.
- [x] 55 tests passed, including real image/text/PDF previews, compact navigation,
  history, permission replies, Markdown safety and no replay on recovery.
- [x] Native screenshots inspected in DE/EN, four themes and compact dimensions;
  synthetic demo files only. Reference and renders remain in ignored artifacts/studio.

## Wissen timestamps (2026-10-05)

- [x] Show local creation/change dates below the note title and on memory profile entries.
- [x] Preserve creation in portable note metadata, edits, history and Vault restoration.
- [x] Display existing file modification times without rewriting old notes or inventing creation dates.
- [x] Verify autosave, unchanged saves, frontmatter, imports, copied notebooks and restoration.
- [x] Install six runtime files with a private rollback copy and verify the installed DE/EN UI.

All 73 focused Wissen, memory, interoperability and localization checks passed
their assertions. The isolated Vault module then crashes during Qt/Python
shutdown; the same 18 passing checks followed by the same shutdown crash reproduce
on the unmodified baseline. The extended Vault restore test also passes alone.
Native tests against the installed bundle pass in German and English, including
autosave, legacy notes, memory entries and the profile. Both narrow and wide
window renders were inspected. The program rollback copy is under
`~/.local/state/lumen/manual-updates/wissen-timestamps-20261005-003512`.

The complete 457-test run has two existing errors (Vision launcher JSON output
and the setup dialog's second QApplication), both reproduced by the unmodified
453-test baseline. A WebDAV transfer failed once in the full run and passes when
rechecked alone against the changed tree; it also passes in the baseline. Two
optional integrations are skipped. These wider-suite limitations remain separate
from the passing timestamp checks; no unrelated runtime changes were made.
