# Lumen Notes und Lumen Gedächtnis

**Notes und Gedächtnis sind getrennte Funktionen.** Notes ist die gemeinsame Notiz-App auf Lumen Server. Das lokale Gedächtnis unterstützt die eigenständig nutzbaren Desktop-Gespräche und benötigt dafür keinen Lumen Server.

## Lumen Notes öffnen

**Lumen Notes** im App-Menü oder `lumen-wissen` öffnet die Server-App in einem Desktopfenster. Die historische Kennung `wissen` bleibt für Starter und Verweise erhalten; sie bezeichnet keine zusätzliche lokale Notiz-App.

Voraussetzung sind die bestehende Serververbindung, das passende Konto und die Gerätefreigabe **Notes**. Notizen, Sammlungen, Formatierung und Änderungen liegen beim Server. Nur dort aktuell berechtigte Inhalte sind sichtbar. Die Freigabe einer Notiz für Lumen ist eine eigene Entscheidung, keine automatische Folge ihrer Speicherung oder Synchronisation.

Bei unterbrochener Verbindung oder entzogenen Rechten zuerst **Serververbindung öffnen**, **Gerätefreigabe öffnen** beziehungsweise **Erneut prüfen** verwenden. Der Desktop startet keinen lokalen Ersatzeditor. Ein erfolgreicher Verbindungsaufbau ist keine Bestätigung einer zuvor unklar gebliebenen Speicherung.

Ausgewählte Reader-Stellen, Texte und Dateien können über **Als Notiz speichern …** an den überprüfbaren Server-Übergabedialog gehen. Ein direkter Aufruf wie `lumen-wissen /pfad/notiz.md` ist im normalen Notes-Einstieg nicht mehr unterstützt. [Server-App und Übergaben](docs/notes-server-desktop.md).

## Lokales Gedächtnis

Das Gedächtnis ist über die persönlichen Lumen-Einstellungen erreichbar; der technische Direkteinstieg lautet `lumen-wissen --area lumen`. Es hält freigegebene Fakten, Vorlieben, Entscheidungen und gegebenenfalls bestätigte Lösungen für spätere Gespräche bereit. Herkunft, Korrektur und Vergessen bleiben nachvollziehbar.

**Gedächtnis verwenden**, **Aus Gesprächen lernen** und die Übernahme von Vorschlägen sind getrennte Einstellungen. Installation oder Serverkopplung ist keine pauschale Zustimmung zum Lernen. Ohne aktivierte Gedächtnisnutzung bleiben normale Desktop-Gespräche und Dateiaktionen nutzbar.

Der Lernweg nutzt den eingerichteten Anbieter in einer getrennten, begrenzten Sitzung. Er kann damit einen Cloud-Anbieter verwenden. Die aktuelle Implementierung lässt das Modell Aussagen mit wörtlichem Beleg vorschlagen und prüft Freigaben, Herkunft und konkurrierende Änderungen vor Übernahme. Eine positive Bestätigung des Nutzers ist für eine gelernte Lösung nötig; ein erfolgreicher Werkzeugstatus reicht nicht.

Gespeicherte Lösungen sind Kontext, keine Ausführungsfreigabe. Vergessen entzieht den lokalen Kontext, löscht aber keine früheren Gespräche, unabhängigen Sicherungen oder bereits an einen Anbieter übertragenen Inhalte. [Lernvertrag](docs/memory/LEARNING.md).

## Vorhandene lokale Notizdaten

Die früheren Markdown-Notizbücher, Entwürfe, Verlaufsdateien und privaten Datenbanken werden durch die Stilllegung des lokalen Notes-Fensters nicht gelöscht. Die alte Ordnerauswahl und ihr separater Notes-Abgleich sind jedoch keine aktuelle Bedienung des gemeinsamen Servereditors. Eine automatische vollständige Übernahme alter Notizbücher oder ihrer Versionsgeschichte wird nicht zugesichert.

Eigene Markdown-Dateien kannst du weiterhin in Lumen Files und geeigneten lokalen Editoren öffnen. Die aktuelle Server-App erhält sie nur durch eine unterstützte, ausdrücklich bestätigte Übergabe. Sicherungen der alten Originaldaten bis zur geprüften Übernahme behalten.

[Desktop-Verantwortlichkeiten](docs/desktop-retirement.md) · [Lokale Dateien](files/README.md) · [Installation](INSTALL.md)
