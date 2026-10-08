# Google-Anmeldung für Lumen

Lumen verwendet einen eigenen Google OAuth-Client vom Typ **Desktop-App** und den
vorhandenen rclone-Browser-Login mit Loopback-Rückleitung. Es gibt keinen Lumen-
Anmeldeserver: Kontotokens und der Dateicache bleiben auf dem jeweiligen Rechner;
rclone kommuniziert direkt mit Google. Eine mitgelieferte App-Identität ersetzt
keine Google-Freigabe. Der Code markiert eine App nicht selbst als „verifiziert“.

## Einmalige Einrichtung durch den Herausgeber

1. Im Google-Cloud-Konto ein Projekt **Lumen** erstellen und die **Google Drive API**
   aktivieren. Keine VM, kein Dienstkonto und keinen API-Key anlegen.
2. In **Google Auth Platform** App-Name **Lumen**, Support- und Kontaktadresse
   hinterlegen. Zielgruppe **External**; zunächst **Testing**, explizite Testnutzer.
3. Unter **Data Access** ausschließlich `https://www.googleapis.com/auth/drive`
   anmelden. Lumen benötigt bestehende Ordner und Dateien sowie Kopieren,
   Umbenennen, Schreiben und Löschen. `drive.file` würde nur von der App angelegte
   bzw. explizit freigegebene Dateien abdecken, nicht das komplette Laufwerk.
4. Unter **Clients** einen OAuth-Client **Desktop app**, Name **Lumen Desktop**,
   erstellen und die JSON-Datei lokal speichern. Keine fremde App-ID übernehmen.
5. Für den öffentlichen Einsatz: eigene verifizierte Domain, öffentlich erreichbare
   Homepage, Datenschutzerklärung und Kontaktinformationen hinterlegen, tatsächliche
   Datenverwendung dokumentieren, den Ablauf per Demo zeigen und Googles Prüfung für
   den eingeschränkten Drive-Bereich durchlaufen. Erst nach erfüllten Voraussetzungen
   öffentlich freigeben. Testing ist kein allgemeiner Release: Nur Testnutzer dürfen
   sich anmelden, und ihre Berechtigung kann nach sieben Tagen ablaufen.

Quellen: [Desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app),
[Drive-Berechtigungen und Prüfung](https://developers.google.com/workspace/drive/api/guides/api-specific-auth),
[Consent-Konfiguration](https://developers.google.com/workspace/guides/configure-oauth-consent).
Google entscheidet über Freigabe und eventuelle weitere Anforderungen. Eine
Security-Prüfung ist laut Drive-Dokumentation insbesondere relevant, wenn Daten
mit eingeschränkten Berechtigungen über eigene Server übertragen oder dort gespeichert
werden; der hier implementierte Dateizugriff nutzt keinen solchen Server.

## Paket bauen oder lokal installieren

Für Bash **und Fish** (nur den tatsächlichen absoluten JSON-Pfad einsetzen):

```sh
env LUMEN_GOOGLE_OAUTH_CLIENT_FILE=/absoluter/pfad/lumen-desktop.json bash packaging/arch/build-package.sh
env LUMEN_GOOGLE_OAUTH_CLIENT_FILE=/absoluter/pfad/lumen-desktop.json bash install.sh
```

Der Build normalisiert die JSON auf `installed.client_id` und
`installed.client_secret`, und legt sie im Paket unter
`/usr/share/lumen/files/google-drive-client.json` ab. Web-/Dienstkonten werden
abgelehnt. Auth-Endpunkte, Kontotokens und zusätzliche JSON-Felder werden nicht
übernommen. Eine explizit angegebene ungültige oder fehlende Datei bricht den Build ab.
Ohne Konfiguration bleibt die zentrale Anmeldung aus, die eigene App bleibt nutzbar.

Alternativ kann die normalisierte Datei lokal in `files/google-drive-client.json`
liegen; dieser Pfad und Google-Downloadnamen `client_secret_*.json` sind von Git
ausgeschlossen. Der Build nimmt die Datei explizit mit, obwohl `git archive` sie
nicht enthält. Direkte makepkg-Builds benötigen eine bereits entsprechend bestückte
Quell-Tar-Datei. Quell-Installationen ohne mitgelieferte Konfiguration bewahren eine
bereits installierte App-Identität.

Ein verteilter Desktop-Client kann seine App-Identität nicht geheim halten. Die
JSON ist im Paket lesbar und enthält deshalb ausschließlich diese Identität;
persönliche Refresh-Tokens gehören niemals hinein. Sie verbleiben getrennt in
`~/.config/lumen/google-drive/rclone.conf` mit Modus `0600`. Bestehende Anmeldungen
werden bei einem Paketwechsel nicht umgeschrieben.

## Freigabe prüfen

- Dialog ohne Konfiguration: zentrale Anmeldung gesperrt, erweiterte Option nutzbar.
- Paket mit eigener App: keine Eingabe von Client-ID/Secret nötig, Klick öffnet Google.
- Angemeldetes Testkonto: Ordner anzeigen, Testdatei kopieren/umbenennen und in Drive
  prüfen; nur die selbst angelegte Testdatei anschließend wieder entfernen.
- Browser-Abbruch: kein Konto und keine temporären Token-Dateien zurücklassen.
- Bereits verbundenes Konto: Update verändert dessen Konfiguration nicht.

Automatisiert: `QT_QPA_PLATFORM=offscreen python -m unittest discover -s files -p test_google_drive.py`.
Der echte rclone-Abbruchtest läuft zusätzlich, wenn rclone im PATH liegt. Synthetische
Anmeldetests bestätigen den Datenfluss, nicht Googles Freigabe für reale Nutzer.
