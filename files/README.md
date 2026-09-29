# Lumen Files

Native Dateiverwaltung für Linux/KDE mit großer Vorschauleiste, laufender Dateinamensuche und Inhaltssuche, lokal und auf Netzwerkservern. Nutzt die bereits installierten Bibliotheken und Werkzeuge.

## Start

Im Anwendungsmenü **Lumen Files** wählen, oder:

```bash
lumen-files
```

Ein Ordnerpfad oder eine Netzwerkadresse kann als Argument übergeben werden. Aus dem Checkout startet `./bin/lumen-files`, aus dem Paket `/usr/bin/lumen-files` mit den Quellen unter `/usr/share/opencode-lumen/files/`.

## Bedienung

- **Strg+F:** aktueller Ordner einschließlich Unterordner durchsuchen. Alle eingegebenen Wörter müssen im Dateinamen vorkommen, Großschreibung ist egal. Treffer erscheinen laufend; **Esc** beendet die Suche. Typfilter begrenzen die Anzeige.
- **Inhalte / Strg+Umschalt+F:** Text-, Code- und PDF-Inhalte im aktuellen Ordner einschließlich Unterordnern durchsuchen; Treffer zeigen echte Textstellen und eine Vorschau.
- **Einmal auswählen:** Vorschauleiste. **Leertaste:** große Vorschau. Bilder, SVG, blätterbare PDFs, Text/Code, Video-Standbilder und Audio-Wellenformen. Medienwiedergabe über die Standard-App.
- **Strg+L:** Pfad eingeben. **Alt+Links/Rechts/Hoch:** Verlauf / übergeordneter Ordner. Die seitlichen **Vor-/Zurück-Tasten der Maus** navigieren ebenfalls im Verlauf, unabhängig davon, über welchem Fensterbereich die Maus steht. In der Bildgalerie wechseln sie das Bild. **Strg+T / Strg+W:** Tab öffnen / schließen. **Strg+Tab:** nächster Tab.
- **Strg+C / X / V:** kopieren / ausschneiden / einfügen. **F2:** umbenennen. **Strg+Umschalt+N:** Ordner erstellen. **Entf:** nach Bestätigung in den Systempapierkorb verschieben.
- **Strg+H:** versteckte Dateien. **Ort merken** über das Lesezeichen-Symbol neben „Server verbinden“ ergänzt einen Favoriten. Rechtsklick auf einen gemerkten Ort entfernt ihn wieder. Die kompakte Seitenleiste zeigt bis zu zehn Orte auch bei 1000 × 640 Pixeln ohne Scrollen; lange Namen werden gekürzt, vollständige Pfade stehen im Tooltip.
- Ziehen von Dateien kopiert sie in den Zielordner. Bestehende Ziele werden mit einer Fehlermeldung beibehalten.

## Lumen-Integration

**Lumen** in der Werkzeugleiste oder **Strg+J** öffnet das native Seitenpanel.
Rechtsklick → **Lumen** übernimmt alle ausgewählten Dateien:

- **Mit Lumen öffnen:** eigene Frage eingeben.
- **Erklären:** direkte Ergebnisansicht mit kurzer Erklärung und „Mehr Details“.
- **Fehler beheben:** native Fortschrittsanzeige, anschließend Ergebnis, Änderungen und Prüfung. „Ergebnis prüfen“ untersucht das Resultat nochmals ohne Bearbeitung.
- **Git-Diff prüfen:** eigene Ergebnisansicht für die Prüfung ohne Bearbeitung.

Diese Dateiaktionen zeigen ihre Ergebnisse ohne Chat-Eingabe, Gesprächsauswahl,
Moduswahl oder interne Auftragstexte. „Erneut versuchen“, „Kopieren“ und „Schließen“
sind direkt verfügbar; Abbrechen, Freigaben und Rückfragen bleiben im selben Panel.
Der freie Chat über **Lumen / Strg+J / Mit Lumen öffnen** bleibt separat erreichbar.
**Strg+Enter** sendet; „Neues Gespräch“ und die Gesprächsauswahl verwalten
Lumen-Unterhaltungen im Arbeitsordner. Der Kontext bleibt sichtbar, auch wenn
man im Dateimanager weiter navigiert. Netzwerkdateien nutzen ihren lokalen
KIO-FUSE-Pfad. Bilder/PDFs werden als Anhänge übergeben.

