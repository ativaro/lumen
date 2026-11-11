# Lumen Reader und Sound

Auftrag: Ideen 3 und 4 als eigenständige native Apps umsetzen. Gemeinsame
ToolWindow/Library, Themes, lokale Piper-Stimme und Wissensspeicher verwenden.

## Reader

- Office-Dokumente (`.docx .docm .xlsx .xlsm .pptx .pptm .odt .ods .odp`) liest ein
  eigener Leser lokal aus dem XML der Datei, ohne Server und ohne Office-Programm:
  Lumens Dokument-Kern in Rust (`native/document-core`, Programm `lumen-document`),
  gestartet von `lumen_office.py`. Es ist eine Leseansicht, kein Drucklayout: Überschriften,
  Hervorhebungen, Listen, Tabellen und Bilder; Tabellenblätter und Folien beginnen je
  auf einer neuen Seite, Überschriften bilden das Inhaltsverzeichnis. Nicht gelesen
  werden Kopf-/Fußzeilen, Fußnoten, Diagramme, Formen, Folienlayout, Makros, verbundene
  Zellen und EMF/WMF-Bilder; Tabellenblätter sind auf 1000 Zeilen und 40 Spalten
  begrenzt. Die alten Binärformate `.doc .xls .ppt` und passwortgeschützte Dateien
  werden nicht geöffnet.
- PDFs, EPUBs, TXT/Markdown und gespeicherte HTML-Artikel bewusst importieren;
  Webartikel nur nach eingegebener Adresse abrufen, ohne Browserkonto.
- Private unveränderliche Lesekopie, Original bleibt erhalten. PDF im Seitenlayout,
  EPUB mit stabiler Seiteneinteilung; Zoom, Inhaltsverzeichnis, Buchsuche,
  Leseposition, Lesezeichen, Textmarkierung und bearbeitbare Randnotizen.
- Zugängliche Textansicht zusätzlich zur gerenderten Seite. Verschlüsselte PDFs
  mit Passwort nur im Arbeitsspeicher; keine PDF-Skripte, eingebetteten Programme
  oder automatisch geladenen externen Inhalte. EPUB-Größenprüfung vor Verarbeitung.
- Auswahl oder aktuelle Seite lokal vorlesen, mit Pause/Stopp. Markierte Stelle
  mit Titel, Seite und Originalquelle auf ausdrücklichen Klick ins Lumen-Wissen.
- Dokumentparser als begrenzter, abbrechbarer Unterprozess. Neue Lesekopie bei
  geändertem Original; keine automatische Migration alter Markierungen.

## Sound

- Native Live-Ansicht der verfügbaren Ausgänge und einzelnen Wiedergabe-Streams.
  Lautstärke, Stumm und Ausgabegerät pro Stream ändern; stabile App-Zuordnung für
  ausdrücklich gespeicherte Regeln. Fehlendes Gerät nicht durch ein zufälliges ersetzen.
- Optionale Gesprächsabsenkung: ausgewählte Musik-Apps leiser, wenn ein ausdrücklich
  ausgewähltes Gesprächsprogramm einen aktiven Gesprächs-/Aufnahmestrom hat.
  Nur Metadaten prüfen, niemals Mikrofoninhalt aufnehmen. Vorherige Kanalpegel
  wiederherstellen, fremde/manuelle Änderungen beachten, keine Lautstärkeerhöhung.
- Automatik standardmäßig aus, Start bei Anmeldung ausdrücklich einschaltbar.
  Eigener kleiner Benutzer-Dienst, keine Änderungen oder Neustarts von PipeWire,
  WirePlumber oder vorhandenen Gerätekonfigurationen.

## Abnahme

Reale synthetische PDF-/EPUB-/HTML-Dateien, Wiederöffnen/Notizerhalt,
Passwort-/Archivgrenzen, Wissenszitat und lokale Sprachsynthese prüfen. Audiotests
in eigener temporärer PipeWire-Sitzung mit stummen virtuellen Geräten/Streams;
keine Lautstärkeänderung oder Aufnahme an Benutzergeräten. Native Fenster rendern,
Launcher/Installer/Paket prüfen, vollständige Suite, Benutzerinstallation und Git.
Persönliche Dokumente, Audio-Metadaten, Einstellungen und Screenshots bleiben lokal.
