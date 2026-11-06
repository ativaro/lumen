# Lumen Vault, Sicherungen und Inbox auf dem Desktop

Tresor, Gerätesicherungen und E-Mail sind getrennte Funktionen. Der normale Desktop-Starter für Vault und Inbox öffnet die jeweilige **Lumen-Server-App**. Lokale Sicherungen und der separat eingerichtete native Zugangsdaten-Broker bleiben davon unabhängig.

## Lumen Vault öffnen

`lumen-vault` oder **Lumen Vault** im App-Menü öffnet den gemeinsamen Servertresor. Voraussetzung sind Serververbindung, Konto und die Gerätefreigabe `vault_sync`. Die Sitzung bleibt an dieses Konto, Gerät und die App gebunden. Ohne Verbindung gibt es keinen automatischen lokalen Ersatz.

Anmeldung am Server und Entsperren des Tresors sind verschiedene Schritte. Die Freigabe eines Eintrags für Lumen macht sein Secret nicht zum freien Modellkontext: Eintragskatalog und konkrete Nutzung haben getrennte Regeln. Die sichtbare Bestätigung der jeweiligen Aktion bleibt maßgeblich. [Server-Tresor und Grenzen](https://forge.example.invalid/ativaro/lumen-server/src/branch/main/docs/vault-web.md) (privater Zugang erforderlich).

## Lokale Sicherungen

Öffne **Lumen System → Sicherungen** oder:

```sh
lumen-system --page backups
```

Der bisherige Aufruf `lumen-vault --backups` führt zum selben Systemfenster. Die Sicherungsansicht verwendet den lokalen Sicherungsdienst, Restic, gewählte Quellen und Ziele sowie gegebenenfalls den System-Schlüsselbund. Ein normaler Vault-Start öffnet nicht mehr diese Backup-Oberfläche.

Wähle die zu schützenden Dateien und ein erreichbares Ziel. Bewahre den unabhängigen Sicherungsschlüssel getrennt auf und prüfe eine Wiederherstellung, bevor du dich auf einen Zeitplan verlässt. Verschlüsselter Tresorstand und Restic-Sicherung sind unterschiedliche Datenformate mit unterschiedlichen Schlüsseln. Eine Sicherung ist weder ein bootfähiges Systemabbild noch automatisch ein konsistenter Export jeder laufenden Anwendung.

Der Benutzer-Timer `lumen-vault.timer` führt ausdrücklich eingerichtete Pläne aus. Er berücksichtigt Schlüsselverfügbarkeit, Schonungsregeln und erreichbare Ziele. Ohne eingerichteten Zeitplan entstehen keine regelmäßigen Sicherungen. Bereits vorhandene Ziele werden geprüft; ein fehlendes NAS wird nicht still durch einen neuen lokalen Bestand ersetzt. Wiederherstellungen bleiben getrennt von Originaldateien. Es gibt kein automatisch aktiviertes Löschen alter Sicherungsstände.

Ein gekoppelter Lumen Server kann als verschlüsseltes Ziel dienen, wenn Speicher und Gerätezugriff eingerichtet sind. Wiederherstellung auf einem anderen Gerät benötigt die passende Serverfreigabe und den bisherigen Sicherungsschlüssel. Eine Statusmeldung allein beweist nicht, dass alle Inhalte wiederherstellbar sind.

## Nativer Zugangsdaten-Broker und Testoberfläche

Die native Rust-/Qt-Vorabversion ist ausdrücklich getrennt:

```sh
lumen-vault --lab
```

Das verlangt eine vorhandene Laborinstallation. Die normale Installation baut diese Binärdateien nicht nach und wird durch ihre Existenz nicht auf das Laborfenster umgeleitet. Der Broker kann genehmigte Zugangsdatenaktionen ausführen, ohne Secrets als Werkzeugargumente oder an das Sprachmodell herauszugeben. Sein eigener Eintragskatalog, lokales Entsperren und die Bestätigung der konkreten Nutzung bleiben erforderlich.

Diese Komponente trägt weiterhin `PRODUCTION_READY=false`; eine unabhängige vollständige Sicherheitsfreigabe ist nicht dokumentiert. Die vorhandenen nativen KDBX-, Browser-/SSH-/HTTP-/MCP- und Hintergrundtransport-Verträge gelten nur für diese ausdrücklich eingerichtete Vorabversion, nicht als Zusicherung eines zweiten regulären Offline-Tresors. [Native Anleitung und Schutzgrenzen](native/vault-ui/README.md).

## Lumen Inbox und Kalender

`lumen-inbox` öffnet die gemeinsame Server-Inbox. Kontoeinrichtung, Abruf, Entwürfe, Versand und Kalenderoperationen erfolgen auf dem verbundenen Server und unter dessen Berechtigungen. Die frühere lokale IMAP-/SMTP-/CalDAV-Bibliothek ist kein aktueller Client oder Offline-Cache.

Wichtig für lokale Dienste wie Proton Mail Bridge: `127.0.0.1` auf dem Server bezeichnet den Server, nicht deinen Desktop. Alte Anleitungen zur Bridge im Desktopfenster sind deshalb kein gültiger Netzwerkaufbau für die Server-App. Nutze nur die vom Server unterstützte und überprüfte Anbieteranbindung; Zugangsdaten nicht in Chat oder Dokumentation kopieren. [Server-Inbox](https://forge.example.invalid/ativaro/lumen-server/src/branch/main/docs/inbox.md).

Alte lokale Konten, Cache-Dateien und Entwürfe werden bei der Codebereinigung nicht gelöscht. Sie werden aber nicht automatisch zu Serverkonten oder hochgeladen. Ein Versand braucht die aktuelle Freigabe in der Serveroberfläche. Frühere lokale Übergaben zu Inbox-Aufgaben/-Entwürfen sind kein nachgewiesener vollständiger Serverweg.

[Installation](INSTALL.md) · [App-Zuständigkeiten](docs/desktop-retirement.md) · [Übergaben](docs/interop/USAGE.md)
