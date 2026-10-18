# Lumen Projekte: gemeinsame Themes

Projektübersicht, Journal, Quellenauswahl und Bearbeitungsdialoge verwenden die
semantischen Farben der gemeinsamen Qt-Palette. Die Projektsymbole lesen diese
Palette auch beim Zeichnen. Layout und Datenmodell bleiben unverändert.

`test_project_themes.py` prüft den Wechsel bei bereits offenen Fenstern und
Dialogen: Glas, Atelier, Graphit, Mitternacht, Clear und System sowie zurück zu
Glas. Escape verwirft den Dialog ohne Änderungen. Zusätzliche native DE/EN-Prüfung
verifiziert den Einstellungs-Dateiwächter, Mausklicks und gerenderte Oberflächen
in isolierten Profilen, auch gegen die installierten Module.

Die unbenutzten Arbeitsraum-Oberflächen `workplace_rooms.py` und
`projects_rooms.py` sowie ihre überholten Testgruppen wurden am 19.10.2026
entfernt. Die aktuellen Projektwege werden durch `test_projects_journal_current`,
`test_project_dialogs` und `test_project_panorama` geprüft. `test_projects_legacy`
sichert weiterhin die Übernahme alter Zuordnungen, Materialien und Entwürfe.
Alte gespeicherte Daten werden nicht gelöscht. Diese Korrektur prüft nicht alle
Lumen-Apps oder die KWin-Fensterdekoration.

## Wiederherstellen der Projektauswahl

Beim Start und beim Öffnen eines Projektverweises wird das Journal gezeigt.
Die Projektauswahl öffnet keinen eingebetteten Editor mehr. Aufgaben und Vorhaben
öffnen weiterhin ihren eigenen Editor; neue Einträge behalten ihren Anlegeweg.
Quellenverweise wählen die aktuelle Quellenansicht mit dem geprüften Inhalt,
setzen die bestehende Auswahl für Übergaben und scrollen zum passenden Eintrag.
Verzögerte Scroll-Aufrufe sind an die Lebensdauer ihres Widgets gebunden.

Regressionen decken Projektauswahl, Aufgabenentwürfe (Abbrechen/Speichern),
Quellenverweise und Scrollen ab. Der tatsächliche `tools_app.main`-Start mit
`window.ini`-Auswahl wurde zweimal je DE/EN-Profil vor und nach Installation
geprüft, ohne persönliche Profile zu verwenden.