OpenCode arbeitet als lokale Hintergrund-Engine mit der bestehenden
Konfiguration. Dateien lassen sich auch ohne laufende Engine verwalten.

## Intelligent umbenennen und sortieren

Dateien markieren → Rechtsklick → **Lumen → Intelligent umbenennen …** oder
**Dateien sortieren …**. Bei mehreren ausgewählten Dateien öffnet auch **F2**
das intelligente Umbenennen. Eine optionale Vorgabe wie „Datum und Thema im
Namen“ ergänzen und **Vorschläge erstellen** anklicken.

Die native Tabelle zeigt bisherige Namen, editierbare Ziele und Begründungen.
Ziele mit Doppelklick/F2 bearbeiten, unerwünschte Vorschläge abwählen.
Erst **Änderungen anwenden** verändert Dateien. Umbenennen erhält den bisherigen
Ordner und die Endung; Sortieren erhält den Namen und erstellt Unterordner im
aktuellen Ordner. Belegte, doppelte, überlappende oder ungültige Ziele werden
markiert. Nachträglich geänderte Dateien werden nicht verschoben.

**Rückgängig** im Dialog oder **Letzte Lumen-Dateiaktion rückgängig …** im
Datei-Kontextmenü stellt den letzten Durchlauf wieder her, auch nach einem
Neustart. Ein neuer Durchlauf ersetzt die vorherige Rückgängig-Möglichkeit.
Das Journal liegt unter `~/.local/share/Lumen Files/organize-undo.json` (bzw.
unter dem entsprechenden XDG-Datenpfad). Bei Teilfehlern/Abbruch werden bereits
ausgeführte Änderungen angezeigt; verbleibende Undo-Konflikte bleiben im
Journal. Leere neu angelegte Zielordner bleiben erhalten. Auch Undo überschreibt
keine Dateien und lässt inzwischen bearbeitete Dateien unangetastet.

