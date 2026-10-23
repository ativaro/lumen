# Lumen Desktop

**Wir bauen ein System, das für dich arbeitet.**

Wir bauen Lumen, weil wir uns einen Computer wünschen, mit dem sich die eigene Arbeit leichter anfühlt. Einen, dem du erzählen kannst, was du vorhast. Mit dem du einer Idee nachgehst, dich durch ein Problem arbeitest und am Ende etwas geschafft hast.

Lumen beginnt mit einem Gespräch. Du kannst laut denken, Fragen stellen, widersprechen und deine Richtung ändern. Dabei kann Lumen mit dem arbeiten, was deine Aufgabe ausmacht: deinen Dateien, deinen Daten, deinen Programmen und deinem Rechner. Es kann Zusammenhänge untersuchen, Dinge verständlich machen und selbst Arbeitsschritte ausführen. Du beschreibst auf deine Art, was du erreichen möchtest. Lumen fragt nach, wenn etwas fehlt, und arbeitet mit dir weiter.

Dafür haben wir Lumen direkt in den Desktop gebracht. Im eigenen Dateimanager liegen deine Inhalte und das Gespräch darüber nebeneinander. Aus einer Benachrichtigung kann der nächste Schritt entstehen. Wenn etwas auf deinem Rechner hakt, kann Lumen mit dir nach der Ursache suchen und bei der Behebung helfen. Wenn für deine Arbeit ein Programm fehlt, kann es die Installation übernehmen. Was zusammengehört, bleibt so auch beim Arbeiten zusammen.

Du gibst die Richtung vor und bestimmst, welche Zugriffe und Änderungen du erlaubst. Lumen soll dir den Rücken freihalten und dir helfen, mehr von dem umzusetzen, was dir wichtig ist.

**Das ist Lumen Desktop. Auf deinem Rechner, mit deinen Inhalten, für deine Vorhaben.**

Und wenn du Lumen noch stärker in deinen Alltag einbinden möchtest, verbinde deinen Desktop mit Lumen Server. Deine Notizen, Projekte und Aufgaben kommen zusammen, und Lumen kann wiederkehrende Arbeit für dich übernehmen – auch während du nicht am Rechner sitzt. Mit Lumen Mobile hast du Lumen unterwegs dabei: Gedanken festhalten, auf deine Inhalte zugreifen und später am Computer weiterarbeiten. So wird aus der Hilfe am Desktop ein Begleiter für deinen Alltag.

**Installiere Lumen und bring deine erste Aufgabe mit.**

## Installation

