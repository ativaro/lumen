# Lumen Vault und Inbox

Beide Apps erscheinen im Anwendungsmenü und verwenden das aktive Lumen-Theme.
Die vollständige Installation und `install-tools.py` enthalten beide Starter.
Im nativen Einrichtungsassistenten **Vault vorbereiten** beziehungsweise **Inbox
vorbereiten** wählen; `libsecret` stellt die Verbindung zur entsperrten KWallet
oder einem anderen Secret Service her. Die optionalen Laufzeiten benötigen kein
sudo. Persönliche Konten und Sicherungspläne gehören nicht zum Distributionspaket.

## Vault

Im nativen Vault führt **Sicherung einrichten** durch vier Schritte:

1. **Was schützen?** Meine Dateien, Mein Lumen und Mein Tresor sind mit vorhandenen
   Quellen vorausgewählt. Einzelne Quellen abwählen oder lokale/NAS-Ordner ergänzen.
   Der Tresor wird ausschließlich als verschlüsselte KDBX-Datei kopiert.
2. **Wohin?** USB/Ordner wählen oder NAS suchen. Bekannte Files-Verbindungen und
   angekündigte SMB-Server erscheinen automatisch; manuelle Servereingabe bleibt
   möglich. Freigabe wählen, Benutzername/Passwort eingeben, bei Bedarf **Zugang
   merken** aktivieren und testen. Neue Archive erhalten einen eigenen Unterordner.
3. **Automatisch und verschlüsselt:** Täglich ist vorgeschlagen, wöchentlich/manuell
   wählbar. Den erzeugten Sicherungsschlüssel außerhalb des Sicherungsziels speichern
   und seine unabhängige Aufbewahrung bestätigen. Für automatische Läufe liegt er
   zusätzlich im System-Schlüsselbund. Das Tresor-Master-Passwort bleibt separat nötig.
4. **Prüfen und starten:** Erst eine erfolgreiche Sicherung samt Wiederherstellung
   einer kleinen Prüfdatei schaltet den Zeitplan frei. Bei einem Fehler **Einrichtung
   abschließen** wiederholen. Drei Karten zeigen den Stand der gewählten Bereiche.

**Stände laden → Wiederherstellen** stellt immer in einen neuen privaten
`Lumen-Wiederherstellung-*`-Ordner wieder her. Originaldateien bleiben erhalten.
Auf einem neuen Rechner führt auch die Lumen-Ersteinrichtung direkt zu Sicherungen.
Der wiederhergestellte Tresor liegt im Anwendungspaket unter
`native-vault/vault.kdbx`; vor dem Anlegen eines neuen Tresors über **Verschlüsselte
Sicherung wiederherstellen** mit seinem ursprünglichen Master-Passwort öffnen.
Ein bereits vorhandener Tresor wird nicht ersetzt. Weitere Sicherungsziele lassen
sich mit demselben Wizard als eigener Plan einrichten.

Ohne installierte native Tresor-Oberfläche bleibt die bisherige Python-Sicherungsapp
mit manueller Quell-/Zielauswahl verfügbar.

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

## Manueller Tresorabgleich mit Lumen Server

Der native Tresor kann verschlüsselte KDBX-Fassungen über einen gekoppelten Server
austauschen. Im Server bei **Geräte → Fähigkeiten verwalten** ausdrücklich
**Verschlüsselten Tresor abgleichen** aktivieren; die normale Sicherungsfreigabe
reicht dafür nicht aus. Im entsperrten **Vault → Einstellungen → Serverabgleich…**
Server/Konto prüfen und **Lokale Fassung veröffentlichen** wählen.

Auf einem neuen Desktop bietet die leere Tresoransicht **Tresor von Lumen Server
übernehmen…** an. Das ursprüngliche Hauptpasswort wird ausschließlich lokal im
nativen Broker verarbeitet. **Fassung übernehmen** authentifiziert die Datei und
ersetzt bewusst den vollständigen aktiven Tresor. API-/MCP-Freigaben müssen danach
auf diesem Gerät neu erteilt werden. Gleichzeitige Veröffentlichungen bewahren
beide Serverfassungen; kein stilles Überschreiben des neueren Serverstands.

