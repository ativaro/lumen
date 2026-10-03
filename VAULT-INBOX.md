# Lumen Vault und Inbox

Beide Apps erscheinen im Anwendungsmenü und verwenden das aktive Lumen-Theme.
Die vollständige Installation und `install-tools.py` enthalten beide Starter.
Im nativen Einrichtungsassistenten **Vault vorbereiten** beziehungsweise **Inbox
vorbereiten** wählen; `libsecret` stellt die Verbindung zur entsperrten KWallet
oder einem anderen Secret Service her. Die optionalen Laufzeiten benötigen kein
sudo. Persönliche Konten und Sicherungspläne gehören nicht zum Distributionspaket.

## Vault

1. **Sicherung einrichten**: Namen, bereits eingebundenen USB-/NAS-Zielordner und
   Quellordner auswählen. Das Ziel einer neuen Sicherung muss leer sein und darf
   nicht innerhalb der Quellen liegen. Lumen-/KDE-Einstellungen sind optional.
2. Ein langes Sicherungspasswort festlegen und außerhalb des Rechners aufbewahren.
   Der lokale Schlüsselbund allein hilft bei Rechnerverlust nicht weiter.
3. **Sicherungsvorschau**, anschließend **Jetzt sichern**. Restic verschlüsselt und
   dedupliziert die Daten. Unvollständige Sicherungen werden als Fehler gemeldet.
4. **Stände laden** → Inhalt ansehen oder einen Stand wiederherstellen. Das Ziel
   ist immer ein neuer privater `Lumen-Wiederherstellung-*`-Ordner; Originaldateien
   werden nicht überschrieben. Ein abgebrochener Restore bleibt als unvollständiger
   Ordner erhalten. Dateien können danach bewusst zurückkopiert werden.

Ein vorhandenes Restic-Repository lässt sich mit seinem bisherigen Passwort
übernehmen, auch ohne Quellordner für eine reine Wiederherstellung. Das Programm
prüft die Repository-ID vor jedem Lauf. Bei einem anderen oder nicht erreichbaren
Datenträger erfolgt kein Ersatzbackup in ein neues lokales Verzeichnis.

Tägliche/wöchentliche Sicherungen aktivieren den Benutzer-Timer `lumen-vault.timer`.
Er prüft alle 15 Minuten auf fällige Pläne, wartet bei gesperrtem Schlüsselbund,
aktiven Spielen/Aufnahmen oder fehlendem Medium und hält den Grund im Plan fest.
Der Benutzer muss angemeldet sein. Archivierte Pläne werden nicht ausgeführt.
Manuelle Pläne starten keinen Timer; nach Deaktivierung des letzten Zeitplans wird
er gestoppt. Es gibt kein automatisches Löschen alter Sicherungsstände.

**Struktur prüfen** prüft Metadaten; **Alle Sicherungsdaten prüfen** liest auch die
verschlüsselten Datenblöcke. Vault erstellt Dateisicherungen, keine Btrfs-Snapshots
und kein bootfähiges Systemabbild.

## Inbox mit Proton

