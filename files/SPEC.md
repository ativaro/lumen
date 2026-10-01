# Lumen — Dateien

Native Linux-Dateiverwaltung mit Schwerpunkt auf schneller Dateinamensuche und brauchbaren Vorschauen. Deutsch, dunkle ruhige Oberfläche, Systemschrift, vorhandenes PyQt5 und GIO; keine neuen Pakete.

## Akzeptanz
- Gestaltung gemäß freigegebenem Entwurf: Tabs oberhalb einer kompakten Navigation,
  Graphitflächen mit türkisen Akzenten, sichtbare blaue Ordner und native Dateiicons,
  klare Typografie, dezente Auswahl und kompakte Sammelfläche/Miniaturregler unten.
  Vorschau, Größen/Herkunft, Suche und Netzwerkfunktionen bleiben erhalten. Lange
  Pfade halten den aktuellen Ordner sichtbar; Strg+L erlaubt die vollständige Adresse.
  Weiterer Entwurfsabgleich: dichteres Raster mit 144px Standardminiaturen, weiche
  Verläufe, leisere Trennlinien und Fokusmarkierung am Dateinamen. Eigene Symbole
  nur für konfigurierte XDG-Ordner, gemeinsam in Liste/Raster/Bibliothek; native
  Symlinkmarkierungen erhalten. Netzwerk- und Bibliotheksherkunft bleibt sichtbar.
  Keine fremden Fenster schließen oder den Desktopstil für den Abgleich ändern.
- Echte lokale Ordner, Favoriten, Tabs, Verlauf, versteckte Dateien und Typfilter.
- Seitliche Maustasten und Browser-Zurück/Vor-Tastensignale navigieren über allen Fensterbereichen im Verlauf, in der Galerie durch Bilder; andere Dialoge lösen keine Hintergrundnavigation aus. Dateiliste selbst und ihre innere Fläche prüfen; `QWidget.window()` bleibt aufrufbar. Zehn Orte passen bei 1000 × 640 Pixeln ohne Scrollen in die Seitenleiste.
- Dateinamensuche ab 250 ms Eingabepause, rekursiv, laufende Treffer, abbrechbar; ohne Beachtung der Großschreibung. Keine Symlink-Rekursion. Maximal 5.000 Treffer mit sichtbarem Hinweis. Kein Hintergrundindex.
- Auswahl zeigt Bilder, blätterbare PDFs, Text/Code und Video-Standbilder; Leertaste öffnet große Vorschau. Decoder laufen außerhalb der Oberfläche mit Zeitlimit. Keine automatische Ausführung, kein HTML-Rendering.
- Öffnen, Ordner erstellen, Umbenennen, Kopieren, Ausschneiden/Einfügen, bestätigter Papierkorb. Kein stilles Überschreiben. Fehler sichtbar, große Kopien im Hintergrund.
- Startmenüeintrag und Startbefehl. Standard-Dateimanager bleibt eine gesonderte Nutzereinstellung.

## Struktur und Befehle
`app.py`: Oberfläche; `core.py`: Suche/Dateioperationen; `preview.py`: Vorschau; `test_lumen.py`: ausführbare Prüfungen; `style.qss`: Gestaltung.

Start: `/usr/bin/python3 files/app.py`
Test: `cd files && QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest -v`
Prüfung: `/usr/bin/python3 -m compileall -q files`

## Stil und Grenzen
Python, vier Leerzeichen, kleine direkte Funktionen: `def valid_name(name): ...`. Native Qt-Widgets und Standardbibliothek zuerst. Tests mit unittest und temporären Verzeichnissen, keine Nutzerdaten verändern. Decoder begrenzen Lesevolumen und Laufzeit. Keine Systemkonfiguration, Fremdprojekte oder Standardzuordnungen ändern. Versionskontrolle lokal.

