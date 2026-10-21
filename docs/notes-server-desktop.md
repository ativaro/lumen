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

Der gemeinsame Host erneuert seine auf 15 Minuten begrenzte App-Sitzung eine
Minute vor Ablauf über die bestehende native Geräteverbindung. Auch eine nur
zeitlich abgelaufene Sitzung lässt sich im selben Fenster erneut prüfen;
Editor, Cookie und CSRF bleiben erhalten. Die Erneuerung enthält keine
Inhaltsänderung und wiederholt keine Schreibaufträge. Server, Konto, Gerät,
App und aktuelle Freigaben werden erneut geprüft. Abmeldung, Sitzungsrotation
und Widerruf können nicht dadurch rückgängig gemacht werden. Ein unbekannter
Schreibausgang bleibt gesperrt. Das gilt ebenso für Projekte, Code, Audio Studio,
Vault, Inbox und den gemeinsamen Compose-Host.
