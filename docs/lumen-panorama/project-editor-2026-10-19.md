# Lumen Projekte: ruhiger Aufgabeneditor

Die zuvor schmale Seitenleiste konkurrierte mit der zusätzlichen Journalspalte.
Beim Bearbeiten sind jetzt höchstens Projektinhalt und ein 520–560 Einheiten
breiter Editor nebeneinander sichtbar. Unter 1160 Einheiten übernimmt der Editor
den Inhaltsbereich; Schließen stellt das Journal samt seiner Seiteninhalte wieder
her. Auch bei 840 × 660 bleiben die festen Speichern-/Abbrechen-Aktionen erreichbar;
der Formularinhalt scrollt. Keine zusätzliche globale App-Leiste.

Bezeichnung und gewünschtes Ergebnis stehen zuerst. Die unveränderbare bestehende
Zuordnung und Bearbeitungsart stehen im Kontextkopf; neue Aufgaben behalten ihre
explizite Vorhaben-/Art-Auswahl. Aufgabe, Material und Ergebnisse haben einen
sichtbaren ausgewählten Reiter. Der Rhythmus erscheint nur bei eingeschalteter
Wiederholung. Notizen, Laufdaten, Deep Research und Abhängigkeiten liegen unter
„Weitere Angaben“. Speichern führt die Aufgabe nicht aus. Konflikt-, Schreibschutz-,
Zeitplan- und Quellenlogik bleiben erhalten.

## Abgleich und Abnahme

Panorama-Referenz aus `standard.md` gelesen und als Vergleich gerendert: Glas,
Projekt/Aufgabe, vergleichbare Fenstergröße und synthetischer Wärmepumpenauftrag.
Gemeinsame Flächen, Palette, Abstände, beschriftete Felder und Seiteneditor
übernommen. Bewusste native Anpassungen: breiterer Editor für lange Aufträge,
mehr Platz für das Ergebnisfeld und feste untere Aktionen; keine Web-App-Leiste.
Die beiden anderen Spalten des bisherigen Formulars werden bei kleinen Fenstern
nicht untereinander gedrückt.

32 gezielte Prüfungen aus aktuellen Projektjournal-, Dialog-, Theme-, Editor-
und Migrationstests bestehen sowohl gegen Quellmodule als auch gegen installierte
Produktmodule. Geprüft: Änderungen speichern/abbrechen/verwerfen, Quellen getrennt
halten, bestehende Intervalle und Notizen behalten, Wiederholung, Schreibschutz,
Reiter per Tastatur, Feldfokus und vier Themes. Ein erster installierter Prüflauf
scheiterte nur an der fehlenden CLI-AST-Testdatei im isolierten Testpaket. Die
Datei wurde aus der installierten Runtime übernommen; Fehlerbeleg bleibt erhalten.

Echte synthetische Qt-Aufnahmen: vier Themes, 1440 × 1000, 1040 × 900 und
840 × 660, Zusatzangaben, Ergebnisse, Journal und Neuanlage. Alle 28 deutschen Quell-/Runtime-Aufnahmen sind bytegleich. Zusätzliche englische
Prüfrunde. Kein persönliches Produktionsprofil und keine laufenden persönlichen
Fenster geöffnet, beendet oder neu gestartet. Keine echten KI-/Netzwerkaufrufe,
kein vollständiger Screenreader- oder Desktop-Gesamttest.

## Entfernung alter Arbeitsraum-Oberflächen

Auf ausdrücklichen Nutzerwunsch entfernt: `files/workplace_rooms.py`,
`files/projects_rooms.py` und deren überholte Tests `test_workplace_rooms.py`,
`test_projects_rooms.py`, `test_project_editor.py`. Kein verbleibender Import
in den aktuellen Python-Aufrufern. Aktuelle Aufgabeneditor-Regressionen werden
von `test_project_panorama.py` und den bestehenden Journal-/Dialogtests abgedeckt.

Bestehende Daten werden nicht gelöscht. `projects_legacy.py` liest weiterhin
historische `room`-/`project_rooms`-Zuordnungen ausschließlich zur idempotenten
Übernahme in Lumen-Projekte; Originalmaterial, Entwürfe und Zuordnungen bleiben
erhalten. Die aktive technische Klasse in `lumen_workplace.py` dient weiterhin
Übertragungen/Verlauf und System-Arbeitsmodi; sie bindet keine Arbeitsraumansicht
ein. Diese Hilfsfunktionen sind kein globales Arbeitsraum-Produktmodell.

## Installation und Rückweg

Drei Runtime-Dateien aktualisiert, dabei 633 andere Code-/Asset-Dateien unverändert.
Die alten Raum-Module waren in der installierten Runtime bereits nicht mehr
vorhanden; das letzte veraltete `test_project_editor.py` wurde dort separat
entfernt. Broker, Daten und persönliche Prozesse unverändert. Server/Mobile
wurden nicht geändert.

Belege, tatsächliche Aufnahmen, Hashmanifeste und Rückwege:
`~/.local/state/lumen/projects-panorama-20261019/`.
Zuerst `cleanup/install-desktop.py rollback --apply`, danach
`install-desktop.py rollback --apply`; beide prüfen die betroffenen Dateien vor
Änderungen. Für den Hauptschritt wurde Installation/Rollback an einer kleinen
Wegwerfkopie geprüft. Alte Fenster laden die Änderung beim normalen Wiederöffnen.