## Inhaltssuche
- Das rechte Symbol im Suchfeld oder Strg+Umschalt+F öffnet eine native Suchansicht für den aktuellen Ordner und Unterordner. Suchfeld, laufende Treffer mit echten Textausschnitten, Dateivorschau, Öffnen und „Ordner öffnen“; keine Chatoberfläche.
- Text/Code und PDFs mit Textebene werden lokal durchsucht. Fragen wie „Die Rechnung für meinen Monitor“ werden auf wesentliche Suchwörter reduziert; alle Begriffe müssen im Inhalt vorkommen. Groß-/Kleinschreibung und übliche deutsche Endungen werden berücksichtigt.
- „Mit Lumen erweitern“ ergänzt auf ausdrücklichen Klick alternative Suchbegriffe. Nur die Suchfrage wird als Anfrage übergeben, keine Suchtreffer oder Ordnerlisten. Ein leerer Arbeitsordner und deaktivierte Projektkonfiguration verhindern das automatische Laden von Anweisungen aus dem Suchordner; persönliche globale Lumen-/OpenCode-Anweisungen bleiben wie eingerichtet Teil des Modellkontexts und werden im Tooltip genannt. Backend mit gesperrten Werkzeugen wiederverwenden; Ergebnisse sind echte lokale Fundstellen. Begriffe sichtbar, Modellfehler lassen lokale Suche nutzbar.
- Lesen und PDF-Extraktion in einem abbrechbaren Kindprozess; vorhandenes pdftotext nutzen. Keine Symlinks/Spezialdateien, versteckte Inhalte nur bei entsprechender Auswahl. Maximal 1 MiB Text je Datei, PDFs bis 128 MiB/12 Sekunden, 500 Treffer und 100.000 besuchte Einträge. Fehler und Teilabdeckung werden sichtbar gezählt. Keine Office-/OCR-Suche, kein dauerhafter Index, kein System-Indexer wird aktiviert.
- Neue Anfrage/Abbruch/Schließen verwirft alte Antworten und beendet eigene Decoder. Beim Öffnen eines Treffers Existenz prüfen. Tests mit temporären Text/PDF-Dateien, tatsächlichen Zitaten/Seiten, Synonymen, Grenzen, Symlinks, Fehlern, Abbruch, veralteten Antworten und nativer UI. Bestehende Tests bleiben grün.
- Reihenfolge: Suchkern und Prozessprotokoll → native Ansicht und Lumen-Begriffe → reale Modell-/UI-Prüfung → Installation/Dokumentation.

## Intelligentes Umbenennen und Sortieren
- Zwei Aktionen teilen eine native Vorschautabelle: Umbenennen ändert Namen im bisherigen Ordner; Sortieren verschiebt unterhalb des aktuellen Ordners und erhält Dateinamen. Keine Chatansicht.
- Auswahl regulärer Dateien, höchstens 100 pro Durchlauf; keine rekursive Ordnerauswahl, Symlinks oder Spezialdateien. Textauszüge, bis zu drei PDF-Seiten und höchstens zwölf verkleinerte Bildvorschauen dienen als Kontext; sonst Metadaten. Begrenzte Decoder laufen außerhalb der Oberfläche.
- Optionale Vorgabe, dann „Vorschläge erstellen“. Lumen liefert ausschließlich Daten; alle Werkzeuge sind für diese neue Sitzung gesperrt. Globale OpenCode-Einstellungen bleiben unverändert.
- Tabelle mit Auswahl, bisherigem Pfad, editierbarem Ziel und Begründung/Fehler. Erst „Anwenden“ verändert Dateien. Erweiterungen bleiben erhalten; ungültige Pfade, doppelte oder belegte Ziele und veränderte Quellen sperren den Vorgang.
- Dateioperationen laufen im Hintergrund über vorhandenes GIO ohne Überschreiben, innerhalb desselben Dateisystems. Teilfehler und Abbruch zeigen den tatsächlichen Stand. Ein vorab atomar gespeichertes Journal erlaubt das Rückgängigmachen des letzten Durchlaufs auch nach Neustart; neue Vorgänge ersetzen es. Neu entstandene leere Ordner bleiben bestehen.
- Verifizieren: temporäre Dateien für Vorschlag → Bearbeiten/Abwählen → Anwenden → Undo, Pfadausbruch/Symlinks, Konflikte, geänderte Quellen, Teilfehler, Abbruch, fehlerhafte Modellantworten und echten Modellaufruf. Bestehende unittest-Prüfungen bleiben grün.
- Reihenfolge: sichere Vorschlags-/Dateilogik → nativer Dialog und Kontextmenü → Modell-/UI-Prüfung → Benutzerinstallation und Dokumentation.

