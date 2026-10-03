# Lumen Wissen

Eine eigene native Wissens-App, erreichbar über das Anwendungsmenü, die Suche
oder `lumen-wissen`. Sie verwendet die vier Lumen-Themes und benötigt für lokale
Notizen kein laufendes OpenCode. **Einrichtung** öffnet den gemeinsamen Wizard.

## Schreiben und verbinden

**Neue Notiz** beziehungsweise Strg+N legt eine Markdown-Datei an. Die Suche
durchsucht Titel, Text, Herkunft und `#tags`. Unter **Einfügen** lassen sich
Notizlinks, Bilder und Tags einsetzen. `[[Notizname]]`, `[[datei.md|Anzeigename]]`
und gewöhnliche relative Markdown-Links verbinden Notizen. Mehrdeutige Namen
lassen sich über den vollständigen relativen Dateinamen auflösen.

**Vorschau** zeigt formatierten Text und lokale Bilder. **Bearbeiten** führt zum
Markdown-Editor zurück. **Verbindungen** zeigt ausgehende Links und Rückverweise;
bei schmalen Fenstern bleibt diese Spalte zunächst eingeklappt. **Fokus** blendet
die Seitenleisten aus. Die optionale **Wissenskarte** zeigt die aktuelle Notiz
und bis zu 36 direkte Nachbarn. Ihre Knoten und die Verbindungsliste öffnen die
jeweilige Notiz; die Liste ist auch per Tastatur bedienbar.

**Speichern** oder Strg+S schreibt die Datei. Beim Wechsel der Notiz oder beim
normalen Schließen wird ebenfalls gespeichert. Während des Schreibens wird
nach kurzer Pause ein privater lokaler Entwurf gesichert. Änderungen aus anderen
Editoren werden etwa alle fünf Sekunden erkannt. Bei einem Konflikt bleibt der
Entwurf erhalten: **Externe Fassung laden** verwirft ihn nach Bestätigung,
**Entwurf als Kopie** legt eine zusätzliche Notiz an.

Vor dem Überschreiben oder Entfernen speichert Lumen eine lokale Fassung.
**Wiederherstellen** bringt sie zurück. Diese Kopien sind keine Btrfs-Snapshots
und ersetzen keine Sicherung des Notizordners. Sie werden nicht automatisch
bereinigt und können entsprechend Speicher belegen.

## Eigener Ordner und offene Dateien

Beim ersten Start wird `~/.local/state/lumen/wissen` angelegt; `LUMEN_DATA` bzw.
`XDG_STATE_HOME` können den Basisort ändern. **Ordner wählen** öffnet einen
anderen vorhandenen Ordner, etwa unter Dokumente oder auf einem eingebundenen
NAS. Es verschiebt keine Dateien. **Ordner öffnen** zeigt den Speicherort im
Dateimanager. `lumen-wissen "/pfad/zur/notiz.md"` öffnet eine Datei innerhalb des
gewählten Ordners auch im bereits laufenden Fenster.

Notizen sind gewöhnliche UTF-8-Markdown-Dateien. Ein optionaler HTML-Kommentar
hält Herkunft und Übernahme-ID fest. Fremde Frontmatter bleibt als Text erhalten.
Bilder werden bewusst als relative PNG-Anhänge in `attachments` kopiert und bei
Bedarf verkleinert. Obsidian kann denselben Ordner lesen; Obsidian-Plugins,
Canvas-Dateien und spezielle Frontmatter-Auswertungen werden nicht nachgebildet.
Externe Umbenennungen schreiben vorhandene Verknüpfungen nicht automatisch um.

Fehlt das NAS oder wurde der Ordner ersetzt, meldet Lumen den Fehler und behält
den lokalen Entwurf. Nach einem erneuten Einbinden kann **Ordner wählen** den
Speicherort ausdrücklich neu bestätigen. Lumen folgt keinen Symlinks im
Notizordner. Der Scan ist auf 5.000 Notizen, 32 MiB Text und 10.000 Einträge
begrenzt; eine Notiz auf 1 MiB. Überschreitungen erscheinen im Status.

## Fundstellen und Fragen

**Ins Lumen-Wissen** übernimmt in Reader eine gewählte Textstelle oder Markierung
mit Quelle und Seite. In Inbox übernimmt es die Auswahl oder den Nachrichtentext
mit Absender, Datum und Betreff, bis 20.000 Zeichen. **Ergebnis ins Wissen**
übernimmt das ausgewählte Lumen-Auftragsergebnis mit Herkunft. Diese Aktionen
senden nichts an ein Modell.

Im Reiter **Fragen** sucht **Quellen finden** lokal nach passenden Notizen.
Die Häkchen bestimmen, welche davon verwendet werden. Erst **Lumen fragen**
übermittelt bis zu acht frisch gelesene Auszüge von jeweils rund 3.000 Zeichen
an den in Lumen eingerichteten Anbieter. Dieser kann ein Cloud-Anbieter sein.
Andere Dateien und Werkzeuge sind für diese Anfrage gesperrt. Die Antwort wird
mit nummerierten Quellen angefordert; ihre Fundstellen bleiben darunter
anklickbar. Zitate und Aussagen sind prüfbar, aber nicht automatisch verifiziert.
**Antwort als Notiz** speichert die Antwort samt Verknüpfungen zurück.

Bestehende SQLite-Erinnerungen werden beim ersten Öffnen kopiert; die Originale
bleiben in der Datenbank. Wiederholte Starts erzeugen keine Duplikate. Änderungen
aus noch laufenden alten Lumen-Fenstern werden als zusätzliche Fassung übernommen
und überschreiben keine Markdown-Bearbeitung. Gelöschte Notizen entstehen durch
die unveränderte alte Erinnerung nicht erneut.

Entwürfe liegen privat unter dem Lumen-Zustandsordner in `wissen-drafts`, frühere
Fassungen in `wissen-history`. Fensterzustand und letzte Notiz liegen unter
`~/.local/share/lumen-tools/wissen`. Diese Daten gehören nicht ins Quellcode-Repo.

## Prüfung

`PYTHONPATH=files QT_QPA_PLATFORM=offscreen python3 -m unittest test_wissen -v`
prüft Migration, Konflikte, Wiederherstellung, Pfadgrenzen, Quellenkontexte und
die native Oberfläche. `python3 tests/check-reader-launch.py` prüft Kalt-/Warmstart
und Notizübergabe mit einem temporären Profil; ein optionales Argument wählt das
Starter-Verzeichnis der installierten Version.