Proton Mail benötigt die separat installierte, angemeldete **Proton Mail Bridge**
und einen dafür geeigneten bezahlten Proton-Tarif:
[offizielle Linux-Anleitung](https://proton.me/support/bridge-for-linux).
Die normale Proton-Mail-Desktop-App ersetzt Bridge nicht.

1. In Bridge das Konto anmelden und dessen IMAP-/SMTP-Zugangsdaten anzeigen.
2. Das öffentliche TLS-Zertifikat in den erweiterten Bridge-Einstellungen
   exportieren. Nicht den privaten Schlüssel auswählen.
3. In Inbox **Konto hinzufügen → Proton Mail Bridge**: Absenderadresse,
   Bridge-Benutzername und **Bridge-Passwort** eintragen, Zertifikatsdatei wählen.
   Das normale Proton-Passwort gehört nicht in Inbox.
4. Speichern und **Aktualisieren**. Die Vorlage verwendet 127.0.0.1 mit IMAP-Port
   1143 und SMTP-Port 1025, jeweils STARTTLS; unter Serverdetails anpassbar.
   Vor der Anmeldung muss das Zertifikat zum gespeicherten Fingerabdruck passen.
   Bei einem Zertifikatswechsel das exportierte Zertifikat erneut auswählen.

Proton Calendar bietet aktuell kein CalDAV. Für lesenden Zugriff in Proton einen
privaten Kalender-Freigabelink erstellen und in Inbox **Kalender-Abo (ICS / Proton)**
wählen. Der vollständige private Link liegt im Schlüsselbund. Termine/Serien werden
lokal für die letzten 30 Tage und kommenden 12 Monate aufgelöst.
[Proton-Kalenderfreigabe](https://proton.me/support/share-calendar-via-link)

## Andere Mail- und Kalenderanbieter

- IMAP/SMTP unterstützen TLS direkt und STARTTLS; beide Server verwenden dieselben
  Anmeldedaten. Externe Server müssen ein gültiges Zertifikat haben. OAuth-only-
  Anbieter benötigen gegebenenfalls ein App-Passwort; eine OAuth-Anmeldung ist
  hier noch nicht enthalten.
- CalDAV: endgültige HTTPS-Adresse und Zugangsdaten eintragen, **Kalender auswählen**
  und aktualisieren. Für mehrere Kalender desselben Anbieters jeweils einen Eintrag
  anlegen. Einfache Termine lassen sich erstellen und ändern; ETags verhindern das
  Überschreiben zwischenzeitlicher Änderungen. Serien, ganztägige Termine und
  Einladungen werden angezeigt, aber beim Anbieter bearbeitet. Bestehende Alarme
  und weitere Eigenschaften einfacher Termine bleiben beim Bearbeiten erhalten.
- Einträge werden nur über **Aktualisieren** abgerufen. Neueste 200 Nachrichten,
  maximal 20 MiB pro Nachricht und 64 MiB je Ordner; Übersprungenes ist sichtbar.
  Andere Ordner können nach **Ordner laden** gewählt werden. Die Suche arbeitet
  ausschließlich im lokalen Bestand. Inbox verändert keine Gelesen-Markierungen,
  verschiebt oder löscht keine Nachrichten auf dem Server.
- Anhänge werden nur auf ausdrücklichen Klick gespeichert; bestehende Dateien
  werden nicht überschrieben. Nachrichten erscheinen als Text ohne Trackingbilder.
- Entwürfe werden automatisch lokal gespeichert. **Senden** verlangt eine konkrete
  Bestätigung. Bei unklarer SMTP-Bestätigung zuerst beim Anbieter nachsehen; keine
  automatische Wiederholung. Eine eigene IMAP-Kopie in „Gesendet“ wird nicht erzeugt
  (dies hängt von der serverseitigen Verarbeitung des Anbieters ab).
- Aufgaben bleiben lokal. **Mit Lumen entwerfen** übermittelt nur nach ausdrücklicher
  Auswahl den Nachrichtentext an den eingerichteten KI-Provider. Ergebnisse werden
  als Vorschlag angezeigt, Antworten als bearbeitbare Entwürfe; kein automatischer
  Versand und keine automatischen Kalendereinladungen.

Konten, Nachrichten, Kalender und Entwürfe liegen mit privaten Dateirechten unter
`~/.local/share/lumen-tools/inbox`; Sicherungspläne unter `.../vault`.
Der Mail-Cache ist lokal nicht zusätzlich verschlüsselt; für Schutz bei Verlust des
Rechners ist die Datenträgerverschlüsselung zuständig. Zugangsdaten liegen separat
im System-Schlüsselbund. **Konto entfernen** entfernt den lokalen Kontobestand und
seine Zugangsdaten; Inhalte beim Anbieter bleiben erhalten.

## Verifikation

`PYTHONPATH=files QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s files -v`
prüft die lokale Logik und nativen Dialoge. `LUMEN_TEST_RESTIC` auf eine Restic-Binärdatei
setzen für den echten temporären Backup-/Restore-Test. CalDAV zusätzlich im
optionalen Environment prüfen:

```sh
PYTHONPATH=files ~/.local/share/lumen/inbox-env-v1/bin/python -m unittest files/test_inbox.py -v
```

Die Mail-/Kalendertests verwenden ausschließlich lokale TLS-Testserver und
`example.invalid`-Adressen; sie benötigen keine realen Konten.
