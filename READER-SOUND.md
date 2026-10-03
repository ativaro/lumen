# Lumen Reader und Lumen Sound

Beide sind eigenständige native Fenster mit den gemeinsamen Lumen-Themes. Sie
erscheinen im Anwendungsmenü und in der Suche. Der Installer richtet die Starter
ein; **Einrichtung** prüft die optionalen Abhängigkeiten. Es werden keine
Dateizuordnungen ersetzt und keine Audioregeln automatisch aktiviert.

## Reader

**Buch oder Dokument öffnen** importiert PDF, EPUB, TXT, Markdown oder HTML in
eine private Bibliothek. Auch **Öffnen mit → Lumen Reader** und
`lumen-reader "/pfad/buch.pdf"` funktionieren; ein weiteres Dokument erreicht
das bereits geöffnete Fenster. **Artikel speichern** lädt eine ausdrücklich
angegebene Webadresse ohne Browserkonto und speichert den lesbaren Text.

Seitenbreite, Zoom, Textansicht, Inhaltsverzeichnis und Buchsuche helfen bei der
Navigation. Bild-ab/Bild-auf wechseln die Seite bei fokussierter Leseansicht.
Leseposition und Randnotizen werden automatisch gespeichert. Text auf der Seite
ziehen oder in der Textansicht per Tastatur auswählen und **Markieren** klicken.
**Lesezeichen** hält die aktuelle Seite fest. **Lesemodus** blendet beide
Seitenleisten aus; ein weiterer Klick bringt sie zurück. Notizen lassen sich
als Markdown exportieren.

**Vorlesen** verwendet die vorhandene lokale Piper-Stimme für die Auswahl oder
die aktuelle Seite (bis 24.000 Zeichen), mit Pause und Stopp. Die Stimme lässt
sich in der Einrichtung installieren. **Ins Lumen-Wissen** übernimmt nur die
ausgewählte Stelle beziehungsweise Markierung, mit Titel, Reader-Seite und
Originalquelle. Der Klick sendet keine Daten an einen KI-Anbieter.

Originale bleiben unverändert; alle Ansichten beziehen sich auf eine Lesekopie.
Ein geändertes Original wird bei erneutem Import ein neuer Eintrag. PDF-Seiten
behalten ihr Layout, EPUB-Seiten verwenden eine feste Einteilung für verlässliche
Notizpositionen. HTML wird in reinen Artikeltext umgewandelt: Skripte, Bilder,
Styles und externe Ressourcen werden nicht übernommen. DRM-geschützte EPUBs,
interaktive PDF-Formulare und OCR für reine Bildseiten gehören nicht zum Reader.
Bildseiten bleiben sichtbar, haben aber keine auswählbare Textschicht.

PDF-Passwörter bleiben nur für die geöffnete Sitzung im Speicher. Die Lesekopie
bleibt verschlüsselt; ausdrücklich angelegte Notizen und Wissenseinträge enthalten
jedoch den ausgewählten Klartext. Vorlesedateien werden beim Seitenwechsel oder
normalen Schließen entfernt. Die Bibliothek liegt privat unter
`$XDG_DATA_HOME/lumen-tools/reader` (standardmäßig `~/.local/share/lumen-tools/reader`),
das bestehende Lumen-Wissen im Lumen-Datenspeicher. Archiveinträge bleiben in der
Bibliothek und können wieder eingeblendet werden.

Der Parser läuft in einem abbrechbaren Unterprozess mit Zeit-, Datei-, Seiten-
und Ausgabegrenzen. Dies ist keine Betriebssystem-Sandbox. Die optionalen
Reader-Pakete sollten wie der Rest des Systems aktuell gehalten werden.

## Sound

**Anwendungen** zeigt die aktiven Wiedergabestreams. Regler, **Stumm** und
**Ausgabe** betreffen genau diesen Stream. Kanalbalance bleibt erhalten; der
Regler begrenzt neue Einstellungen auf 0–100 %. Ein fehlendes Zielgerät wird
gemeldet. Lumen ändert keine Hardwareprofile oder globalen Standardgeräte.

**Für App merken** speichert Lautstärke, Ausgang, Stummstatus und eine optionale
Rolle. Unter **Regeln & Gespräche** lassen sich Regeln bearbeiten oder löschen.
Eine App wird anhand ihrer gemeldeten Kennung beziehungsweise Programmdatei
zugeordnet; mehrere Browser-Tabs können deshalb dieselbe Regel erhalten.
Die Ziel-App muss für das erstmalige Hinzufügen einen Audio- oder Aufnahmestrom
geöffnet haben. Ein fehlendes gespeichertes Ausgabegerät wird abgewartet.

Die **Automatik ist standardmäßig aus**. Erst **Für diese Anmeldung aktiv** oder
**Bei jeder Anmeldung starten** plus **Übernehmen** aktiviert die Regeln.
Der eigene Benutzer-Dienst `lumen-sound.service` arbeitet auch bei geschlossenem
Fenster. Das Abschalten stellt temporär abgesenkte Musik wieder her; ausdrücklich
gesetzte App-Lautstärken und Ausgaben bleiben erhalten. Löschen einer Regel setzt
eine laufende App ebenfalls nicht auf frühere Einstellungen zurück.

Für Gesprächsabsenkung einer App die Rolle **Musik**, der Gesprächs-App die Rolle
**Gespräch** geben, das Absenken einschalten und speichern. Es greift, wenn die
Gesprächs-App eine aktive Mikrofonverbindung oder einen als Telefonie gemeldeten
Wiedergabestrom öffnet. Der Prozentwert bezieht sich auf den vorherigen Musikpegel.
Erkennung erfolgt ungefähr alle zwei Sekunden anhand von Metadaten; es wird kein
Audio aufgenommen oder transkribiert. Apps ohne solche Merkmale lösen keine
Absenkung aus. Eine dauerhaft offene Mikrofonverbindung kann sie länger auslösen.

Manuelle Pegeländerungen haben während des Gesprächs Vorrang. Bei Gesprächsende,
normalem Dienststopp oder Wiederanlauf werden nur noch unveränderte, von Lumen
abgesenkte Streams wiederhergestellt. Server-/Stream-Identitäten verhindern eine
Wiederherstellung auf einem anderen Stream. Bei einem hart beendeten Dienst kann
die Wiederherstellung erst nach dessen erneutem Start erfolgen.

Regeln und das Wiederherstellungsjournal liegen privat unter
`$XDG_DATA_HOME/lumen-tools/sound`. PipeWire/WirePlumber werden weder konfiguriert
noch neu gestartet. Benötigt wird `pactl` aus `libpulse` und ein Pulse-kompatibler
Audioserver; für die Automatik zusätzlich die systemd-Benutzersitzung.

## Prüfung

`python3 -m unittest discover -s files -v` prüft Dokumentimport, Notizerhalt,
Wissenszitate, Audiozustände und Fehlerpfade. `python3 tests/check-sound.py`
prüft reale Umschaltung und Absenkung in einer privaten PipeWire-Sitzung mit
stummen virtuellen Geräten und WirePlumbers hardwarefreiem Policy-Profil.
`python3 tests/check-reader-launch.py` prüft Kalt-/Warmstarts aller Werkzeuge und
die Dateiübergabe an Reader in einem temporären Benutzerprofil. Ein optionales
Argument gibt ein anderes Starter-Verzeichnis für die installierte Version an.
