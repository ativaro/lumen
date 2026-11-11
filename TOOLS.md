# Lumen Desktop: lokale Werkzeuge und gemeinsame Apps

Die vollständige Installation liefert die Starter, gemeinsame Einstellungen und die lokale Qt-Laufzeit. Für einen neuen Rechner [INSTALL.md](INSTALL.md) verwenden. `install-tools.py` ist ein älterer ergänzender Benutzerinstaller bei vorhandenen Abhängigkeiten, kein zweiter vollständiger Offline-Produktumfang. Für die aktuelle Gesamtinstallation und ihre vollständigen Starterwege den regulären Installer verwenden; die Sonderflags der heutigen `bin/`-Starter werden vom älteren Tools-Installer nicht sämtlich nachgebildet.

## Was eigenständig auf dem Desktop arbeitet

| Funktion | Einstieg | Ort der Arbeit |
| --- | --- | --- |
| Gespräche, Dateien verstehen, IT-Hilfe und Softwareinstallation | `lumen`, `lumen-search` | Lokale Lumen-Engine mit deinem eingerichteten KI-Anbieter und dessen Freigaben |
| Dateien und Netzwerkordner | `lumen-files` | Lokaler Dateimanager; Online-Konten und Netzfreigaben werden einzeln verbunden |
| Lesen | `lumen-reader` | Lokale Lesekopien, Positionen und Markierungen |
| Text- und Dokumentbearbeitung | `lumen-translate` | Lokales Compose-Fenster; KI-Aufträge verwenden den gewählten Anbieter |
| Haushalt | `lumen-household` | Lokale Geräte, Verträge, Fristen und Belege |
| System, Sound, Sicherungen | `lumen-system`, `lumen-sound` | Lokale Diagnose, Einstellungen und ausdrücklich eingerichtete Sicherungsziele |
| Gedächtnis | Lumen-Einstellungen; technisch `lumen-wissen --area lumen` | Eigene lokale Erinnerungen und Lernfreigaben |
| Mitteilungen und Bildschirmhilfe | `lumen-notification`, `lumen-companion` | Lokaler Desktop mit seinen jeweiligen Freigaben |

Dateiverwaltung, Haushalt und Systemübersicht benötigen kein Modell. Antworten und inhaltliche KI-Verarbeitung brauchen eine funktionierende Modellauswahl. Systemänderungen verwenden Werkzeugfreigaben und erforderliche Administratorrechte. Ein lokaler Desktop ist kein Versprechen ausschließlich lokaler Inferenz.

## Was die Serververbindung ergänzt

| Gemeinsame App | Kompatibler Starter |
| --- | --- |
| Lumen Notes | `lumen-wissen` |
| Lumen Projekte | `lumen-workbench` |
| Lumen Code | `lumen-code` |
| Lumen Audio Studio | `lumen-meetings`, `lumen-radio` |
| Lumen Inbox | `lumen-inbox` |
| Lumen Vault | `lumen-vault` |

Diese Starter öffnen die laufende Serveroberfläche in einem eigenen Desktopfenster. Server, Konto, App-Sitzung und Gerätefreigabe werden geprüft. Ohne Verbindung gibt es keinen zweiten lokalen Editor. Eine App installieren, öffnen oder entsperren erteilt keine neue Daten- oder Ausführungsfreigabe. Die verfügbaren Funktionen bestimmt der verbundene Server.

## Daten, Sicherungen und Altbestände

Lokale Anwendungen behalten ihre privaten Datenverzeichnisse. Frühere Notes-/Projekt-/Inbox-/Audio-Daten werden nicht durch die Entfernung alter Programmdateien gelöscht, aber auch nicht automatisch importiert oder weiter synchronisiert. Der Server ist für seine Appdaten maßgeblich. Nicht das ganze Verzeichnis bei geöffneten Datenbanken kopieren: den vorgesehenen Sicherungs-/Exportweg verwenden und eine Wiederherstellung prüfen.

`lumen-vault --backups` ist ein kompatibler Verweis auf **Lumen System → Sicherungen**. `lumen-vault --lab` ist eine ausdrücklich getrennte native Testversion, kein normaler App-Start und keine öffentliche Passwortmanager-Freigabe. [Tresor und Sicherungen](VAULT-INBOX.md).

## Entwicklung und Prüfung

[Funktionszuordnung](CAPABILITIES-tools.md), [gemeinsamer App-Host](docs/desktop-retirement.md) und [Veröffentlichung](PUBLISHING.md) beschreiben die aktuellen Grenzen. Für Tests temporäre HOME/XDG- und `LUMEN_TOOLS_DATA`-Profile verwenden. Keine persönlichen Konten, Tresore oder Desktop-Sitzungen als Testumgebung einsetzen. Bereits dokumentierte Abnahmen belegen ihren jeweiligen Sourcepin, nicht automatisch jeden späteren Stand.
