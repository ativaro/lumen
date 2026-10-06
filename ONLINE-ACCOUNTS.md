# Lumen Online-Konten

## Umfang

Ein gemeinsamer Bereich in Lumen verwaltet zunächst Cloud-Dateien: Google Drive,
OneDrive (Personal/Business), Dropbox und WebDAV über HTTPS. Mehrere Konten desselben
Anbieters sind möglich. Ein Konto erscheint nach erfolgreicher Einrichtung in Files;
Öffnen, Status und lokales Entfernen sind im Kontobereich verfügbar.

## Zuständigkeiten und Reihenfolge

| Bereich | Aufgabe | Prüfung |
| --- | --- | --- |
| Konten | Stabile Konto-ID, Name, Anbieter, getrennte lokale Konfiguration | Mehrere Konten und Pfadgrenzen |
| Anmeldung | Vorhandenen rclone-Ablauf wiederverwenden, Browser oder WebDAV | Abbruch, falsche Anmeldung, OneDrive-Auswahl |
| Dateien | Gemeinsame Sitzungs-Mounts und Navigation in Files | Kein Schreiben in getrennte Mountpunkte |
| Oberfläche | Online-Konten in Einstellungen und Files | Tastatur, Status, deutsche/englische Texte |

Die bestehende Google-Verbindung wird ohne Migration weiterhin erkannt. Google
benötigt weiter einen freigegebenen Desktop-Client; die Kontenoberfläche erteilt
keine Google-Freigabe. OneDrive und Dropbox verwenden die rclone-App-Anmeldung.
WebDAV prüft eine HTTPS-Ordneradresse durch Auflisten vor dem Speichern.

## Grenzen

- Kein persönliches Herausgeberkonto wird automatisch verbunden, kein Cloud-Billing
  eingerichtet und keine neue OAuth-App bei einem Anbieter erzeugt.
- Kontenfreigabe ist kein automatischer Auftrag an die KI, Cloud-Dateien zu lesen.
- Kontozugangsdaten bleiben lokal in privaten Verzeichnissen (0700), Dateien (0600).
  rclone-WebDAV-Passwörter sind verschleiert, nicht zusätzlich verschlüsselt.
- Entfernen löscht nur die lokale Verbindung. Für einen Widerruf beim Anbieter
  dessen Kontoverwaltung verwenden. Eingebundene Konten werden zum Schutz laufender
  Übertragungen nicht entfernt; zuerst von der Desktop-Sitzung abmelden.
- Keine vollständige Offline-Synchronisierung, Kalender, Kontakte oder E-Mail in
  diesem Schritt. Keine pauschalen Unmounts und keine GitHub Actions.

## Prüfung

Python/PySide6, vorhandene unittest-Tests und rclone. Source: `files/google_drive.py`,
`files/online_accounts.py`, `files/app.py`, `files/settings_dialog.py`.

```sh
QT_QPA_PLATFORM=offscreen LUMEN_LANGUAGE=de python -m unittest discover -s files -p 'test_online_accounts.py'
QT_QPA_PLATFORM=offscreen LUMEN_LANGUAGE=de python -m unittest discover -s files -p 'test_google_drive.py'
bash packaging/arch/build-package.sh
```

Provider-Verträge: [OneDrive](https://rclone.org/onedrive/),
[Dropbox](https://rclone.org/dropbox/), [WebDAV](https://rclone.org/webdav/),
[nichtinteraktive Konfiguration](https://rclone.org/commands/rclone_config_update/).
Tests mit Ersatzprozessen und abgebrochenem echtem OAuth prüfen den Ablauf, nicht
die Freigabe oder Dateizugriffe eines echten Cloud-Kontos.

### Verifiziert am 6. Oktober 2026

- 40 gezielte Tests bestanden: Online-Konten (6), Google Drive (5), Einstellungen
  und Navigation (23), Übersetzungen (6). Native Qt-Dialoge visuell geprüft.
- Die 11 Konten-/Drive-Tests zusätzlich gegen das installierte Lumen ausgeführt.
  Bestehende installierte PDF- und Lumen-Server-Anpassungen wurden beim selektiven
  Update bewahrt; ursprüngliche Dateien und SHA-256-Werte liegen im Patch-Backup.
- Zwei KI-Setup-Tests und der vorhandene KIO-WebDAV-Livetest scheitern in dieser
  Sitzung. Derselbe Fehler tritt im unveränderten Ausgangsstand `bb11215` auf
  (gespeicherte Modellwahl beziehungsweise Netzwerk-Zeitüberschreitung).
- Echte rclone-Anmeldungen für Google, OneDrive und Dropbox bis zum Browser-Callback
  mit absichtlichem Abbruch geprüft. Kein persönliches Cloud-Konto verbunden.
  Erfolgreiche Cloud-Anmeldung, echte Cloud-Dateizugriffe und Uploads bleiben ein
  Nutzertest mit dem jeweiligen Konto; Googles App-Freigabe steht noch aus.
