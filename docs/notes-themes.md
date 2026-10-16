# Lumen Notes: gemeinsame Themes

Notes übernimmt die gemeinsame Qt-Palette statt einer fest eingestellten
Graphit-Palette. Navigation, Notizliste, Editor, Menüs, Auswahl und Symbole folgen
dem gewählten Theme auch bei geöffnetem Fenster. Geschützte Markdown-Abschnitte
werden bei einem Palettenwechsel als Vorschaugrafik neu gezeichnet, ohne den
Notiztext neu zu laden. Halbtransparente neutrale Tabellenlinien passen sich dem
Untergrund an, ohne Formatänderungen in den Rückgängig-Verlauf einzufügen.

`test_notes_themes.py` prüft Glas, Atelier, Graphit, Mitternacht, Clear und System
sowie den Rückwechsel. Ungespeicherter Text, Rückgängig/Wiederholen und Speichern
bleiben erhalten. Bestehende Tabellen-, Link- und Layoutprüfungen ergänzen diesen
Test. Native DE/EN-Prüfungen gegen die installierten Module bestätigen außerdem
den tatsächlichen Einstellungs-Dateiwächter in isolierten Profilen.

Diese Korrektur ändert keine Notizdateien oder KWin-Dekorationen. Eine bereits
laufende alte Notes-Version muss regulär geschlossen und erneut geöffnet werden.
