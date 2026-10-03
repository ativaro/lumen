# Lumen Vault und Inbox

Angenommener Auftrag: zwei eigenständige native Apps; Vault zuerst, Inbox mit
Proton-Mail-Bridge sowie allgemeinen IMAP-/SMTP- und CalDAV-Konten. Vorhandene
Qt-Themes, ToolWindow, private Library und abbrechbare Jobs wiederverwenden.

| Modul | Verantwortung | Abhängigkeit |
|---|---|---|
| secrets | Zugangsdaten im System-Secret-Service, keine Klartext-Konfiguration | secret-tool/KWallet |
| vault | verschlüsselte Sicherungspläne, Vorschau, Verlauf, Prüfung, Wiederherstellung | restic, secrets |
| inbox | lokale Postfachansicht, Entwürfe, Kalender und Aufgaben | IMAP/SMTP, CalDAV/ICS, secrets |

## Vault

- USB-/NAS-/lokalen Zielordner und Quellen ausdrücklich auswählen; optional
  Lumen-/KDE-Benutzereinstellungen. Kein Root, keine Partitionen/Bootloader.
- Restic verschlüsselt und dedupliziert. Vorschau vor erster Sicherung, Snapshots
  und enthaltene Dateien anzeigen. Dateiauswahl oder kompletter Stand in neuen,
  eigenen Wiederherstellungsordner; keine vorhandenen Dateien überschreiben.
- Tägliche/wöchentliche Benutzer-Zeitpläne erst nach Aktivierung. Fehlendes Medium
  oder gesperrter Schlüsselbund ergibt sichtbaren Fehler, keinen falschen Erfolg.
- Repositoryidentität, Quell-/Zielüberschneidung, Dateistatus und Job-Sperre prüfen.
  Metadatenprüfung und vollständige Datenprüfung unterscheiden. Kein automatisches
  Löschen alter Sicherungen. Passwort extern aufbewahren; Schlüsselbund allein
  genügt nicht für Wiederherstellung nach Rechnerverlust.

## Inbox

- IMAP/SMTP über TLS; Proton-Vorlage mit lokalen Bridge-Adressen und separat
  bestätigtem/exportiertem Zertifikat. Bridge-Zugangsdaten statt Proton-Passwort.
  Bridge selbst benötigt laut Proton einen bezahlten Tarif und Benutzeranmeldung.
- Kontenübergreifender Posteingang, Threads, lokale Suche, Nachricht als sicherer
  Text, Anhänge ausdrücklich speichern, lokale Entwürfe und explizites Senden.
- CalDAV-Kalender auswählen, Termine lesen/erstellen/bearbeiten; Änderungen erst
  nach Prüfung, ETags schützen vor fremden Änderungen. ICS-Abos bleiben lesend.
  Proton Calendar unterstützt kein CalDAV; dafür ICS-Abonnement anbieten.
- Aufgaben aus Nachrichten lokal speichern, Antwort-/Termin-/Aufgabenvorschläge
  mit vorhandener Lumen-Anbindung erst nach ausdrücklichem Klick. Nachrichtentext
  ist untrusted data; keine Werkzeuge, automatischen Antworten oder Einladungen.
- Keine Konten still aus anderen Apps übernehmen. Einrichtung/Passwörter erfolgen
  in den nativen Dialogen. Keine echten Nachrichten beim Entwickeln versenden.

## Grenzen und Abnahme

Trust boundaries: externe Nachrichten/Anhänge/ICS/DAV-Antworten, Pfade auf NAS,
Restic-Prozessausgabe, KI-Vorschläge. Anmeldedaten nur im Schlüsselbund; SQLite
mit privaten Rechten, keine Geheimnisse in Logs/argv. TLS-Prüfung für externe
Server, Bridge-Vertrauen nur für Loopback und bestätigtes Zertifikat. Begrenzte
Netzwerkantworten, Zeitlimits, keine automatischen externen Bilder/HTML-Skripte.

Prüfung: reale Restic-Sicherung/-Wiederherstellung im temporären Profil, falsche
Passwörter/fehlende Ziele/Abbruch; lokale TLS-IMAP-/SMTP-/DAV-Fixtures statt echter
Konten; Kalenderkonflikte, bösartige Anhänge und sichere Textdarstellung. Native
Screenshots und Start/Schließen, vollständige isolierte Suite, portable Installer,
Paket und Benutzerinstallation. Persönliche Daten und Testartefakte nie ins Git.

Quellen: https://proton.me/support/bridge-for-linux,
https://proton.me/support/subscribe-to-external-calendar,
https://restic.readthedocs.io/en/stable/,
https://caldav.readthedocs.io/.
