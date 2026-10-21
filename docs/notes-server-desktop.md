# Lumen Notes auf Desktop

Lumen Notes verwendet dieselbe laufende Server-Oberfläche und denselben
Datenbestand wie Lumen Server. `tools_app.py` → `server_notes_app.py` →
`server_app_window.py` öffnet sie mit der bestehenden Geräteanbindung.
Berechtigungen und Widerruf gelten weiterhin; ohne Anbindung gibt es keinen
zweiten lokalen Benutzer-Notizeditor und keinen separaten Notes-Abgleich.

Die früher kopierten Serverkomponenten, der Offline-WebChannel-Editor und dessen
Buildskript sind entfernt. Für die Oberfläche wird ausschließlich der Server
entwickelt und bereitgestellt. Der lokale Gedächtniseditor bleibt unabhängig
davon erhalten. Einzelheiten: [Desktop-Verantwortlichkeiten](desktop-retirement.md).
