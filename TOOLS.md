# Eigenständige Desktop-Werkzeuge

Die Werkzeuge werden mit Lumen installiert, haben aber eigene Fenster und
Einträge im Anwendungsmenü. Kein Terminal, keine zusätzliche Weboberfläche.
Sie verwenden die vier Lumen-Themes und die vorhandene Einrichtung.

| Anwendung | Start | Ablauf |
|---|---|---|
| Lumen Meeting-Werkstatt | `lumen-meetings` | Aufnahme importieren → lokal transkribieren → Zeitstelle anklicken → Ergebnisse vorschlagen → korrigieren/exportieren |
| Lumen Digitaler Haushalt | `lumen-household` | Gerät/Vertrag anlegen → Daten und Fristen eintragen → Belege/Handbücher hinzufügen → durchsuchen/öffnen |
| Lumen Projekt-Werkbank | `lumen-workbench` | Projekt anlegen → Notizen und Fragen festhalten → Dateien, Ordner und Webseiten verknüpfen |
| Lumen Persönliches Radio | `lumen-radio` | Ausgabe anlegen → Artikel/Dokumente/Text auswählen → Hörskript erzeugen und prüfen → lokal vertonen → abspielen/exportieren |

## Ohne Administratorrechte installieren

Wenn die Lumen-Abhängigkeiten bereits vorhanden sind, nur die vier Werkzeuge
für den aktuellen Benutzer installieren:

```bash
./install-tools.py
```

Dies installiert eine eigene Laufzeitkopie unter
`~/.local/share/lumen-tools/runtime/`, vier Starter in `~/.local/bin/` und
Menüeinträge samt Icons. Bibliotheken, Panels und die laufenden Lumen-Fenster
werden dabei nicht verändert. Die vorhandenen Sprachmodelle und Einstellungen
werden weiterverwendet. Nach einer späteren Systeminstallation rufen die lokalen
Starter automatisch die jeweilige Anwendung unter `/usr/bin/` auf.
Die vollständige Installation auf einem frischen System benötigt weiterhin die
im Haupt-README beschriebenen Systemabhängigkeiten.

## Speicherung und Verhalten

- Private Bibliotheken liegen unter `$XDG_DATA_HOME/lumen-tools/` bzw.
  `~/.local/share/lumen-tools/`, getrennt nach Anwendung. Zum Sichern bei
  geschlossenen Fenstern das komplette Verzeichnis kopieren.
- Notizen, Korrekturen und Auswahl werden automatisch gespeichert. Beim
  nächsten Start wird der zuletzt geöffnete aktive Eintrag wieder angezeigt.
- Archivieren entfernt einen Eintrag aus der aktiven Bibliothek. „Archiv
  anzeigen“ und „Wiederherstellen“ holen ihn zurück.
- Meetings und Haushaltsbelege sind importierte Kopien. Projektdateien sind
  Verknüpfungen; Netzlaufwerke müssen erreichbar sein. Radio speichert den
  importierten Quellentext und seine Herkunft, unabhängig vom Original.
- Keine Aufnahme startet automatisch. Transkription und Vertonung sind lokal.
  Ergebnisvorschläge und Hörskripte verwenden erst nach dem entsprechenden
  Knopfdruck den eingerichteten OpenCode-/LLM-Provider. Das kann ein
  Cloud-Provider sein. Die üblichen OpenCode-Grundeinstellungen gelten.
  Modellantworten erhalten keine Werkzeuge oder Änderungsrechte.
- Haushalt und Werkbank funktionieren vollständig ohne KI. Fristen werden
  angezeigt; es gibt keine automatische Kündigung oder Hintergrund-Erinnerung.
- Ein erneutes Vertonen ersetzt die aktive Ausgabe erst nach Erfolg.
  Nach Textänderungen wird vorhandenes Audio als ältere Fassung markiert.
  Quellenlinks einer erzeugten Ausgabe bleiben als zugehöriger Stand erhalten.
- Die Anwendungen senden keine Daten automatisch an GitHub. Laufzeitbibliotheken,
  Medien, Modelle und Anmeldedaten gehören nicht in die Repositories.

## Voraussetzungen und Grenzen

Vorhandene Lumen-Laufzeit: Python, PySide6, QtSvg, PyGObject, Pillow. Audio benötigt
`ffmpeg` einschließlich `ffprobe`/`ffplay`; PDF-Text Poppler; gescannte Belege
Tesseract samt Sprachdaten. Lokale Whisper-/Piper-Modelle lassen sich über
„Einrichtung“ installieren. Ohne Textindex bleibt ein Haushaltsbeleg gespeichert
und kann weiterhin geöffnet werden.

Aufnahmen: maximal 2 GB und acht Stunden. Belege: 128 MB. Radioquellen:
PDF/Text/Markdown oder Text in Bildern, pro Quelle höchstens 120.000 Zeichen;
für eine KI-Ausgabe höchstens 70.000 ausgewählte Zeichen. Meeting-KI hat dasselbe
Textlimit. Größere Eingaben werden erklärt zurückgewiesen, nicht still gekürzt.
Ein Hörskript darf höchstens 24.000 Zeichen enthalten. Die Minutenwahl ist ein
Schreibziel, keine garantierte Audio-Länge. Artikel hinter Login/Paywall oder
nur per JavaScript gerenderte Inhalte können als Text eingefügt werden.

Es gibt keine automatische Sprecheridentifikation. Zeitstellen kommen aus
Whisper-Segmenten; Text, Entscheidungen und Aufgaben bleiben korrigierbar.
KI-Ergebnisse können falsch sein – die Originalstelle ist direkt erreichbar.

## Entwicklung und Verifikation

`CAPABILITIES-tools.md` ordnet die vier Specs zu. `files/tools_data.py` enthält
Speicherung und lokale Verarbeitung, `tools_ui.py` gemeinsame Widgets/Jobs,
`tools_app.py` Fensteraktivierung. Die vier `tools_*.py`-Anwendungsmodule bleiben
getrennt von Lumen Files und dem Systemassistenten.

```bash
QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s files -p 'test_tools.py' -v
./bin/lumen-meetings
./packaging/arch/build-package.sh
```

`LUMEN_TOOLS_DATA` kann für isolierte Tests auf ein temporäres Verzeichnis zeigen.
Die Prüfungen decken Import, Abbruch, Persistenz, Archiv/Wiederherstellen,
Originalschutz, Quellenvalidierung, Projektwechsel und veraltete Radioausgaben ab.
Sprachpipeline und native Oberflächen wurden zusätzlich mit synthetischen
Testdaten geprüft; echte Meetings oder persönliche Belege wurden dafür nicht
verwendet.
