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


## Panorama-Abstände und kompakte Schreibfläche

Der Notes-Webeditor verwendet für Dokumentinnenränder und Rundungen die bereits
übergebenen Desktop-/Theme-Tokens. Die Navigation bleibt 224 logische Pixel breit,
die Notizliste folgt mit 210 Pixeln der freigegebenen Referenz. Icon-Schaltflächen
der vorhandenen Formatleiste sind quadratisch; die Reihenfolge und Funktionen
bleiben erhalten. Bei 1280 Pixeln passt die Leiste in eine Zeile, bei kleineren
Fenstern darf sie umbrechen. Lange Notiztitel haben zusätzlich einen Tooltip.

Linkfelder verwenden Abstand zwischen Label und Eingabe; Eingaben und Aktionen
fluchten unten. Lange gültige Tags umbrechen innerhalb der Schreibfläche, der
Entfernenknopf bleibt sichtbar und bedienbar. Aktionsbeschriftungen verwenden die
14-Pixel-Bediengröße, Metadaten bleiben bei 12 Pixeln. Fehlende englische Notes-
Beschriftungen sind aus den bestehenden Desktop-Übersetzungen übernommen.

`test_notes_web.py` prüft diese konkreten Fälle einschließlich eines erhaltenen
ungespeicherten Entwurfs beim Themewechsel. Die Sichtprüfung muss zusätzlich am
echten Editor erfolgen; grüne Logiktests ersetzen keinen Referenzvergleich.
