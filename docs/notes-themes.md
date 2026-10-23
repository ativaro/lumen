> **Historischer Entwurf oder Abnahmebeleg – keine aktuelle Installationsanleitung.** Der lokale Notes-Editor und sein kopierter Offline-Webeditor sind entfernt. Die aktuellen Notes-Farben und Inhalte kommen über den Server-Host. Aktuelle Zuordnung: [Desktop-Verantwortlichkeiten](desktop-retirement.md).

> Historischer Stand des entfernten nativen Notes-Editors. Aktuell: [Desktop-Verantwortlichkeiten](desktop-retirement.md).

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

Auf ausdrücklichen Nutzerwunsch verwendet Notes seit 19.10.2026 die vollständige
Servergestaltung statt der früheren Desktop-Nachbildung: Navigation bis 190,
Notizliste bis 250 Pixel, Originalschrift, Abstände und Rundungen aus dem
Server-Snapshot. Farben und ein ausdrücklich gewählter anderer Desktop-Font
folgen weiterhin der nativen Auswahl. Die Formatleiste darf wie auf dem Server
umbrechen; Reihenfolge, Funktionen und erreichbare Ziele bleiben erhalten.
Lange Notiztitel haben zusätzlich einen Tooltip.

Linkfelder verwenden Abstand zwischen Label und Eingabe; Eingaben und Aktionen
fluchten unten. Lange gültige Tags umbrechen innerhalb der Schreibfläche, der
Entfernenknopf bleibt sichtbar und bedienbar. Schriftgrößen folgen nun den
originalen Serverregeln. Fehlende englische Notes-
Beschriftungen sind aus den bestehenden Desktop-Übersetzungen übernommen.

`test_notes_web.py` prüft diese konkreten Fälle einschließlich eines erhaltenen
ungespeicherten Entwurfs beim Themewechsel. Die Sichtprüfung muss zusätzlich am
echten Editor erfolgen; grüne Logiktests ersetzen keinen Referenzvergleich.
