# Lumen Desktop: gemeinsame Server-Apps, lokale Fähigkeiten

Quellvertrag der veröffentlichten Desktoplinie; aktuelle Zuordnung: Notes, Projects, Code, Audio Studio, Vault und Inbox öffnen
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

## Installation, Offline und Kompatibilität

Der [Benutzerinstaller](../INSTALL.md) liefert die aktuellen Starter. Die normale
Vault-App wird nicht durch eine vorhandene Laborinstallation ersetzt;
`lumen-vault --lab` bleibt der ausdrückliche Laborweg, `--backups` führt zu
Lumen System. `lumen-wissen --area lumen` öffnet das lokale Gedächtnis, während
der normale Notes-Aufruf zum Server führt. Compose bleibt lokal; der private
Compose-Text-Pilot ist kein allgemein freigeschalteter Serverersatz.

Vorhandene lokale Notes-/Projekt-/Inbox-/Audio-Daten werden nicht gelöscht.
Sie werden aber auch nicht durch die bloße Installation automatisch importiert.
Alte handschriftliche Angaben zu Rooms, lokalen Projekt-Timern und
Notes-Ordnersynchronisation beschreiben keinen weiteren Produktmodus.

Reguläre Desktop-Gespräche, tiefe Analysen ausgewählter Dateien und genehmigte
Systemaktionen bleiben ohne Lumen Server verfügbar. Der eingerichtete Anbieter
und seine Rechte bestimmen die KI-Ausführung. Ein verbundener Server erweitert
diesen Umfang, ohne pauschal die lokale Festplatte lesen zu dürfen.
