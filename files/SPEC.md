# Lumen Files

Native Linux-Dateiverwaltung mit Schwerpunkt auf schneller Dateinamensuche und brauchbaren Vorschauen. Deutsch, dunkle ruhige Oberfläche, Systemschrift, vorhandenes PyQt5 und GIO; keine neuen Pakete.

## Akzeptanz
- Echte lokale Ordner, Favoriten, Tabs, Verlauf, versteckte Dateien und Typfilter.
- Seitliche Maustasten navigieren über allen Fensterbereichen im Verlauf, in der Galerie durch Bilder; andere Dialoge lösen keine Hintergrundnavigation aus. Zehn Orte passen bei 1000 × 640 Pixeln ohne Scrollen in die Seitenleiste.
- Suche ab 250 ms Eingabepause, rekursiv, laufende Treffer, abbrechbar; Dateinamen ohne Beachtung der Großschreibung. Keine Symlink-Rekursion. Maximal 5.000 Treffer mit sichtbarem Hinweis. Kein Hintergrundindex, keine Volltextsuche.
- Auswahl zeigt Bilder, blätterbare PDFs, Text/Code und Video-Standbilder; Leertaste öffnet große Vorschau. Decoder laufen außerhalb der Oberfläche mit Zeitlimit. Keine automatische Ausführung, kein HTML-Rendering.
- Öffnen, Ordner erstellen, Umbenennen, Kopieren, Ausschneiden/Einfügen, bestätigter Papierkorb. Kein stilles Überschreiben. Fehler sichtbar, große Kopien im Hintergrund.
- Startmenüeintrag und Startbefehl. Standard-Dateimanager bleibt eine gesonderte Nutzereinstellung.

## Struktur und Befehle
`app.py`: Oberfläche; `core.py`: Suche/Dateioperationen; `preview.py`: Vorschau; `test_lumen.py`: ausführbare Prüfungen; `style.qss`: Gestaltung.

Start: `/usr/bin/python3 /home/example/Documents/work/opencode-lumen/files/app.py`
Test: `cd /home/example/Documents/work/opencode-lumen/files && QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest -v`
Prüfung: `/usr/bin/python3 -m compileall -q /home/example/Documents/work/opencode-lumen/files`

## Stil und Grenzen
Python, vier Leerzeichen, kleine direkte Funktionen: `def valid_name(name): ...`. Native Qt-Widgets und Standardbibliothek zuerst. Tests mit unittest und temporären Verzeichnissen, keine Nutzerdaten verändern. Decoder begrenzen Lesevolumen und Laufzeit. Keine Systemkonfiguration, Fremdprojekte oder Standardzuordnungen ändern. Versionskontrolle lokal.

## Netzwerkverbindungen
- Verbindungsdialog für SMB, SFTP, WebDAV (HTTP/HTTPS), FTP und NFS; UNC-Adressen und direkte URL-Eingabe über Strg+L.
- Vorhandenes KIO-FUSE über asynchrones D-Bus nutzen. Keine Root-Mounts und keine neue Protokollimplementierung.
- KDE übernimmt Anmeldung. Lumen speichert ausschließlich validierte Serveradressen ohne Passwort; fehlgeschlagene Verbindungen nicht speichern.
- Gemerkte Server in der Seitenleiste, Netzwerkadressen in Pfadleiste und Verlauf statt flüchtiger Mountpfade. Verbindungen im neuen Tab und nach Neustart wieder öffnen.
- Bestehende Dateiaktionen, Suche und Vorschauen auf verbundenen Verzeichnissen wiederverwenden. Papierkorb nur wenn das Dateisystem ihn unterstützt, niemals endgültiges Löschen als Ersatz.
- Verbindung im Hintergrund, Abbruch der wartenden Oberfläche und sichtbare Fehler. Späte Antworten dürfen den inzwischen gewechselten Tab nicht umleiten.
- Prüfen: Adressvalidierung, Passwortschutz, Fehler/Abbruch, persistierte Orte und echte lokale WebDAV-Verbindung mit Lesen/Schreiben/Vorschau; keine fremden Server verändern.

## Bildarbeit und Speicheranalyse
- Tabs stehen über Suche, Dateiaktionen und Pfadnavigation. Der automatische Eintrag `/mnt/games` entfällt; Dateien und Mount bleiben unverändert.
- Bilder per Doppelklick oder Leertaste in einer großen Galerie öffnen. Pfeiltasten, Nachbarbilder vorladen, Zoom/Pan, Vollbild, Drehen, Spiegeln und Undo.
- Bearbeitung explizit speichern; JPEG/PNG/WebP, keine Animationen oder Symlinks überschreiben. Original vor jedem Speichern sichern; gleichzeitige Änderungen erkennen. Papierkorb nach Bestätigung, anschließend nächstes Bild. Kein permanentes Löschen.
- Speicheranalyse für den aktuellen oder gewählten Ordner: sortierbarer Baum mit Größen und Anteilsbalken, Unterordner bei Bedarf analysieren, Abbruch, sichtbare Zugriffsfehler. GNU du für belegten Platz oder Dateigröße, keine Symlink-Rekursion und keine fremden Dateisysteme durchlaufen.
- Prüfen: Layoutposition, Bildfolge/Cache, Rotation/Spiegelung/EXIF/Sicherungen/Kollisionen, Papierkorb, Größenwerte mit Sparse-/Hardlink-/Symlink-Dateien und Abbruch; Netzwerkregressionen erhalten.

## Native Lumen-Integration
- Gemeinsames Chat-Panel mit der eigenständigen Lumen-App; toolbar / Strg+J und Kontextmenü öffnen es im Dateimanager.
- Sichtbarer Arbeitsordner und alle ausgewählten Pfade; native Antworten, Abbruch, Freigaben und Rückfragen.
- „Lesen & prüfen“ nutzt den Plan-Agenten, „Aufgaben erledigen“ den Build-Agenten.
- Bestehende OpenCode-Konfiguration und globale Anweisungen bleiben erhalten; keine Terminal-Fenster oder gemeinsamen temporären Chatdateien.
- Gemeinsame Implementierung: `assistant.py` und `assistant_backend.py`; API-/Formulartest in `test_assistant.py`.

- „Erklären“, „Fehler beheben“ und „Änderungen prüfen“ wirken als Dateiaktionen:
  Titel, Auswahl, Fortschritt und Ergebnis statt eines vorbereiteten Chat-Auftrags.
  Native Freigaben/Fragen, Abbrechen/Retry, Kopieren/Schließen und passende Folgeaktionen.
  Mehr Details und Ergebnis prüfen lesen ausschließlich; freier Chat bleibt separat.
