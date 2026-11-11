> **Historischer Entwurf oder Abnahmebeleg – keine aktuelle Installationsanleitung.** Der normale Radio-Starter öffnet Lumen Audio Studio auf dem verbundenen Server. Die lokale Modell-/Speicherarchitektur unten beschreibt den früheren Stand. Aktuelle Zuordnung: [Desktop-Verantwortlichkeiten](docs/desktop-retirement.md).

# radio

## Ziel und Abnahme
Explizit gewählte HTTPS-Artikel und lokale Dokumente/Text als Quellen sammeln. Webseiten abrufen ohne Login/Cookies, Textvorschau und Quelle zeigen; unpassende/gesperrte Seiten können als Text eingefügt werden. Nur ausgewählte Quellen gehen nach Knopfdruck an den eingerichteten KI-Provider. Hörskript bleibt editierbar; Quellen werden von der Anwendung referenziert. Piper erzeugt lokale WAV-Ausgabe; native Wiedergabe/Pause/Seek und WAV/Markdown-Export. Alte Ausgabe bleibt bis erfolgreicher Neuerzeugung erhalten. Quelllimits werden sichtbar erklärt, nichts unbemerkt abschneiden. Prüfung: Auswahllogik, Parser/URL-Grenzen, echte synthetische Sprachausgabe, abgebrochene Erzeugung, Persistenz.

## Umsetzung und Prüfung
Python/PySide6, stdlib SQLite, bestehende appearance.py/assistant_backend.py/Sprachwerkzeuge. Quellen unter files/, Starter bin/, Desktop-Dateien data/applications/. Kein zusätzlicher Server/Frontend-Stack.
Stil: kleine Funktionen, snake_case, bestehende native Widgets; beispielsweise `store.update(record_id, title=title.strip())`.
Prüfen: `QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s files -p 'test_tools*.py' -v`. Starten: `./bin/lumen-radio`. Paket: `./packaging/arch/build-package.sh`.
Immer: lokale private Speicherung, explizite Importe, atomare Schreibvorgänge, verständliche Fehler, Abbruch, native Tastaturbedienung. Keine persönlichen Daten/Modelle in Git. Kein Überschreiben der Originale. KI läuft erst nach ausdrücklicher Aktion mit den ausgewählten Inhalten über den eingerichteten Provider; dies muss sichtbar sein. Modellantworten sind untrusted Vorschläge und werden validiert. Neue externe Dienste/Abos oder Löschung von Originalen erfordern einen eigenen Auftrag.
