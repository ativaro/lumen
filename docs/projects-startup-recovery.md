> **Historischer Entwurf oder Abnahmebeleg – keine aktuelle Installationsanleitung.** Der konkrete damalige Offscreen-Prozess ist kein aktueller Störungsnachweis. Keine persönlichen Prozesse anhand dieser alten PID-/Pfadangaben beenden; heutige Projekte laufen im Server-Host. Aktuelle Zuordnung: [Desktop-Verantwortlichkeiten](desktop-retirement.md).

# Lumen Projekte: unsichtbare Testinstanz blockiert den Start

18.10.2026: Der normale Projekte-Starter war korrekt. Eine ältere Offscreen-
Abnahmeinstanz aus `ponytail-fixes-20261018/desktop` hielt jedoch die echte
`~/.local/share/lumen-tools/workbench/window.lock`. Ihr `LUMEN_DATA` war temporär,
`LUMEN_TOOLS_DATA` fehlte; deshalb benutzte sie die persönliche Tools-Bibliothek.
Weitere Starts wurden erfolgreich an ihr unsichtbares Fenster weitergereicht.
Die Sperre wurde nach Prüfung von exaktem Prozesspfad, Argumenten, Offscreen-
Plattform und tatsächlich gehaltenem Lock gezielt durch SIGTERM gelöst.
Projektinhalte wurden nicht geändert. Die echte Fenstersperre ist wieder frei.

Ein auslösender alter Testweg ist
`files/test_lumen_os.py::LumenIntegrationTest.test_native_pages_workflow_result_and_source_context`:
Er setzt lediglich `LUMEN_DATA` und ruft inzwischen externe Seiten auf.
Der neue Schutz am gemeinsamen Tools-Einstieg weist Offscreen-/Minimal-Starts
zurück, wenn nicht **beide** Datenpfade ausdrücklich gesetzt sind. Die Prüfung
findet vor QApplication-Erzeugung, Bibliotheksöffnung und Sperrübernahme statt.
Normale sichtbare Desktop-Starts benötigen diese Testvariablen weiterhin nicht.

Regression: fehlende einzelne Testpfade werden ohne App-/Bibliothekszugriff
abgewiesen; explizite Testpfade behalten die vorhandene Aktivierung. Native
synthetische A/B-Profile prüfen Kaltstart und erneutes Aktivieren von Projekte.
Die persönliche Sitzung wird nicht als Testumgebung neu gestartet. Ein
Neuaufruf durch den Nutzer zeigt den normalen Projekte-Weg wieder an.
Belege, vorherige Startdatei und begrenzter Rückweg:
`~/.local/state/lumen/projects-start-20261018/`.