**Aktueller Zugang:** Der Quellstand wird privat auf [Forgejo](https://forge.example.invalid/ativaro/lumen) verteilt. Ein öffentlicher Desktop-Download ist noch nicht freigegeben. Es gelten die [Lumen-EULA](LICENSE) und die [Lizenzen der enthaltenen Komponenten](THIRD_PARTY_NOTICES.md).

### Voraussetzungen

Für den vollständigen Desktop: **Arch Linux oder CachyOS mit KDE Plasma 6**, angemeldet als normaler Benutzer in einer grafischen Sitzung. Der Installer installiert keine Linux-Distribution und keinen Plasma-Desktop. Du brauchst Internet für fehlende Pakete und die Einrichtung; Paketinstallationen können dein Linux-Passwort verlangen.

Für den derzeitigen Download brauchst du Zugriff auf das private Repository [ativaro/lumen auf Forgejo](https://forge.example.invalid/ativaro/lumen) und eine Netzwerkverbindung zu diesem Forgejo-Server. Eine Anmeldung im Browser meldet Git im Terminal nicht automatisch an. Verwende deinen eingerichteten Git-Zugang oder die Anmeldeabfrage von Git; schreibe keine Zugangsdaten in Befehle oder Repository-URLs.

### Installieren und einrichten

Öffne ein Terminal in deiner Plasma-Sitzung. Installiere Git, falls es fehlt:

```bash
sudo pacman -S --needed git
```

Wechsle in einen Ordner, in dem noch kein Unterordner `lumen` existiert, und starte **ohne sudo**:

```bash
git clone --branch main --single-branch https://forge.example.invalid/ativaro/lumen.git
bash lumen/bootstrap.sh
```

Der Installer richtet die Programme für deinen Benutzer ein und öffnet **Lumen einrichten**. Dort kannst du:

1. Deinen KI-Anbieter und ein Modell auswählen. Ein vorhandener Zugang kann weiterverwendet werden; Anbieter können eigene Kosten und Limits haben.
2. Optionale Spracherkennung und Stimmen vorbereiten.
3. Ein Erscheinungsbild auswählen und bei Bedarf **Lumen-Desktop aktivieren**. Vor Änderungen an Panels, Hintergrund und Fensterdekoration wird die betroffene Konfiguration gesichert. Du kannst deine vorhandene Desktop-Gestaltung behalten.
4. Optional einen bereits verfügbaren Lumen Server verbinden. Das ist für den lokalen Einstieg nicht erforderlich.

Starte anschließend **Lumen** aus dem Anwendungsmenü oder mit `lumen`. Die Einrichtung erreichst du später unter **Einstellungen → Einrichtung** oder über `lumen-setup-wizard`.

Die KI-Einrichtung nutzt die für Lumen passende Engine. Die gewählte Modellverbindung bestimmt, ob Anfragen lokal verarbeitet oder an einen externen Anbieter gesendet werden. Ein als kostenlos angebotenes Modell ist keine Garantie für dauerhafte Verfügbarkeit oder unbegrenzte Nutzung.

Andere Installationsarten, Paketbau, Voraussetzungen und Rückweg: [Installationsanleitung](INSTALL.md).

### Aktualisieren

Wenn Lumen bereits installiert ist, öffne **Lumen Updater** oder starte:

```bash
lumen-updater
```

Fehlt der Updater, kannst du ihn aus dem privaten Repository vorübergehend laden. Git-Zugang und die vorhandene Lumen-Laufzeit werden benötigt. Als normaler Benutzer in der Desktop-Sitzung:

```bash
(d="$(mktemp -d)" && trap 'rm -rf -- "$d"' EXIT && git clone --depth 1 --branch main --single-branch https://forge.example.invalid/ativaro/lumen.git "$d/lumen" && bash "$d/lumen/bin/lumen-updater")
```

Prüfe die Auswahl und wähle **Alles aktualisieren**. Persönliche Inhalte, Einstellungen und vorhandene gültige Modelle bleiben erhalten. Systempakete und Flatpaks sind zusätzliche, ausdrückliche Auswahlen. Öffne Apps anschließend neu; Änderungen an Plasma-Panels werden spätestens nach einer neuen Anmeldung geladen.

Eine bereits gespeicherte andere Updatequelle wechselt dadurch nicht automatisch zu Forgejo. Zum bewussten Wechsel installiere aus dem oben genannten Forgejo-Checkout. Details: [Native Updates](INSTALL.md#native-updates).

## Was die einzelnen Apps können

### Lumen: Gespräche, die dich weiterbringen

**Lokal nutzbar; für Antworten ist eine Modellanbindung nötig.**

Beginne mit einer Frage oder einer Idee und bleibe im Gespräch: nachfragen, eine Erklärung vertiefen, eine Antwort überarbeiten oder zum nächsten Schritt wechseln. Vorhandene Gespräche lassen sich wieder öffnen und fortsetzen. Fortschritt, Rückfragen und Ergebnisse sind direkt im Gespräch sichtbar.

Dateien, Bilder, PDF-Seiten, markierter Text oder die Zwischenablage lassen sich bewusst als Kontext verwenden. So kannst du über deine eigenen Inhalte sprechen. Antworten können Quellen und nutzbare Ergebnisdateien enthalten. Die gemeinsame Suche findet außerdem Programme und Dateien; aus einer Frage wird ein Gespräch.

Gespräche können zu ausgeführten Aufgaben führen. Du kannst etwa „Installiere diese Anwendung“ sagen, Dateien bearbeiten lassen oder ein Computerproblem untersuchen. Direkte Aufträge werden im laufenden Gespräch bearbeitet; erforderliche Werkzeugfreigaben bleiben dort sichtbar. Für Systemänderungen kann zusätzlich der normale grafische Administrator-Dialog erscheinen. Lumen prüft bei unterstützten Datei-, Paket- und Dienstaktionen das tatsächliche Ergebnis.

Du kannst Vorgänge verfolgen, abbrechen und Ergebnisse später wieder öffnen. Im Analysemodus bleibt der Auftrag lesend. Werkzeugfreigaben bestimmen, welche Änderungen möglich sind; eine ausdrücklich gewählte automatische Freigabe hat weitergehende Wirkung als eine einzelne Bestätigung. Eine Modellantwort ist kein Beweis, dass eine Aktion ausgeführt wurde: Maßgeblich sind der sichtbare Auftragsstatus und das Ergebnis.

### Lumen Files

**Dein eigener Dateimanager auf dem Rechner.**

Dateien, Ordner und erreichbare Netzlaufwerke durchsuchen, als Tabs öffnen und mit Vorschauen ansehen. Bibliotheken und Sammelfläche helfen, häufig benötigte Inhalte wiederzufinden. Galerie, Dateieigenschaften und Speicheranalyse bieten weitere Ansichten derselben Dateien.

Umbenennen und Sortieren lassen sich vor dem Anwenden prüfen. Für unterstützte Vorgänge gibt es Rückgängig-Funktionen mit Konfliktprüfung. Versionen, vorbereitete Offline-Kopien von NAS-Ordnern, Textsuche und optionale OCR helfen bei umfangreichen Sammlungen. Die Dokumentenwerkstatt bearbeitet ausgewählte PDF-Seiten; Bild- und Inhaltssuche benötigen ihre jeweiligen Zusatzkomponenten.

**Lumen Files ist zugleich dein Zugang zum Inhalt deiner Dateien.** Wähle eine Datei oder mehrere Dateien aus und stelle deine eigene Frage. Lumen kann Dokumente und Daten erklären, Programmcode untersuchen, Konfigurationen verständlich machen und bei Fehlern oder Änderungen helfen. Der Gesprächskontext bleibt sichtbar, während du im Dateimanager weiter navigierst.

Das Kontextmenü bietet **Mit Lumen öffnen**, **Erklären**, **Fehler beheben** und **Git-Diff prüfen**. Dateiaktionen haben eine eigene Ergebnisansicht mit Fortschritt, Rückfragen und Freigaben. Du kannst mehr Details anfordern, einen Vorgang abbrechen und unterstützte Ergebnisse nochmals prüfen lassen.

Die Dateiauswahl beschränkt sich nicht auf eine feste Liste von Dokumenttypen. Wie Lumen den Inhalt erschließt, hängt vom Format, den verfügbaren Werkzeugen und dem Modell ab; verschlüsselte oder beschädigte Dateien und fehlende Lesewerkzeuge können die Analyse begrenzen. Normale Dateivorgänge funktionieren auch ohne KI-Modell.

[Bedienung, Formate und Grenzen von Lumen Files](files/README.md).

### Lumen Notification

**Meldungen sammeln, wiederfinden und im Gespräch aufgreifen.**

Die Glocke bündelt KDE- und Lumen-Meldungen. Du kannst Meldungen öffnen, später ansehen oder archivieren. **Mit Lumen besprechen** bereitet einen Gesprächsentwurf vor; erst das Senden übermittelt ihn an die Modellanbindung.

Spielruhe sammelt Meldungen bei erkannten Spielen still. KDE bleibt für Empfang, ursprüngliche Aktionen und Ton zuständig. Lokale Systemmeldungen bleiben auf deinem Rechner. Lokale Erinnerungen brauchen das laufende Panel und erscheinen nach verpassten Terminen beim nächsten Start.

### Lumen Reader

**Lokal nutzbar.**

PDFs, EPUBs und gespeicherte Artikel lesen, Leseposition behalten, Text markieren und Randnotizen erfassen. Ausgewählte Passagen lassen sich als Quellen für Lumen verwenden. Lokales Vorlesen benötigt eine installierte Stimme. Nicht jedes Dokument enthält auslesbaren Text; Scans brauchen für Textfunktionen OCR.

[Reader und Vorlesen](READER-SOUND.md).

### Lumen Compose

**Die integrierte Text- und Dokumentenbearbeitung bleibt lokal; KI-Aufträge brauchen ein Modell.**

Texte übersetzen, korrigieren, umformulieren oder auf einen gewünschten Stil bringen. Du prüfst das Ergebnis, bevor du es weiterverwendest. Ausgewählter Text lässt sich auch direkt aus anderen Programmen an Lumen übergeben.

Die lokale Dokumentenbearbeitung bietet zusätzlich PDF-Funktionen, deren Grenzen vom Dokument abhängen. Layout, Schriften, Scans und Tabellen sind anspruchsvoller als einfacher Text; eine originalgetreue Ausgabe ist nicht für jedes PDF zugesichert. Die Server-App Compose ist ein eigener, serverseitiger Textweg und benötigt eine Verbindung.

[Text- und PDF-Funktionen](files/README.md#lumen-compose).

### Lumen Digitaler Haushalt

**Lokal nutzbar.**

Geräte, Verträge, Fristen, Handbücher und Belege zusammenhalten. Du kannst Informationen ergänzen, Belege öffnen und Einträge durchsuchen. Die lokale Haushaltsverwaltung braucht keine KI. Sie kündigt keine Verträge und führt keine Zahlungen aus. Automatische Routinen des Server-Haushalts sind davon getrennt.

### Lumen System

**Deinen Rechner und seine Einstellungen im Blick behalten.**

Lumen hilft dir auch als IT-Support für deinen Rechner. Es kann Systemwerte und Protokolle heranziehen, Fehler erklären und gemeinsam mit dir die Ursache eingrenzen. Erlaubte Maßnahmen lassen sich anschließend ausführen, etwa eine Anwendung installieren oder einen Dienst neu starten und seinen Zustand prüfen. Eine Diagnose startet auf deinen Auftrag; Änderungen folgen den Werkzeugfreigaben und nötigen Administratorrechten.

Die Systemansicht zeigt CPU, GPU, Arbeitsspeicher, Laufwerke, Prozesse und Sensoren. Die verfügbare Hardware bestimmt, welche Werte angezeigt werden. Eine KI-Auswertung startet auf Anfrage.

Im selben Fenster liegen **Sound** mit Ausgängen, Lautstärken und App-Regeln sowie **Arbeitsmodi** für Desktop- und Audioeinstellungen. Unterstützte Änderungen protokolliert Lumen; ein Rückweg wird nur angeboten, wenn er sicher möglich ist.

Lokale Sicherungen nutzen ausgewählte Quellen und Ziele sowie einen getrennt aufzubewahrenden Wiederherstellungsschlüssel. Eine erfolgreiche Wiederherstellungsprobe ist wichtiger als eine reine Erfolgsmeldung beim Sichern.

[Systemfunktionen](files/README.md#lumen-system) · [Audio](READER-SOUND.md).

### Lumen Companion und Bildschirmhilfe

**Lokal gestartet; Bildauswertung braucht ein geeignetes Modell.**

Ein Fenster oder einen Bildschirmausschnitt auswählen, die Vorschau prüfen und Lumen dazu fragen. Die Begleitung kann beim Verständnis einer Oberfläche und beim nächsten Arbeitsschritt helfen. Sie ist kein unbeschränkter Fernzugang zum Desktop.

Optionale Beobachtung von Änderungen ist begrenzt und hängt von der zugänglichen Fensterstruktur ab. Sichtbare Geheimnisse lassen sich nicht in jedem Programm zuverlässig erkennen. Pausiere die Begleitung, bevor du solche Inhalte eingibst. [Ablauf und Schutzgrenzen](INSTALL.md#screen-companion).

### Lumen Einstellungen und Updater

**Lokal nutzbar.**

Modellanbindung, Sprache, Darstellung, optionale Komponenten, Benachrichtigungen und Wartung verwalten. Die Oberfläche bietet Deutsch und Englisch. **Glas**, **Graphit**, **Atelier** und **Mitternacht** sind Themes derselben Panorama-Gestaltung.

Der Updater zeigt verfügbare Komponenten und führt die ausgewählten Schritte aus. Fenster werden bei Problemen nicht ungefragt beendet. Die Wiederanlaufhilfe kann nach einem Absturz Ansichten und Entwürfe anbieten; sie sendet keine alten Anfragen automatisch erneut und stellt nicht jede ungespeicherte Bearbeitung wieder her.

## Gemeinsame Apps mit Lumen Server

**Optionale Erweiterung:** Wenn du einen Lumen Server verbindest, kommen gemeinsame Inhalte und weitere Produktiv-Apps hinzu. Für die oben beschriebenen lokalen Gespräche, Lumen Files und Desktop-Benachrichtigungen ist diese Verbindung nicht erforderlich.

Lumen Server stellt die gemeinsamen Apps und Hintergrundaufgaben bereit; Lumen Mobile macht unterstützte Inhalte unterwegs zugänglich. Beide werden derzeit privat entwickelt und erprobt und sind noch nicht öffentlich gestartet. Preise und künftige Angebote sind nicht festgelegt.

Diese Apps benötigen einen erreichbaren Server, dein Konto und die passenden Gerätefreigaben. Der Desktop zeigt die gemeinsame Serveroberfläche in einem eigenen Fenster. Ihre früheren lokalen Implementierungen sind kein zusätzlicher Offline-Modus. Ohne Verbindung sind die Serverinhalte nicht bearbeitbar; bestehende lokale Dateien und Entwürfe werden dadurch nicht zu Serverdaten.

| App | Was du damit im Desktop erledigst |
| --- | --- |
| **Lumen Notes** | Notizen und Sammlungen öffnen, formatiert bearbeiten und gezielt für Lumen freigeben. Das lokale Lumen-Gedächtnis ist davon getrennt. |
| **Lumen Projekte** | Materialien, Gespräche und Aufgaben zu einem Vorhaben zusammenfassen; Quellen und Ergebnisse im Zusammenhang ansehen. Projekte ändern nicht automatisch Eigentum oder Freigaben ihrer Inhalte. |
| **Lumen Code** | Code-Vorhaben, zugehörige Aufgaben, Vorschläge und Ergebnisse in der Server-App bearbeiten. Ein Ausführungsauftrag folgt den dortigen Freigaben und verfügbaren Laufzeitmöglichkeiten. |
| **Lumen Inbox** | Die auf dem Server eingerichteten E-Mail- und Kalenderkonten nutzen, Nachrichten lesen und Entwürfe prüfen. Versand und Änderungen folgen den Serverfreigaben. |
| **Lumen Audio Studio** | Die gemeinsamen Meeting-/Radio-Inhalte öffnen, Transkripte und Hörskripte bearbeiten. Lokale Aufnahmen werden erst über einen bestätigten Übergabeweg bereitgestellt. |
| **Lumen Vault** | Den persönlichen oder freigegebenen Servertresor in einer privaten, gerätegebundenen Sitzung verwenden. Entsperren und Secret-Freigabe sind eigene Schritte; der lokale Zugangsdaten-Broker und lokale Sicherungen sind getrennte Funktionen. |

Zusätzlich kannst du auf Lumen Drive zugreifen, Server-Textgespräche führen und den Bearbeitungsstand eigener Servermeldungen zwischen Geräten teilen. Server-Textgespräche übertragen Text; lokale Anhänge, Gedächtnis und Tresor werden dabei nicht automatisch hochgeladen. Die Verbindung gibt dem Server keinen allgemeinen Zugriff auf deinen Rechner. Entfernte Diagnosen, Dienstaktionen und Wake-on-LAN benötigen eigene Gerätefreigaben.

Der Detailumfang richtet sich nach dem verbundenen Server. Die getrennten READMEs beschreiben [Lumen Server](https://forge.example.invalid/ativaro/lumen-server) und [Lumen Mobile](https://forge.example.invalid/ativaro/lumen-mobile); für die privaten Repositories ist Zugriff nötig. Technische Zuordnung: [Gemeinsame Server-Apps und lokale Fähigkeiten](docs/desktop-retirement.md).

### Lumen Server verbinden

1. In einem bereits verfügbaren Lumen Server **Geräte → Gerät hinzufügen** öffnen und eine Verbindungsanfrage für den Desktop erstellen.
2. Den angebotenen Link im Desktop öffnen lassen.
3. Im nativen Dialog Serveradresse, Konto und Rechte prüfen und bewusst bestätigen.

Erst die Bestätigung aktiviert den Gerätezugang. Ein Link allein teilt keine lokalen Dateien. Der Server kann den Zugang widerrufen. Welche Inhalte übertragen werden, hängt von der jeweiligen Freigabe und Aktion ab.

Für das optionale Textgespräch wähle im Gespräch **Dieses Gerät → Lumen Server · Textgespräch**; in der Suche liegt die Auswahl unter **···**. Bei einer Unterbrechung verwende **Serververbindung prüfen**. Unklare Übermittlungen werden geprüft, statt denselben Auftrag automatisch erneut zu senden.

## Schnellzugriff und fortgeschrittene Bedienung

| Aktion | Standard |
| --- | --- |
| Suchen oder fragen | `lumen-search` oder die Suche im Panel |
| Fragen | `Meta+Shift+O` |
| Zwischenablage erklären | `Meta+Shift+C` |
| Bildschirmausschnitt fragen | `Meta+Shift+V` |
| Markierten Text erklären | `Meta+Shift+E` |
| Einstellungen | `Ctrl+,` in Lumen/Files oder `lumen-settings` |

Bestehende KDE-Belegungen können mit Kürzeln kollidieren. Stelle sie bei Bedarf in den Einstellungen um.

Für Terminalnutzer gibt es `lumen-sel`, `lumen-gitmsg` und die optionale Shell-Integration mit `why`, `vix` und `sel`. Der MCP-Zugang stellt Systemabfragen und gesondert aktivierbare Aktionen bereit. Schreibende MCP-Aktionen sind standardmäßig nicht eingeschaltet (`LUMEN_MCP_ACTIONS=0`). Anleitungen: [Bedienung](LUMEN-GUIDE.md), [Engine-Anbindung](NATIVE-LUMEN.md).

<details>
<summary>Fortgeschrittene Konfiguration</summary>

Diese Variablen gehören zur lokalen Laufzeit, nicht in Chattexte oder öffentliche Supportberichte:

| Variable | Zweck |
| --- | --- |
| `LUMEN_OPENCODE_BIN` | Explizite Engine-Auswahl; normalerweise die verwaltete kompatible Laufzeit verwenden. |
| `LUMEN_WORKDIR` | Standard-Ausführungsverzeichnis. |
| `LUMEN_DATA` | Privater Zustand für Aufgaben und lokale Wissensfunktionen. |
| `LUMEN_STATE` | Cache und Berichte. |
| `LUMEN_WATCH_ANALYZE`, `LUMEN_WATCH_MODEL` | Watchdog-Auswertung und Modellwahl. |
| `LUMEN_MCP_ACTIONS` | Schreibende Systemwerkzeuge ausdrücklich aktivieren. |
| `LUMEN_SEL_LANG`, `LUMEN_VISION_PROMPT`, `LUMEN_GITMSG_STYLE` | Vorgaben für Text-, Bild- und Git-Hilfen. |

Eine optionale systemweite Sudo-Konfiguration ist in `install-system.sh` enthalten. Sie verändert unter anderem den Passwort-Cache für privilegierte Befehle und gehört nicht zum normalen Einstieg. Vor Verwendung das Skript und seine Wirkung prüfen; die Einrichtung ist keine Voraussetzung für Lumen.

</details>

## Daten, Rechte und Grenzen

- Dateien bleiben lokal, solange du sie nicht ausdrücklich überträgst oder einer Modellanfrage als Kontext mitgibst. Ein externer KI-Anbieter erhält den Inhalt der an ihn gesendeten Anfragen.
- Der lokale Suchindex und bestätigte Erinnerungen ersetzen nicht die Berechtigungen von Serverinhalten. Normale Textsuche bleibt ohne ein optionales Bedeutungsmodell möglich.
- Eigene Modelle, Server oder Anbieter können zusätzliche Hardware, Speicher oder Gebühren benötigen. Die Lumen-Installation garantiert keine kostenlose KI-Rechenleistung.
- Dateiverständnis ist keine Garantie für jedes Format oder jede Aussage. Dateischutz, verfügbare Lesewerkzeuge, Größenlimits und die Fähigkeiten des gewählten Modells gelten auch bei einer frei gewählten Datei.
- Bevor du wichtige Änderungen übernimmst, prüfe Vorschau und Ergebnis. Nicht jede Modellantwort ist richtig; nicht jede externe Aktion lässt sich rückgängig machen.
- Vollständige Einrichtung und Integration sind auf Arch/CachyOS mit Plasma 6 ausgerichtet. Einzelne Funktionen auf anderen Linux-Desktops ersetzen keine geprüfte Unterstützung des gesamten Systems.

## Entfernen und Wiederherstellen

Für eine Benutzerinstallation aus dem vorhandenen Checkout:

```bash
./uninstall.sh
```

Für eine Paketinstallation:

```bash
lumen-setup --uninstall
sudo pacman -R lumen
```

Prüfe vor dem Entfernen, welche Installation aktiv ist, und sichere persönliche Daten separat. Die Desktop-Gestaltung lässt sich über die bei der Aktivierung angelegte Sicherung zurücksetzen. [Installation und Wiederherstellung](INSTALL.md#recover-the-previous-desktop).

## Entwicklung, Prüfungen und Lizenz

[Installations- und Bauanleitung](INSTALL.md) · [Funktionsbeschreibung](LUMEN-GUIDE.md) · [Dateimanager](files/README.md) · [Architektur](docs/desktop-retirement.md) · [Veröffentlichung und Prüfgrenzen](PUBLISHING.md).

Der Quellstand allein ist kein Beleg, dass alle optionalen Funktionen auf jeder Hardware geprüft sind. Herkunft und verfügbare Releasebelege stehen in den jeweiligen Veröffentlichungsunterlagen.

Lumen-eigene Bestandteile stehen unter der [Lumen-EULA](LICENSE). Aktuell erlaubt sie persönliche und interne geschäftliche Nutzung sowie die beschriebenen lokalen Anpassungen; Weiterverteilung, Verkauf und kommerzielle Ableitungen benötigen eine ausdrückliche Erlaubnis. Frühere Lizenzgewährungen werden dadurch nicht widerrufen. Abhängigkeiten behalten ihre [eigenen Lizenzen](THIRD_PARTY_NOTICES.md); der Status der Distributionsprüfung steht in [LICENSE-PLAN.md](LICENSE-PLAN.md).
