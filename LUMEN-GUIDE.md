# Lumen benutzen

Lumen ist die KI-Erweiterung für CachyOS mit gemeinsamen Einstellungen und
Integrationen. **Lumen** im Panel oder `lumen` öffnet den Assistenten.
**Lumen Files** beziehungsweise `lumen-files` öffnet den eigenständigen
Dateimanager, auch direkt mit einem lokalen Ordner oder einer Netzwerkadresse.
Der Assistent behält zusätzlich den Dateibereich unter `lumen --page files`.
Beide verwenden dieselben Datei-Einstellungen, Modelle und KI-Funktionen;
`Strg+,` öffnet den gemeinsamen Einstellungsdialog. OpenCode bleibt die Engine;
bestehende Anmeldungen und Anbieter werden weiterverwendet.

Nach einem Absturz bietet der Wiederherstellungsdialog **Mit Lumen prüfen** an.
Die Schaltfläche öffnet **Fehlerbericht prüfen** in einem eigenen Lumen-Fenster
und startet die Analyse mit dem eingerichteten Modell. Als Kontext werden nur
Absturzdaten und Fehlerprotokoll ausgewählt, keine gespeicherten Sitzungen oder
Entwürfe. Der Auftrag läuft im Planungsmodus: Ursache erklären, Vermutungen
kennzeichnen und nächste Schritte vorschlagen. Der Bericht bleibt zur späteren
Wiederherstellung erhalten. **Fehlerbericht** öffnet weiterhin den lokalen Ordner.

## Aufträge und echte Ergebnisse

### Lumen-Menü in der Plasma-Leiste

Das Widget **Lumen** öffnet ein kompaktes Menü mit gemeinsamen Aufträgen aus
Lumen und Lumen Files. „Aktuell“ zeigt bis zu acht offene Aufträge, „Zuletzt“ die
fünf letzten abgeschlossenen Vorgänge. Klick auf einen Eintrag klappt Ergebnis
oder Fehler direkt auf; **Auftrag öffnen** zeigt die vollständigen Details.
Native Schritte zeigen ihren tatsächlichen Fortschritt, KI-Aufträge einen
laufenden Status. Rückfragen werden als **Braucht dich** gekennzeichnet.

**Dateien**, **System**, **Alle Aufträge**, **Lumen** und **Einstellungen** bieten
direkte Einstiege. Vorhandene aktuelle Hauptfenster werden wiederverwendet und
Entwürfe bleiben erhalten; bei einem noch laufenden älteren Lumen öffnet ein
Auftragslink ein separates Fenster. Das Menü führt Aufträge nicht automatisch aus.
Die Liste liest ausschließlich die bestehende lokale Auftragsdatenbank; geöffnete
Menüs aktualisieren alle zwei Sekunden, geschlossene alle 15 Sekunden.

Hinzufügen über Plasma → Bearbeitungsmodus → Miniprogramme → **Lumen**. Der
Paketinstaller liefert das Applet systemweit, `install.sh` für den aktuellen
Benutzer. Ein altes persönliches Applet kann die Paketversion überlagern; vor
dem Entfernen einer solchen Kopie eigene Anpassungen sichern. Die bestehende
Lebensdauer der Aufträge bleibt unverändert: ein KI-Auftrag gehört weiterhin
zu seinem Lumen-/Files-Fenster.

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

Für SMB den Server öffnen und die gewünschte Freigabe als Ordner auswählen.
Es genügt `smb://nas/`; gespeicherte Verbindungen öffnen ohne zusätzliches
Adressformular. Geschützte Freigaben fragen bei Bedarf direkt nach Benutzername
und Passwort. Erst wenn die Ordnerliste gelesen werden kann, meldet Lumen eine
erfolgreiche Verbindung.

