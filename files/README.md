# Lumen Files

Native Dateiverwaltung für Linux/KDE mit großer Vorschauleiste und laufender Dateinamensuche, lokal und auf Netzwerkservern. Nutzt die bereits installierten Bibliotheken und Werkzeuge.

## Start

Im Anwendungsmenü **Lumen Files** wählen, oder:

```bash
/usr/bin/python3 /home/example/Documents/work/lumen-files/app.py
```

Ein Ordnerpfad oder eine Netzwerkadresse kann als Argument übergeben werden. `~/.local/bin/lumen-files` ist der zusätzliche Starter. Das Projektverzeichnis muss an seinem Platz bleiben, da beide Starter es verwenden.

## Bedienung

- **Strg+F:** aktueller Ordner einschließlich Unterordner durchsuchen. Alle eingegebenen Wörter müssen im Dateinamen vorkommen, Großschreibung ist egal. Treffer erscheinen laufend; **Esc** beendet die Suche. Typfilter begrenzen die Anzeige.
- **Einmal auswählen:** Vorschauleiste. **Leertaste:** große Vorschau. Bilder, SVG, blätterbare PDFs, Text/Code, Video-Standbilder und Audio-Wellenformen. Medienwiedergabe über die Standard-App.
- **Strg+L:** Pfad eingeben. **Alt+Links/Rechts/Hoch:** Verlauf / übergeordneter Ordner. **Strg+T / Strg+W:** Tab öffnen / schließen. **Strg+Tab:** nächster Tab.
- **Strg+C / X / V:** kopieren / ausschneiden / einfügen. **F2:** umbenennen. **Strg+Umschalt+N:** Ordner erstellen. **Entf:** nach Bestätigung in den Systempapierkorb verschieben.
- **Strg+H:** versteckte Dateien. **Ort merken:** eigenen Favoriten ergänzen. Rechtsklick auf einen gemerkten Ort entfernt ihn wieder.
- Ziehen von Dateien kopiert sie in den Zielordner. Bestehende Ziele werden mit einer Fehlermeldung beibehalten.

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

Die Suche arbeitet direkt auf dem Dateisystem, **ohne Index und ohne Volltextsuche**. Sie folgt keinen Verzeichnis-Symlinks und endet bei 5.000 Treffern mit einem Hinweis. Bei großen Verzeichnisbäumen oder langsamen Netzlaufwerken dauert ein vollständiger Durchlauf länger. Nicht lesbare Einträge werden gezählt. Der Typfilter wirkt auf die gefundenen Treffer.

Textvorschauen lesen maximal 128 KB, Bilder maximal 128 MB / 80 Megapixel. Metadatenabfrage und Decoder laufen außerhalb der Oberfläche und werden jeweils nach 12 Sekunden beendet. Videos zeigen das erste Bild, Audio zeigt eine Wellenform der ersten 30 Sekunden. Keine Office-Vorschau oder integrierte Medienwiedergabe.

Kopien werden zunächst in einem temporären Ordner auf dem Ziellaufwerk erstellt und erst bei Erfolg sichtbar gemacht; bestehende Dateien werden nie still überschrieben. Bei Prozessabsturz können `.lumen-copy-*`-Ordner zurückbleiben. Kopiervorgänge lassen sich derzeit nicht abbrechen; das Fenster bleibt bis zum Ende offen. Ordner zwischen verschiedenen Dateisystemen zu verschieben kann GIO ablehnen; dafür zuerst kopieren und erst nach Kontrolle das Original in den Papierkorb verschieben. System-Papierkorb und Wiederherstellung können weiterhin in Dolphin genutzt werden.

Einstellungen und Favoriten: `~/.config/Lumen/Files.conf`. Es werden keine Standardzuordnungen geändert.

## Prüfung

```bash
cd /home/example/Documents/work/lumen-files
QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest -v
/usr/bin/python3 -m compileall -q .
```

Die Prüfungen verwenden temporäre Dateien: rekursive Suche, versteckte Dateien, Symlink-Schleife, ungültige Namen, Kopieren ohne Überschreiben, Tabs/Verlauf, Suchwechsel, Bild/SVG/PDF/Text/Video/Audio, defekte Dateien, Spezialdateien, Zwischenablage, Umbenennen/Verschieben und wiederherstellbarer Papierkorb. Der Papierkorb-Test hat ein isoliertes Datenverzeichnis.

Gemessener Suchkern: 30.000 kleine Dateien in 100 Ordnern, 100 Treffer, erster Treffer nach 0,0002 s und Abschluss nach 0,0176 s. Synthetischer warmer Cache auf diesem Rechner, ohne UI und ohne 250-ms-Eingabeverzögerung; kein allgemeines Leistungsversprechen.

## Voraussetzungen

Python 3, PyQt5/Qt 5.15 einschließlich QtDBus, PyGObject/GIO, Poppler (`pdfinfo`, `pdftoppm`), FFmpeg (`ffprobe`, `ffmpeg`), KIO-FUSE und KIO-Extras. Sämtliche Komponenten waren auf diesem Rechner vorhanden. Dateioperationen nutzen die dokumentierte [GIO-Semantik](https://docs.gtk.org/gio/method.File.move.html); Bildvorschauen die [Qt-Bilddekodierung](https://doc.qt.io/qt-6/qimagereader.html), mit Prüfung gegen das lokal installierte Qt 5.15.

## Entfernen

Die beiden Starter `~/.local/share/applications/lumen-files.desktop` und `~/.local/bin/lumen-files` entfernen. Optional zusätzlich das Projektverzeichnis und `~/.config/Lumen/Files.conf` entfernen. Dolphin bleibt installiert und unverändert zugeordnet.
