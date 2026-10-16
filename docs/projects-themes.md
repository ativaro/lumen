# Lumen Projekte: gemeinsame Themes

Projektübersicht, Journal, Quellenauswahl und Bearbeitungsdialoge verwenden die
semantischen Farben der gemeinsamen Qt-Palette. Die Projektsymbole lesen diese
Palette auch beim Zeichnen. Layout und Datenmodell bleiben unverändert.

`test_project_themes.py` prüft den Wechsel bei bereits offenen Fenstern und
Dialogen: Glas, Atelier, Graphit, Mitternacht, Clear und System sowie zurück zu
Glas. Escape verwirft den Dialog ohne Änderungen. Zusätzliche native DE/EN-Prüfung
verifiziert den Einstellungs-Dateiwächter, Mausklicks und gerenderte Oberflächen
in isolierten Profilen, auch gegen die installierten Module.

Die ältere Testgruppe `test_project_editor.py` übernimmt noch
`test_projects_rooms.py` mit überholten Projektkennungen. Ihre 21 Fehler bestehen
auch auf der unveränderten Basis; sie sind keine bestandene Regressionprüfung.
Diese Korrektur prüft nicht alle Lumen-Apps oder die KWin-Fensterdekoration.
