# Lumen Vault und Inbox auf dem Desktop

Tresor und E-Mail sind getrennte Funktionen. Der Desktop-Starter für Vault und Inbox öffnet die jeweilige **Lumen-Server-App**. Lokale Sicherungspläne, der lokale KeePass-Tresor, seine native Testversion und der lokale Zugangsdaten-Broker sind aus Lumen Desktop entfernt; vorhandene Plandaten, Sicherungsziele und `~/.local/share/lumen-vault-lab` bleiben unverändert erhalten.

## Lumen Vault öffnen

`lumen-vault` oder **Lumen Vault** im App-Menü öffnet den gemeinsamen Servertresor. Voraussetzung sind Serververbindung, Konto und die Gerätefreigabe `vault_sync`. Die Sitzung bleibt an dieses Konto, Gerät und die App gebunden. Ohne Verbindung gibt es keinen automatischen lokalen Ersatz.

Anmeldung am Server und Entsperren des Tresors sind verschiedene Schritte. Die Freigabe eines Eintrags für Lumen macht sein Secret nicht zum freien Modellkontext: Eintragskatalog und konkrete Nutzung haben getrennte Regeln. Die sichtbare Bestätigung der jeweiligen Aktion bleibt maßgeblich. [Server-Tresor und Grenzen](https://forge.example.invalid/ativaro/lumen-server/src/branch/main/docs/vault-web.md) (privater Zugang erforderlich).

## Lumen Inbox und Kalender

`lumen-inbox` öffnet die gemeinsame Server-Inbox. Kontoeinrichtung, Abruf, Entwürfe, Versand und Kalenderoperationen erfolgen auf dem verbundenen Server und unter dessen Berechtigungen. Die frühere lokale IMAP-/SMTP-/CalDAV-Bibliothek ist kein aktueller Client oder Offline-Cache.

Wichtig für lokale Dienste wie Proton Mail Bridge: `127.0.0.1` auf dem Server bezeichnet den Server, nicht deinen Desktop. Alte Anleitungen zur Bridge im Desktopfenster sind deshalb kein gültiger Netzwerkaufbau für die Server-App. Nutze nur die vom Server unterstützte und überprüfte Anbieteranbindung; Zugangsdaten nicht in Chat oder Dokumentation kopieren. [Server-Inbox](https://forge.example.invalid/ativaro/lumen-server/src/branch/main/docs/inbox.md).

Alte lokale Konten, Cache-Dateien und Entwürfe werden bei der Codebereinigung nicht gelöscht. Sie werden aber nicht automatisch zu Serverkonten oder hochgeladen. Ein Versand braucht die aktuelle Freigabe in der Serveroberfläche. Frühere lokale Übergaben zu Inbox-Aufgaben/-Entwürfen sind kein nachgewiesener vollständiger Serverweg.

[Installation](INSTALL.md) · [App-Zuständigkeiten](docs/desktop-retirement.md) · [Übergaben](docs/interop/USAGE.md)
