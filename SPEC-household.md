# household

## Ziel und Abnahme
Geräte und Verträge mit Titel, Hersteller/Anbieter, Modell/Vertragsnummer, Kauf-/Beginn-Datum, Garantie-/Vertragsende, Kündigungs-/Erinnerungsdatum und Notizen. Belege/Handbücher werden privat kopiert, einzeln geöffnet und entfernt; Originale bleiben erhalten. Suche nach Metadaten und Text aus Belegen (PDF/Text/Bild-OCR). Fällige Fristen im Eintrag sichtbar. Änderungen nach Neustart erhalten. Prüfung: Import, Suche, Update, Fristen, Entfernen ohne Originalverlust. Keine Rechtsberatung oder automatische Kündigung.

## Umsetzung und Prüfung
Python/PySide6, stdlib SQLite, bestehende appearance.py/assistant_backend.py/Sprachwerkzeuge. Quellen unter files/, Starter bin/, Desktop-Dateien data/applications/. Kein zusätzlicher Server/Frontend-Stack.
Stil: kleine Funktionen, snake_case, bestehende native Widgets; beispielsweise `store.update(record_id, title=title.strip())`.
Prüfen: `QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s files -p 'test_tools*.py' -v`. Starten: `./bin/lumen-household`. Paket: `./packaging/arch/build-package.sh`.
Immer: lokale private Speicherung, explizite Importe, atomare Schreibvorgänge, verständliche Fehler, Abbruch, native Tastaturbedienung. Keine persönlichen Daten/Modelle in Git. Kein Überschreiben der Originale. KI läuft erst nach ausdrücklicher Aktion mit den ausgewählten Inhalten über den eingerichteten Provider; dies muss sichtbar sein. Modellantworten sind untrusted Vorschläge und werden validiert. Neue externe Dienste/Abos oder Löschung von Originalen erfordern einen eigenen Auftrag.
