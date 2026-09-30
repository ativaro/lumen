# Lumen benutzen

Lumen ist eine Anwendung. `lumen` startet das Fenster, `lumen --page files`
öffnet den integrierten Dateibereich. Der bisherige Befehl `lumen-files` bleibt
kompatibel, auch für lokale Ordner und Netzwerkadressen. OpenCode bleibt die
Engine; bestehende Anmeldungen und Anbieter werden weiterverwendet.

## Aufträge und echte Ergebnisse

Gespräche erzeugen automatisch gespeicherte Aufträge. Unter **Aufträge** stehen
Status, Ergebnis, Fehler und Verlauf. Pausieren stoppt die Engine; Fortsetzen
verwendet das gespeicherte Gespräch mit dem Auftrag, den bereits erreichten
Zustand zuerst zu prüfen. Nach einem Absturz werden verwaiste Ausführungen als
unterbrochen angezeigt. Es gibt keine automatische Wiederholung eines
möglicherweise bereits ausgeführten Schritts.

**Neuer Auftrag** bereitet native Schritte vor: Anwendungen/Dateien/Webseiten
öffnen, Fenster anordnen, Textdateien schreiben, Dateien kopieren,
Systemdiagnose, Dienstneustart mit Zustandsprüfung, Paketinstallation mit
Paketprüfung oder Snapper-Snapshot. Ordner und Schritte müssen freigegeben
werden. Ein KI-Vorschlag über `lumen_propose_task` ist immer ein ungeprüfter
Entwurf. Systemänderungen verwenden die normale Systemauthentifizierung.

Native Dateiänderungen bis 16 MiB speichern den vorherigen Inhalt. **Änderung
rückgängig** verweigert das Überschreiben späterer Inhalts- oder Rechteänderungen.
Engine-Werkzeuge haben eigene Freigaben und keine pauschale native Undo-Garantie.
**Ergebnis speichern** erzeugt eine echte Markdown-/Textdatei, die im Dateibereich
geöffnet und angesehen werden kann. Desktopstarts bestätigen die Anforderung;
Datei-, Paket- und Dienstaktionen prüfen das Ergebnis explizit.

Ein laufender nativer Schritt darf fertig werden; Pause/Abbruch wirkt vor dem
nächsten Schritt. Währenddessen wird der Auftragsprozess beim Schließen nicht
abgeschossen. Snapper verwendet die Root-Konfiguration: persönliche Ordner sind
nicht automatisch enthalten, und ein Snapshot ist kein unabhängiges Backup.

## Wissen und Erinnerungen

Unter **Wissen** ausgewählte Ordner lokal indexieren und durchsuchen. Treffer
zeigen Datei, Seite und Auszug. Die Suche überspringt versteckte Pfade, Symlinks
und übliche Geheimnisdateinamen. Sie erkennt nicht jeden beliebigen vertraulichen
Inhalt; nur bewusst ausgewählte Ordner freigeben. Grenzen: 10.000 Einträge,
32 MiB extrahierter Text pro Lauf, die Größenlimits des vorhandenen Textlesers
und 16 MiB für native Änderungen. Geänderte Dateien werden bis zur erneuten
Indexierung nicht als aktuelle Treffer ausgegeben.

Freigabe entfernen löscht den Index dieses Ordners. Erinnerungen sind von dir
angelegte, bearbeitbare Einträge mit Quelle. **Verwenden** legt Kontext sichtbar
in den Gesprächsentwurf. `lumen_knowledge` kann freigegebene Wissensordner für
Anfragen durchsuchen; Auszüge gehen dabei an das gewählte Modell. Es gibt kein
heimliches Indexieren des gesamten persönlichen Ordners.

## Abläufe

Einen Auftrag **als Ablauf speichern** oder Schritte neu zusammenstellen.
Auslöser: manuell, Zeitintervall oder Änderungen an direkten Einträgen eines
freigegebenen Ordners. Die Beobachtung ist nicht rekursiv. Änderungen werden bei
der nächsten Prüfung zusammengefasst; verpasste Intervalle werden nicht mehrfach
nachgeholt. **Hintergrundprüfung aktivieren** schaltet `lumen-jobs.timer` ein.
Eine Pause des Ablaufs verhindert neue Aufträge; bereits angelegte Aufträge
werden separat pausiert/abgebrochen.

Datei- und Diagnoseabläufe können mit der gespeicherten Freigabe im Hintergrund
laufen. KI-Aufträge sowie Desktop- und Systemaktionen werden als **Braucht dich**
bereitgelegt und im Vordergrund gestartet. So bleiben Werkzeugrückfragen und
Authentifizierung sichtbar. Neue/angepasste Schritte benötigen erneut Freigabe.

## Modelle, Ressourcen und Kontext

**Modelle** legt Standardmodell, Modell für wiederkehrende KI-Aufträge,
Zeitlimit und Hintergrundpause fest. NVIDIA-SMI kann Hintergrundarbeit bei hoher
GPU-Auslastung zurückstellen. Ohne NVIDIA-SMI gibt es keine GPU-Auslastungsprüfung.