Die verdrängte lokale Fassung bleibt als `sync-before-<SHA256>.kdbx` im privaten
Tresorordner erhalten, unabhängig von der rotierenden `previous.kdbx`. Empfangene
Dateien liegen verschlüsselt unter `sync-incoming-<UUID>.kdbx`. Diese Kopien werden
nicht automatisch gelöscht. Servergrenzen: 64 MiB je Fassung, 200 Fassungen,
512 MiB pro Person; alte Serverfassungen gezielt im Dialog entfernen.

**Einträge zusammenführen** ergänzt die gewählte Fassung lokal: unbekannte IDs
werden übernommen, abweichende vorhandene Einträge als `· Sync conflict` kopiert,
inklusive Verlauf und benutzerdefinierter Felder. Identische bereits übernommene
Kopien werden nicht erneut angelegt. Lokale Löschmarkierungen bleiben bestehen;
eine wieder auftauchende entfernte ID erhält eine neue Konfliktkopie. Auslassungen
auf dem anderen Gerät löschen nichts. Alle API-/MCP-Freigaben werden deaktiviert.
Danach zeigt der Dialogabschluss die Anzahl ergänzter Einträge und Konfliktkopien.
Zum Teilen des Ergebnisses den Serverabgleich erneut öffnen und ausdrücklich
**Lokale Fassung veröffentlichen** wählen.

Dieser konservative Eintragsabgleich wählt keinen Gewinner anhand der Uhrzeit;
auch einseitige Änderungen können deshalb eine Konfliktkopie erzeugen. Beide
Fassungen lassen sich mit der normalen Bearbeitung prüfen und bereinigen.
Neue Ordner werden einschließlich Unterordnern, leeren Ordnern, Reihenfolge und
Metadaten ergänzt. Bereits vorhandene Ordner sowie Tresoreinstellungen bleiben
lokal; entfernte Umbenennungen/Verschiebungen vorhandener Ordner werden noch
nicht übernommen. Erforderlich ist derselbe Tresorursprung. Lokal gelöschte Ordner,
widersprüchliche Kennungen, Anhänge/eigene Symbole oder überschrittene Formatgrenzen
werden vor jeder Ersetzung abgewiesen. Das fertige verschlüsselte Ergebnis wird
vor dem Schreiben nochmals authentifiziert und geöffnet.
`LumenSyncSource` ist ein internes, verschlüsseltes Herkunftsfeld; der
Konflikthinweis wird nur in der Liste ergänzt, Originaltitel bleiben erhalten.
Vorerst kein automatischer Hintergrundabgleich. Restic-Sicherungen bleiben unabhängig. Bestehende
Prerelease-/Auditgrenzen des nativen Tresors gelten unverändert.

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

## Automatischer verschlüsselter Servertransport

Vault → Einstellungen → Serverabgleich → Automatik aktivieren. Voraussetzung ist
ein gemeinsamer lokaler/Serverstand und die Gerätefreigabe `vault_sync`. Danach läuft
der vorhandene Desktop-Verbindungsdienst auch ohne Vault-Fenster oder Entsperren.
Lokale Änderungen werden verschlüsselt veröffentlicht, Serverfassungen verschlüsselt
empfangen. Neue Fassungen im Tresor prüfen/übernehmen oder zusammenführen; lokale
aktive Dateien werden im Hintergrund nie ersetzt. Konflikte pausieren das Senden,
weitere Serverstände können weiterhin empfangen werden. Ausgänge verlorener Uploads
werden anhand gespeicherter UUIDs geprüft, unklare Ergebnisse stoppen das Senden.
Konto-/Token-/Profilwechsel erfordern neues Aktivieren. Keine persönlichen Daten
werden durch Installation/Update automatisch freigegeben. Standard bleibt aus.