## Netzwerkverbindungen
- Verbindungsdialog für SMB, SFTP, WebDAV (HTTP/HTTPS), FTP und NFS; UNC-Adressen und direkte URL-Eingabe über Strg+L.
- Vorhandenes KIO-FUSE über asynchrones D-Bus nutzen. Keine Root-Mounts und keine neue Protokollimplementierung.
- KDE übernimmt Anmeldung. Lumen speichert ausschließlich validierte Serveradressen ohne Passwort; fehlgeschlagene Verbindungen nicht speichern.
- Gemerkte Server in der Seitenleiste, Netzwerkadressen in Pfadleiste und Verlauf statt flüchtiger Mountpfade. Verbindungen im neuen Tab und nach Neustart wieder öffnen.
- Bestehende Dateiaktionen, Suche und Vorschauen auf verbundenen Verzeichnissen wiederverwenden. Papierkorb nur wenn das Dateisystem ihn unterstützt, niemals endgültiges Löschen als Ersatz.
- Verbindung im Hintergrund, Abbruch der wartenden Oberfläche und sichtbare Fehler. Späte Antworten dürfen den inzwischen gewechselten Tab nicht umleiten.
- Prüfen: Adressvalidierung, Passwortschutz, Fehler/Abbruch, persistierte Orte und echte lokale WebDAV-Verbindung mit Lesen/Schreiben/Vorschau; keine fremden Server verändern.

## Bildarbeit und Speicheranalyse
- Fotooberfläche gemäß freigegebenen Entwürfen vom 2026-10-01: großzügiges Bildraster mit unbeschnittenen Miniaturen, ruhiger Auswahlmarkierung und Herkunft; seitliche große Bildvorschau mit Name, Größe, Auflösung und lokalem/NAS-Ursprung, direkter Großansicht und Bearbeitung.
- Galerie bleibt unabhängig vom Systemthema dunkel: Bild im Mittelpunkt, Filmstreifen mit sichtbaren Miniaturen und begrenztem Cache, Pfeiltasten/Maustasten und optionaler Bearbeitungsleiste. Auswahlwechsel schützt ungespeicherte Änderungen; bestehende Sicherungen und Papierkorbbestätigung bleiben erhalten. Keine neuen Abhängigkeiten, automatische NAS-Scans oder Änderung der Ordnergrößenfunktion.
- Tabs stehen über Suche, Dateiaktionen und Pfadnavigation. Der automatische Eintrag `/mnt/games` entfällt; Dateien und Mount bleiben unverändert.
- Bilder per Doppelklick oder Leertaste in einer großen Galerie öffnen. Pfeiltasten, Nachbarbilder vorladen, Zoom/Pan, Vollbild, Drehen, Spiegeln und Undo.
- Bearbeitung explizit speichern; JPEG/PNG/WebP, keine Animationen oder Symlinks überschreiben. Original vor jedem Speichern sichern; gleichzeitige Änderungen erkennen. Papierkorb nach Bestätigung, anschließend nächstes Bild. Kein permanentes Löschen.
- Speicheranalyse für den aktuellen oder gewählten Ordner: sortierbarer Baum mit Größen und Anteilsbalken, Unterordner bei Bedarf analysieren, Abbruch, sichtbare Zugriffsfehler. GNU du für belegten Platz oder Dateigröße, keine Symlink-Rekursion und keine fremden Dateisysteme durchlaufen.
- Prüfen: Layoutposition, Bildfolge/Cache, Rotation/Spiegelung/EXIF/Sicherungen/Kollisionen, Papierkorb, Größenwerte mit Sparse-/Hardlink-/Symlink-Dateien und Abbruch; Netzwerkregressionen erhalten.

## Native Lumen-Integration
- Gemeinsame native Einstellungen über sichtbaren Button und Strg+Komma.
  Akzeptanzkriterien und Systembereiche stehen in `../NATIVE-LUMEN.md`.
  Öffnen liest nur; Änderungen explizit pro Bereich, konkurrierende Änderungen
  nicht überschreiben. Keine sachfremde Aktivierung automatischer Werkzeugfreigaben.
- Gemeinsames Chat-Panel mit der eigenständigen Lumen-App; toolbar / Strg+J und Kontextmenü öffnen es im Dateimanager.
- Sichtbarer Arbeitsordner und alle ausgewählten Pfade; native Antworten, Abbruch, Freigaben und Rückfragen.
- „Lesen & prüfen“ nutzt den Plan-Agenten, „Aufgaben erledigen“ den Build-Agenten.
- Bestehende OpenCode-Konfiguration und globale Anweisungen bleiben erhalten; keine Terminal-Fenster oder gemeinsamen temporären Chatdateien.
- Gemeinsame Implementierung: `assistant.py` und `assistant_backend.py`; API-/Formulartest in `test_assistant.py`.

- „Erklären“, „Fehler beheben“ und „Änderungen prüfen“ wirken als Dateiaktionen:
  Titel, Auswahl, Fortschritt und Ergebnis statt eines vorbereiteten Chat-Auftrags.
  Native Freigaben/Fragen, Abbrechen/Retry, Kopieren/Schließen und passende Folgeaktionen.
  Mehr Details und Ergebnis prüfen lesen ausschließlich; freier Chat bleibt separat.