**Nur lokaler Dienst** fordert einen konfigurierten Anbieter mit einer wörtlichen
Loopback-Adresse wie `http://127.0.0.1:11434/v1`. Lumen bindet Haupt-/Hilfsmodelle
und die Anbieterauswahl der privaten Engine daran, deaktiviert Projektkonfiguration
in diesem Modus und prüft die effektive Konfiguration vor dem Absenden. Es gibt
keinen automatischen Cloud-Fallback. Ein lokaler Proxy kann selbst weiterleiten;
sein Betrieb und dessen Netzwerkregeln bleiben außerhalb dieser Garantie.
Die Richtlinie gilt auch für native Vorschläge und die Lumen-Berichtshelfer.
Lumen verändert keine systemweiten Netzwerksperren.

Dateien/Bilder, ein explizit ausgewählter Bildschirmbereich und eingefügter Text
sind vor dem Senden sichtbar. **Diktieren** benötigt `whisper-cli` (whisper.cpp),
`pw-record` und ein selbst ausgewähltes lokales Modell. Aufnahme maximal 60 Sekunden,
Transkription maximal 120 Sekunden. Audio wird lokal temporär verarbeitet und danach
entfernt; der Text bleibt ein Entwurf. Lumen lädt kein Modell automatisch herunter.
**Schritte erklären** ergänzt eine verständliche Anleitung zur ausgeführten Arbeit.

## Netzwerkverbindungen sauber beenden

Lumen beendet Such-/Vorschauzugriffe und löst Dateimodell-Watcher beim Schließen.
Nach dem Schließen des letzten Netzwerk-Tabs werden unbenutzte lokale
Verbindungszuordnungen freigegeben. Gespeicherte Server und Tab-Adressen bleiben
für eine spätere Wiederverbindung erhalten.

Die installierte KIO-FUSE-Schnittstelle hat `mountUrl`/`remoteUrl`, aber keine
Abmeldung einzelner URLs. Lumen beendet deshalb keinen gemeinsam verwendeten
KIO-FUSE-Dienst. Ein separater, zeitlich begrenzter Aufräumer berücksichtigt nur
Mounts, deren Pfade dieses Fenster tatsächlich verwendet hat, mit passendem
Benutzer und `fuse.kio-fuse`-Typ. Nur ein bestätigtes `ENOTCONN` und unveränderte
Mount-ID erlauben ein gezieltes, normales Unmount. Kein Lazy-/Force-Unmount,
keine pauschale Suche mit Unmount aller Treffer. Erreichbare Mounts und Dolphin
bleiben unberührt. Fremde Dolphin-Tabs werden nicht von Lumen geschlossen.

## Update von opencode-lumen

Im Quellverzeichnis `./packaging/arch/build-package.sh --install` verwenden.
Der Wrapper sichert `/var/lib/opencode-lumen` und die bestehenden
Dienstzustände **vor** dem Ersetzen des alten Pakets: dessen alter Uninstaller
löscht sonst die alten Berichte. Danach werden die Zustände wiederhergestellt.
Das neue Paket heißt `lumen`; der Installer entfernt das alte Paket ohne dessen
destruktive Uninstall-Skripte. Der alte Share-Pfad bleibt als Kompatibilitätslink.
Es gibt bewusst kein automatisches `replaces/conflicts`: eine direkte Installation
neben dem alten Paket stoppt an Dateikonflikten, statt Berichte zu löschen. Neue Timer bleiben ausgeschaltet.

Bei manueller Paketinstallation zuerst `sudo /usr/bin/python3 files/lumen_upgrade.py before`,
dann `sudo pacman -Rdd --noscriptlet opencode-lumen`, `sudo pacman -U …`, danach `sudo /usr/bin/python3 files/lumen_upgrade.py after`.
Anschließend als normaler Benutzer `lumen-setup` ausführen. Vorhandene Qt-Einstellungen
bleiben bestehen. Alte Benutzerberichte werden nur in fehlende Ziele kopiert;
Originale und neuere Dateien bleiben erhalten. Die neue Datenbank liegt unter
`$XDG_STATE_HOME/lumen` (normalerweise `~/.local/state/lumen`) mit privaten Rechten.

## Entwicklung und Prüfung

```sh
QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s files -v
./packaging/arch/build-package.sh
```

Der echte WebDAV-Test benötigt den Sitzungsbus und KIO-FUSE/KIO-WebDAV.
Aus einer Umgebung ohne Desktop-Bus beispielsweise
`DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus` setzen.
KWin-Fensteranordnung benötigt Plasma und `qdbus6`; ohne diese Voraussetzungen
meldet der Auftrag einen konkreten Fehler.

Grundlagen: [OpenCode-Konfiguration](https://opencode.ai/docs/config/),
[KWin-Scripting](https://develop.kde.org/docs/plasma/kwin/api/),
[KIO-FUSE](https://github.com/KDE/kio-fuse),
[CachyOS-Snapshots](https://wiki.cachyos.org/configuration/btrfs_snapshots/).
