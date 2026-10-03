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
