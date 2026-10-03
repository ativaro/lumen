# workbench

## Ziel und Abnahme
Benannte Projekte mit Datei-Verknüpfungen, Weblinks, Notizen und abhakbaren offenen Fragen; alles in einem nativen Fenster. Dateien in Standard-App öffnen, Links im Browser, Notizen und Fragen dauerhaft speichern. Bestehende Dateien nicht verschieben. Einträge entfernen und Projekt archivieren/wiederherstellen; Markdown-Export. Prüfung: Projektwechsel/Neustart bewahren Notizen und Frage-Status, entfernte Verknüpfung lässt Datei bestehen.

## Umsetzung und Prüfung
Python/PySide6, stdlib SQLite, bestehende appearance.py/assistant_backend.py/Sprachwerkzeuge. Quellen unter files/, Starter bin/, Desktop-Dateien data/applications/. Kein zusätzlicher Server/Frontend-Stack.
Stil: kleine Funktionen, snake_case, bestehende native Widgets; beispielsweise `store.update(record_id, title=title.strip())`.
Prüfen: `QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s files -p 'test_tools*.py' -v`. Starten: `./bin/lumen-workbench`. Paket: `./packaging/arch/build-package.sh`.
Immer: lokale private Speicherung, explizite Importe, atomare Schreibvorgänge, verständliche Fehler, Abbruch, native Tastaturbedienung. Keine persönlichen Daten/Modelle in Git. Kein Überschreiben der Originale. KI läuft erst nach ausdrücklicher Aktion mit den ausgewählten Inhalten über den eingerichteten Provider; dies muss sichtbar sein. Modellantworten sind untrusted Vorschläge und werden validiert. Neue externe Dienste/Abos oder Löschung von Originalen erfordern einen eigenen Auftrag.
