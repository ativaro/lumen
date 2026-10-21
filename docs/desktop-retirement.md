# Lumen Desktop: gemeinsame Server-Apps, lokale Fähigkeiten

Stand: 21.10.2026. Notes, Projects, Code, Audio Studio, Vault und Inbox öffnen
über `tools_app.py`/`code_app.py` den privaten `server_notes_app.py`-Host.
`server_app_window.py` verwendet die bestehende geräte- und kontogebundene Sitzung.
Die Fachlogik und Oberflächen dieser sechs Apps werden auf dem Server gepflegt.

Reader, Haushalt, System, Files, Gespräche und integriertes Compose bleiben lokal.
Dasselbe gilt für Mikrofon, Sprachausgabe, Datei-/Drive-Übergaben, Gedächtnis,
Bestätigung von Systemaktionen sowie den nativen Zugangsdaten-Broker. Der native
Gedächtniseditor ist keine zweite benutzbare Notes-App.

Die früheren nativen Appfenster, Code-Sammlungs-/Automationseditoren, Projekt-Replik,
lokalen Inbox-Netzwerkclients und der kopierte Offline-Notes-Webeditor sind entfernt.
`packaging/retired-desktop-files.txt` nennt ausschließlich stillgelegte Code-Dateien.
Der Benutzerinstaller entfernt diese Pfade und alte ausgelieferte Tests/Bytecodes.
Arch-Pakete und Standalone-Installer liefern nur verbleibenden Laufzeitcode aus.
Die eigenen Repositories behalten passende Tests; obsolete UI-Tests wurden entfernt.

Gemeinsam verwendete Notebook-, Sicherungs-, Referenz- und Dateifunktionen bleiben,
wenn Gedächtnis, Reader, Sicherungen oder native Übergaben sie verwenden. Historische
Schemafelder und schließende Prüfungen verhindern die Ausführung alter Code-Jobs;
sie sind kein zweiter Code-Runner. Originaldateien, Datenbanken, Sicherungen,
Zugangsdaten und bestehende Rechte werden durch diese Codebereinigung nicht geändert.

`test_desktop_retirement.py` prüft fehlende Altmodule, fehlende Imports, alle
Server-Starter, den nativen Haushalt, den verbleibenden Datenhelfer sowie die
Updatebereinigung einschließlich Symlink-Abbruch und Datenerhalt. Die vorhandenen
Server-Handoff-, Rechte-, Gedächtnis-, Datei- und Sicherungstests bleiben maßgeblich.