Bis zu 100 reguläre Dateien je Durchlauf, keine Ordnerauswahl oder Symlinks.
Lumen erhält höchstens 4.096 Zeichen Text je Datei, Text aus den ersten drei
PDF-Seiten und bis zu zwölf Bildvorschauen mit maximal 1.024 Pixeln Kantenlänge;
sonst nur Namen/Größen. Gescannte PDFs benötigen Text, es gibt hier kein OCR.
Inhalte werden über deine bestehende Modellkonfiguration verarbeitet. Die
Vorschlagssitzung sperrt alle Werkzeuge über die
[OpenCode-Berechtigungen](https://opencode.ai/docs/permissions/); Files führt
bestätigte Änderungen selbst aus. Vorschläge erscheinen nicht im Chatverlauf.
Verschieben erfordert einen nativen Move innerhalb desselben Dateisystems;
Netzwerk-Backends ohne diese Unterstützung melden einen Fehler, ohne auf
Kopieren/Löschen auszuweichen. Keine neuen Bibliotheken nötig.

## Inhalte suchen

**Inhalte** neben der Dateinamensuche oder **Strg+Umschalt+F** öffnet die native
Suchansicht. Eine Frage wie „Die Rechnung für meinen Monitor“ sucht lokal nach
den wichtigen Begriffen. Mehrere Begriffe müssen im Dokument vorkommen;
Anführungszeichen verbinden Wörter zu einer Phrase. Treffer erscheinen laufend
mit Originaltext, Zeile oder PDF-Seite. Auswählen zeigt die Fundstelle und springt
in der PDF-Vorschau zur passenden Seite. **Datei öffnen** und **Ordner öffnen**
führen direkt zum Ergebnis. **Stoppen**, eine neue Anfrage und Schließen beenden
den Suchprozess einschließlich eines laufenden PDF-Decoders.

Optional ergänzt **Mit Lumen erweitern** verwandte Begriffe, etwa „Bildschirm“
für „Monitor“. Dafür gehen die Suchfrage und die eingerichteten persönlichen
Lumen-Anweisungen an dein konfiguriertes Modell. Gefundene Dokumente werden
nicht angehängt. Die Sitzung läuft mit gesperrten Werkzeugen in einem leeren
Arbeitsordner; Projektanweisungen aus dem durchsuchten Ordner werden nicht
automatisch geladen. Modellfehler lassen bisherige lokale Treffer erhalten.

Ohne persistenten Index: bis zu 1 MiB Text pro Datei, PDF-Textextraktion mit
`pdftotext` bis 128 MiB Dateigröße und 12 Sekunden pro PDF. Maximal 500 Treffer
oder 100.000 besuchte Einträge je Suche. Teilweise durchsuchte, nicht lesbare und
textlose Dateien werden im Ergebnisstatus gezählt. Versteckte Einträge sind
optional, Symlinks und Spezialdateien werden ausgelassen. Keine OCR- oder
Office-Inhaltssuche; gescannte PDFs brauchen bereits eine Textebene. Große Bäume
und Netzwerkordner dauern länger und können Daten vom Server herunterladen.

## Bildgalerie und einfache Bearbeitung

Ein Bild doppelklicken oder mit **Leertaste** öffnen. Die Galerie übernimmt die Bilder und Sortierung der aktuellen Ansicht, auch bei Suchergebnissen. **Links/Rechts** wechseln das Bild; Nachbarbilder werden vorgeladen. **Mausrad / + / −** zoomen, Ziehen verschiebt das Bild, **0** passt es ein, **F11** schaltet Vollbild um. **Esc / Leertaste** schließen die Galerie.

**R / Umschalt+R** drehen rechts / links, **H** spiegelt horizontal, **Strg+Z** nimmt einen Schritt zurück. **Strg+S** speichert JPEG, PNG oder einzelne WebP-Bilder in voller Auflösung. EXIF-Ausrichtung wird berücksichtigt. JPEG wird mit hoher Qualität neu komprimiert; PNG und WebP werden verlustfrei geschrieben. Die Bildschirmvorschau ist für schnelles Blättern auf 2560 Pixel begrenzt; sie ist keine pixelgenaue Originalansicht.

Vor jedem Speichern entsteht eine bytegenaue Sicherung in **`.lumen-originals` neben dem Bild**, sichtbar mit **Strg+H**. Die Sicherung bleibt auch bei weiteren Bearbeitungen erhalten und kann bei Bedarf zurückkopiert werden. Dateien werden zunächst separat geschrieben und anschließend ersetzt. Erkannte externe Änderungen brechen das Speichern ab. Animationen, andere Formate und symbolische Links werden nicht überschrieben. Bei Netzwerkdateien muss der Server Sicherung und Ersetzen unterstützen; Fehler werden angezeigt.

**Entf / Papierkorb** verschiebt das aktuelle Bild nach Bestätigung in den Systempapierkorb und zeigt das nächste. Ein nicht unterstützter Papierkorb führt zu einer Fehlermeldung. Ungespeicherte Bearbeitungen lassen sich beim Bildwechsel speichern, verwerfen oder durch Abbrechen behalten.

## Speicheranalyse

**Speicheranalyse** in der Seitenleiste untersucht den aktuellen Ordner. **Ordner wählen** erlaubt andere Verzeichnisse oder Laufwerke; der Rechtsklick auf einen Ordner bietet dieselbe Funktion. Der Größenbaum ist sortierbar und zeigt den Anteil am jeweiligen Elternordner. Beim Aufklappen werden Unterordner genauer analysiert. **Ordner öffnen** wechselt zur ausgewählten Stelle im Dateimanager.

Standardmäßig wird belegter Speicher gezählt; die Checkbox wechselt zur logischen Dateigröße. Versteckte Dateien sind enthalten, Verzeichnis-Symlinks werden nicht verfolgt, andere Dateisysteme nicht durchlaufen. Ein anderes Laufwerk separat auswählen. Hardlinks werden je Analyselauf einmal gezählt; beim erneuten Untersuchen eines Teilbaums kann sich ihre Zuordnung ändern. Komprimierte oder gemeinsam genutzte Datenblöcke können zu Abweichungen gegenüber dem freien Laufwerksspeicher führen.

Die Analyse nutzt GNU `du` und `find` in eigenen Prozessen, ist mit **Stoppen** abbrechbar und verändert keine Dateien. Unlesbare Bereiche werden als unvollständig gemeldet. Pro aufgeklapptem Ordner erscheinen höchstens die größten 5.000 direkten Einträge; die Gesamtgröße umfasst weiterhin alle gezählten Einträge. Große Unterbäume werden beim ersten Aufklappen erneut durchlaufen.

Tabs stehen oberhalb aller Bedienelemente. Der automatische Seitenleisteneintrag `/mnt/games` entfällt. Eigene Spieleordner können weiterhin über **Ort merken** hinzugefügt werden.

## Netzwerkserver

**Server verbinden** in der Seitenleiste oder **Strg+K** öffnet den Verbindungsdialog. Unterstützt werden die installierten KDE-Protokolle SMB, SFTP, WebDAV, FTP und NFS. Beispiele:

| Verbindung | Adresse |
|---|---|
| NAS / Windows-Freigabe | `smb://nas.local/Freigabe` oder `\\nas.local\Freigabe` |
| SSH / SFTP | `sftp://name@server:22/ordner` |
| WebDAV mit TLS | `webdavs://cloud.example/remote.php/dav/files/name/` |
| WebDAV ohne TLS | `webdav://server/ordner` |
| NFS | `nfs://server/export` |
| FTP | `ftp://name@server/ordner` |

Im Dialog reichen auch `nas.local/Freigabe` und das ausgewählte Protokoll. Vollständige Netzwerkadressen lassen sich direkt über **Strg+L** eingeben; HTTPS-/HTTP-Adressen werden dort als WebDAV interpretiert. Netzwerksuche nach unbekannten Geräten ist nicht enthalten.

KDE übernimmt die Anmeldung und gegebenenfalls KWallet. Passwörter in Adressen werden abgewiesen und nicht in Lumen-Einstellungen gespeichert. **Server merken** speichert nach erfolgreichem Öffnen die Adresse in der Seitenleiste. Rechtsklick öffnet einen neuen Tab oder entfernt den gemerkten Ort. **Ort merken** speichert auch Unterordner einer Verbindung. Pfadleiste, Verlauf und Neustart verwenden die Serveradresse.

Die Anbindung erfolgt über den bereits installierten [KIO-FUSE-Dienst](https://github.com/KDE/kio-fuse/blob/master/README.md). Verbundene Ordner nutzen dieselbe Suche, Vorschau und Dateiaktionen. Übertragungen laufen im Hintergrund; Vorschauen können Daten vom Server herunterladen. Kopien **auf** eine KIO-Netzwerkfreigabe übernehmen Inhalte und Verzeichnisstruktur, aber erzwingen keine Unix-Rechte, Eigentümer oder Zeitstempel, die beispielsweise WebDAV nicht unterstützt. Namenskonflikte überschreiben keine bestehenden Dateien.

**Abbrechen / Esc** verwirft die wartende Verbindung in Lumen. Der gemeinsame KDE-Dienst kann eine bereits laufende Anmeldung noch abschließen; Lumen öffnet oder speichert diese verspätete Verbindung nicht. Einzelne KIO-Verbindungen werden nicht ausgehängt, da sie auch andere KDE-Anwendungen verwenden können. Dateisystem-/Server-Caches können Änderungen verzögert anzeigen. Papierkorb funktioniert nur, wenn der Server bzw. Mount ihn unterstützt; ein Fehler führt nie zum endgültigen Löschen.

SMB/SFTP/NFS/FTP sind über die installierten KDE-Module angebunden. Der automatisierte End-to-End-Test verwendet einen echten, ausschließlich auf `127.0.0.1` erreichbaren WebDAV-Testserver und prüft Navigation, Neustart, Suche, Textvorschau, Upload/Download, Ordnerkopie, Verschieben, Konflikte, Fehler und verspätete Antworten. Eine Anmeldung an deinem eigenen NAS oder SSH-Server ist damit noch nicht geprüft.

## Verhalten und Grenzen der ersten Version

Die Dateinamensuche arbeitet direkt auf dem Dateisystem, **ohne Index**. Sie folgt keinen Verzeichnis-Symlinks und endet bei 5.000 Treffern mit einem Hinweis. Bei großen Verzeichnisbäumen oder langsamen Netzlaufwerken dauert ein vollständiger Durchlauf länger. Nicht lesbare Einträge werden gezählt. Der Typfilter wirkt auf die gefundenen Treffer. Für Textinhalte gibt es die separate Inhaltssuche mit den oben genannten Grenzen.

Textvorschauen lesen maximal 128 KB, Bilder maximal 128 MB / 80 Megapixel. Metadatenabfrage und Decoder laufen außerhalb der Oberfläche und werden jeweils nach 12 Sekunden beendet. Videos zeigen das erste Bild, Audio zeigt eine Wellenform der ersten 30 Sekunden. Keine Office-Vorschau oder integrierte Medienwiedergabe.

Kopien werden zunächst in einem temporären Ordner auf dem Ziellaufwerk erstellt und erst bei Erfolg sichtbar gemacht; bestehende Dateien werden nie still überschrieben. Bei Prozessabsturz können `.lumen-copy-*`-Ordner zurückbleiben. Kopiervorgänge lassen sich derzeit nicht abbrechen; das Fenster bleibt bis zum Ende offen. Ordner zwischen verschiedenen Dateisystemen zu verschieben kann GIO ablehnen; dafür zuerst kopieren und erst nach Kontrolle das Original in den Papierkorb verschieben. System-Papierkorb und Wiederherstellung können weiterhin in Dolphin genutzt werden.

Einstellungen und Favoriten: `~/.config/Lumen/Files.conf`. Es werden keine Standardzuordnungen geändert.

## Prüfung

```bash
cd /home/example/Documents/work/opencode-lumen/files
QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest -v
/usr/bin/python3 -m compileall -q .
```

Die Prüfungen verwenden temporäre Dateien: rekursive Suche, versteckte Dateien, Symlink-Schleife, ungültige Namen, Kopieren ohne Überschreiben, Tabs/Verlauf, Suchwechsel, Bild/SVG/PDF/Text/Video/Audio, defekte Dateien, Spezialdateien, Zwischenablage, Umbenennen/Verschieben und wiederherstellbarer Papierkorb. Der Papierkorb-Test hat ein isoliertes Datenverzeichnis.

Zusätzlich geprüft: Tabs oberhalb der Suche, Galerie-Aufruf und Bildfolge, vorgeladene Nachbarbilder, Drehen/Spiegeln, EXIF-Ausrichtung, Original-Sicherung, Änderungskonflikte, Schutz von Animationen und Symlinks, Papierkorb-Erfolg/Fehler in der Galerie sowie Speichergrößen, Sparse-Dateien, Hardlinks, Verzeichnis-Symlinks, Zugriffsfehler und Abbruch. Native Screenshots in normaler und kompakter Größe liegen unter `artifacts/`.

Die Inhaltssuche prüft echte Text-/PDF-Fundstellen, deutsche Suchbegriffe,
Synonyme, PDF-Seitensprung, Grenzen, versteckte Einträge, Symlink-Austausch,
fehlerhafte Modellantworten und das Beenden laufender Decoder bei Abbruch oder
Scanner-Ausfall. Zusätzlich wurde die Begriffserweiterung mit der echten Engine
an temporären Text- und PDF-Dateien geprüft.

Gemessener Suchkern: 30.000 kleine Dateien in 100 Ordnern, 100 Treffer, erster Treffer nach 0,0002 s und Abschluss nach 0,0176 s. Synthetischer warmer Cache auf diesem Rechner, ohne UI und ohne 250-ms-Eingabeverzögerung; kein allgemeines Leistungsversprechen.

## Voraussetzungen

Python 3, PyQt5/Qt 5.15 einschließlich QtDBus, PyGObject/GIO, Pillow, GNU `du`/`find`, Poppler (`pdfinfo`, `pdftoppm`, `pdftotext`), FFmpeg (`ffprobe`, `ffmpeg`), KIO-FUSE und KIO-Extras. Sämtliche Komponenten waren auf diesem Rechner vorhanden. Dateioperationen nutzen die dokumentierte [GIO-Semantik](https://docs.gtk.org/gio/method.File.move.html); Bildvorschauen die [Qt-Bilddekodierung](https://doc.qt.io/qt-6/qimagereader.html), mit Prüfung gegen das lokal installierte Qt 5.15.

## Entfernen

Die beiden Starter `~/.local/share/applications/lumen-files.desktop` und `~/.local/bin/lumen-files` entfernen. Optional zusätzlich das Projektverzeichnis und `~/.config/Lumen/Files.conf` entfernen. Dolphin bleibt installiert und unverändert zugeordnet.