Unter **Dateien → Quellen …** lassen sich lokale und Netzwerkordner zu einer
Bibliothek verbinden. Die Herkunft steht bei jeder Datei. Die Sammelfläche hält
Verweise, **Arbeitsräume** halten Tabs, Auswahl, eigene Sammlung, Gespräch und
Entwurf zusammen. Raumwechsel senden nichts an die Engine. Details und Grenzen
stehen im [Files-Handbuch](files/README.md#bibliotheken-sammelfläche-und-arbeitsräume).

Unter **Einstellungen → Darstellung** stehen **Klar & hell**, **Warmes Studio**,
**Graphit** und der KDE-Systemstil für beide Apps bereit. Die Auswahl aktualisiert
offene Fenster und lässt das Desktop-Theme unverändert.

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

## Lumen-Leiste: Inseln und Zentrale

Die Erweiterung **Lumen Leiste** (`org.lumen.islands`) bietet drei Rollen:
**Lumen und Dateien** links, **Suche** in der Mitte und **Lumen Zentrale** rechts.
Die Rolle lässt sich über die Widget-Einstellungen ändern. Das bisherige
Lumen-Aufgabenwidget bleibt verfügbar.

Die Suche öffnet die native gemeinsame Datei-/App-Suche mit Gespräch. Das Mikrofon
rechts in der oberen Suchleiste startet dort das Sprachgespräch (auch über
`lumen-search --voice`). Sprechpausen senden den erkannten Text, Antworten werden
lokal vorgelesen. „Beenden“ oder Schließen der Suche schaltet das Mikrofon aus.
Ein animierter Blob zeigt den Gesprächszustand und reagiert auf den Audiopegel.
In der breiten Suche ergänzt eine Pegelwelle die Anzeige; im schmalen Files-Panel
bleibt sie kompakt. „Ich höre zu“, Spracherkennung, Nachdenken, Stimmvorbereitung
und „Lumen spricht“ sind getrennte Zustände. Die Wiedergabewelle folgt der lokalen
Audiodatei zeitlich ungefähr; sie misst nicht die Lautsprecherlautstärke.
Fehlende Sprachkomponenten lassen sich direkt im Einrichtungsassistenten ergänzen.
Unter **Einstellungen → Einrichtung → Mit deiner Stimme** lässt sich statt des
kleinen Modells **Whisper Large v3 Turbo Q8** installieren (874 MB). Das alte Modell
bleibt erhalten und kann über „Vorhandenes Sprachmodell auswählen“ wieder gewählt werden.
Deutsch ist die Vorgabe für die Erkennung; Englisch und weitere Sprachen sowie
automatische Spracherkennung sind auswählbar. Eine kurze Liste eigener Namen und
Fachbegriffe hilft bei Schreibweisen, ersetzt aber keine Prüfung des erkannten Texts.
Sprache, Begriffsliste und GPU-Nutzung gelten gemeinsam für Diktat, Mikrofontest
und Sprachgespräch; auch unter „Sprachgespräch einstellen“ erreichbar. Vorhandene
Vulkan-Bauwerkzeuge werden bei einer neuen lokalen Whisper-Installation genutzt,
andernfalls wird eine CPU-Version erstellt. CPU-Betrieb ist jederzeit auswählbar.
KRunner bleibt über sein eigenes Tastenkürzel erreichbar; `lumen <Frage>` nutzt
dort den bestehenden Lumen-Runner.
Die Zentrale zeigt gemeinsame Aufgaben und native Systemsteuerungen. Lautstärke
und Stummschaltung betreffen das Standard-Ausgabegerät; Helligkeit verwendet KDEs
globale Bildschirmsteuerung. **Audiogeräte** und **Bildschirme** öffnen die
detaillierten KDE-Einstellungen. Fehlende Dienste ergeben deaktivierte Regler.
**Nicht stören** lässt sich für eine Stunde einschalten und jederzeit ausschalten.
Bestehende externe Zeitvorgaben werden beim bloßen Öffnen nicht verändert.

Die obere Anordnung wird über normale Plasma-Leisten hergestellt. Vorhandene
Systemablage, Uhr und Super-Anwendungsstarter werden übernommen; das Dock bleibt
bestehen. Die Paketinstallation ändert das persönliche Panel-Layout nicht von selbst.

Der optionale Plasma-Stil **Lumen Inseln** verwendet sichtbare runde Flächen und
ruhige dunkle Menüs. Bei vorhandenem LumenDark erzeugt
`python plasmoid/install-island-style.py` die Ableitung im Benutzerprofil;
`plasma-apply-desktoptheme LumenIslands` aktiviert sie. LumenDark bleibt erhalten,
die Zeichnungen des unteren Docks und die globalen Schriften werden nicht ersetzt.
