# Lumen Projekte auf dem Desktop

Lumen Projekte ist eine gemeinsame **Server-App**, die der Desktop in einem eigenen Fenster öffnet. `lumen-workbench` bleibt der kompatible Starter; er startet keinen lokalen Projekt-Runner und keine zweite Projektdatenbank.

## Öffnen und arbeiten

1. Lumen Server verbinden und unter **Geräte → dieses Gerät → Serverdaten** die Projektfreigabe prüfen.
2. **Lumen Projekte** im App-Menü oder `lumen-workbench` öffnen.
3. Ein vorhandenes Projekt wählen oder im gemeinsamen Projekteditor anlegen. Projekte fassen ausgewählte Materialien, Gespräche und Aufgaben zusammen.
4. Quellen und Aufträge bewusst auswählen. Eine Verknüpfung startet keine Arbeit und erweitert keine Zugriffsrechte.

Die sichtbaren Funktionen und Ausführungen stammen vom verbundenen Server. Persönliche Aufgaben, Fälligkeiten und Erinnerungen sowie vorhandene Code-Aktionen folgen dessen jeweiligen Freigaben. Ein abgeschlossener automatischer Lauf ist nicht automatisch eine vom Nutzer erledigte Aufgabe. [Server-Dokumentation](https://forge.example.invalid/ativaro/lumen-server/src/branch/main/docs/projects.md) (privater Zugang erforderlich).

## Quellen und Freigaben

Der Desktop kann ein ausgewähltes Material über den geprüften Übergabedialog an das Projekt geben. Lokale Pfade sind für den Server nicht automatisch lesbar. Eine benötigte Datei muss über den vorgesehenen Drive-/Kopierweg bewusst bereitgestellt werden; Herkunft und aktuelle Kontobindung werden geprüft. Projektmitgliedschaft allein gibt keine privaten Dateien oder Gespräche frei.

Im lokalen Lumen-Gespräch können passende Serverwerkzeuge verfügbar sein. Der eingerichtete Katalog und die aktuellen Gerätefähigkeiten sind maßgeblich; alte lokale `lumen_project_*`-Werkzeuge sind stillgelegt. Ein unklarer Schreib- oder Startausgang darf nicht blind wiederholt werden.

## Ohne Verbindung und vorhandene Daten

Ohne erreichbaren Server oder Projektfreigabe bietet der Starter die Verbindungsprüfung an. Es gibt keinen stillen lokalen Ersatz und keinen zusätzlichen Offline-Projekteditor. Lokale Lumen-Gespräche, Dateien und Systemhilfe bleiben unabhängig nutzbar.

Frühere Daten unter `lumen-tools/workbench` werden durch die Bereinigung alter Programmdateien nicht gelöscht. Sie werden dadurch aber auch nicht automatisch als neue Serverprojekte importiert. Alte Wiederholungsintervalle und lokale Projekt-Timer sind kein aktuelles Installationsrezept.

## Technischer Weg

`bin/lumen-workbench` → `files/tools_app.py` → `files/server_notes_app.py` → `files/server_app_window.py`. Die Sitzung ist an Server, Konto, Gerät und App gebunden und wird im selben Fenster erneuert. Ein App-Neustart oder Session-Refresh genehmigt und wiederholt keine Schreiboperation.

[Desktop-Verantwortlichkeiten](docs/desktop-retirement.md) · [Server-App-Verbindung](docs/notes-server-desktop.md) · [Übergaben](docs/interop/USAGE.md)
