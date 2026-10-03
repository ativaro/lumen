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


## Eigenständige Desktop-Werkzeuge, 2026-10-02
Siehe CAPABILITIES-tools.md und SPEC-meetings/household/workbench/radio.md. Die vier angenommenen Anwendungen werden in dieser Reihenfolge als eigene native Fenster gebaut, mit privater SQLite-Speicherung, gemeinsamen Themes und vorhandener Sprach-/KI-Laufzeit. Jede Scheibe erhält Funktionsprüfung und UI-Rendering; anschließend Portable Installer und Arch-Paket aktualisieren.

## Einzeiler → lokale Installation → Wizard, 2026-10-02

Ziel: Ein Befehl lädt Lumen über HTTPS, ergänzt auf Arch/CachyOS die native
Basis und installiert die Anwendungen im Benutzerprofil. Anschließend öffnet der
vorhandene Qt-Wizard auch dann, wenn er früher schon abgeschlossen wurde.
Plasma 6 muss bereits laufen; root-/Headless-Aufrufe scheitern vor Änderungen.
Abgebrochene Downloads/Paketinstallationen dürfen keinen Wizard-Erfolg vortäuschen.
Persönliche Einstellungen und Modelle bleiben erhalten. Desktop-Aktivierung mit
Theme/Wallpaper/Panel-Sicherung erfolgt ausschließlich per Schaltfläche im Wizard.

Umsetzung: `bootstrap.sh` verwendet `install.sh`; `setup_dialog.py` ergänzt eine
Desktop-Seite, `lumen_setup.py` verwendet die vorhandene Desktop-Einrichtung.
Stil: vorhandene Bash-Funktionen und Qt-Widgets, etwa `if groups: self.start_job('packages', groups)`.
Prüfung: `bash -n bootstrap.sh install.sh`; isolierte unittest-Tests mit simulierten
Download-/Paketbefehlen, echte Benutzerinstallation und Wizard-Rendering im Testprofil,
`/usr/bin/python3 -m unittest discover -s files -v`; keine Installation oder
Paneländerung im aktiven Benutzerprofil zum Testen. Danach portable Quellen und
Anleitung veröffentlichen. Keine neue Distribution-Unterstützung oder KI-Zugangsdaten.
# Lokale Foto- und Systemfunktionen, 2026-10-03

Angenommener Umfang: persistente mehrstufige Bildvorschauen mit Nachbar-Prefetch;
lokale semantische Bildsuche mit expliziter Ordnerwahl; Foto-Aufräumvorschläge
(Serien, Unschärfe, Screenshots); Hardware-Sensoren; automatische Schonung bei
Spielen/Aufnahmeprogrammen. Native Qt-Oberflächen, vorhandene Themes und
Papierkorb-/Jobpfade wiederverwenden. Keine automatische Löschung oder private
Ordnerindizierung. Modelle und Indizes bleiben im Benutzerprofil.

Reihenfolge: Vorschaucache → gemeinsame Aktivitäts-/Hardware-Erkennung → lokale
Bildsuche samt Einrichtung → Foto-Aufräumhilfe → integrierte Prüfung und Auslieferung.
Numen hat widersprüchliche Lizenzangaben; seine Konzepte werden eigenständig über
Linux-Schnittstellen umgesetzt. Keine Übernahme von AGPL-Quelltext. Pictus dient
als Referenz für Cachegrößen, lokale Vektorsuche und erklärbare Fotovorschläge.

Abnahme: Cacheinvalidierung nach Bearbeitung, begrenzter Speicher, unveränderte
Originale; echte lokale Modellinferenz; abbrechbare Suche/Analyse mit sichtbarem
Wartegrund; keine vorselektierten Löschungen; fehlende Sensoren nicht als Null;
Fixtures für Prozess-/Sensorparser, synthetische Fotos, native UI-Rendering,
vollständige isolierte Suite und portables Paket. Laufende Benutzerfenster bleiben
offen. Daten, Modelle und Messwerte werden nicht eingecheckt.
# Vault und Inbox, 2026-10-03

Siehe SPEC-vault-inbox.md. Bestehende native ToolWindow-/Library-/Job-Bausteine
verwenden. Reihenfolge: Secret-Service → Vault-Backend mit realem Restore-Test →
Vault-UI/Zeitplan → Inbox-Protokolle mit lokalen Servern → Inbox-UI → Installer,
vollständige Tests und Bereitstellung. Keine Benutzerkonten oder persönlichen
Backup-Ziele ohne Auswahl im jeweiligen Einrichtungsdialog aktivieren.

# Reader und Sound, 2026-10-03

Reader zuerst als vollständiger Schnitt mit Parser-Unterprozess, nativer Ansicht,
Lesestand/Notizen und bestehender Sprache/Wissen-Anbindung; prüfen und committen.
Danach Sound mit pactl/PipeWire, nativer Streamsteuerung und expliziter Automatik;
Prüfung an isolierten virtuellen Audioquellen. Abschließend Gesamtprüfung,
Benutzerinstallation, Paket und Dokumentation. Spezifikation: SPEC-reader-sound.md.

# Lumen Wissen, 2026-10-03

Angenommenes Konzept: eigene native Notiz-App auf Markdown, mit Verknüpfungen,
Tags, Quellen, Wissenskarte und expliziten Fragen. SPEC-wissen.md ist der Vertrag.
Erst sichere Dateispeicherung/Migration prüfen; dann vollständige native Oberfläche
und Quellenaktionen; schließlich Integration, Paket, Benutzerinstallation und Git.
