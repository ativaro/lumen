# meetings

## Ziel und Abnahme
Aufnahmen als private Kopie importieren; ffmpeg wandelt Audio für die lokale Whisper-Erkennung. Segmenttext mit Millisekunden gespeichert. Anklicken spielt die Originalaufnahme ab der Zeitstelle. Erkennung ist abbrechbar, Sprache/Fachbegriffe in Einstellungen. KI erzeugt editierbare Zusammenfassung, Entscheidungen und Aufgaben mit nachprüfbaren Segmentverweisen. Markdown-Export; Wiederöffnen nach Neustart. Keine automatische Aufnahme von Gesprächen. Prüfung mit synthetischer deutscher Aufnahme, JSON-Zeitmarken, Cancel und Wiederöffnen.

## Umsetzung und Prüfung
Python/PyQt5, stdlib SQLite, bestehende appearance.py/assistant_backend.py/Sprachwerkzeuge. Quellen unter files/, Starter bin/, Desktop-Dateien data/applications/. Kein zusätzlicher Server/Frontend-Stack.
Stil: kleine Funktionen, snake_case, bestehende native Widgets; beispielsweise `store.update(record_id, title=title.strip())`.
Prüfen: `QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s files -p 'test_tools*.py' -v`. Starten: `./bin/lumen-meetings`. Paket: `./packaging/arch/build-package.sh`.
Immer: lokale private Speicherung, explizite Importe, atomare Schreibvorgänge, verständliche Fehler, Abbruch, native Tastaturbedienung. Keine persönlichen Daten/Modelle in Git. Kein Überschreiben der Originale. KI läuft erst nach ausdrücklicher Aktion mit den ausgewählten Inhalten über den eingerichteten Provider; dies muss sichtbar sein. Modellantworten sind untrusted Vorschläge und werden validiert. Neue externe Dienste/Abos oder Löschung von Originalen erfordern einen eigenen Auftrag.
