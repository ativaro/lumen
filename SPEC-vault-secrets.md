# Plan: Lumen Vault für Passwörter und Geheimnisse

Stand: 04.10.2026 · **Architektur und Entwurf 1 freigegeben; native Testversion mit Rust-Prozess umgesetzt. Keine produktive Passwortverwaltung.**

## 1. Ziel und Empfehlung

Vault bekommt zwei gleichberechtigte Bereiche: **Tresor** und **Sicherungen**.
Der Tresor verwaltet Passwörter, API-Tokens, Wiederherstellungscodes und sichere
Notizen. Die bisherigen Restic-Sicherungen bleiben funktional erhalten.

Empfehlung für die Oberfläche: Entwurf 1 mit Sammlungen links, Einträgen in der
Mitte und Details rechts. Entwurf 2 bietet Favoriten und eine kompakte Detailleiste.
Beide verwenden dieselben Sicherheitsregeln und die vier vorhandenen Lumen-Themes.

Standardweg: „Tresor erstellen“ → Hauptpasswort festlegen → Wiederherstellung
verstehen → erster Eintrag. Technische Parameter werden sinnvoll vorbelegt;
Schlüsseldatei, KDF und Integrationen liegen unter „Erweitert“.

## 2. Ausgangslage im Projekt

- `files/tools_vault.py` und `files/vault_data.py` verwalten heute Backups.
- `files/tools_secrets.py` nutzt Secret Service für Zugangsdaten von Apps.
- `files/tools_data.py::Library` speichert Titel und JSON in unverschlüsseltem
  SQLite. Private Dateirechte sind **keine** Verschlüsselung. Diese Library ist
  kein Speicher für Tresoreinträge, auch nicht für deren sensible Metadaten.
- Gemeinsame Suche, Interop, Crash-Recovery, MCP und Lumen-Gedächtnis dürfen keine
  Tresorfelder automatisch übernehmen. Diese Ausschlüsse müssen technisch gelten.
- Der aktuelle Repository-Lizenztext ist MIT; die diskutierte kommerzielle/
  Community-Lizenzierung ist noch ein Vorschlag. Neue Abhängigkeiten dürfen diese
  spätere Entscheidung nicht still vorwegnehmen.

## 3. Sicherheitsziel und Grenzen

Geschützt werden sollen eine gestohlene Tresordatei, verlorene Backup-Medien,
versehentliche Klartextablage, unberechtigte Lumen-Werkzeugaufrufe, manipulierte
Importdateien und unbeabsichtigte Weitergabe an KI-Anbieter.

Ein entsperrter Tresor kann auf einem vollständig kompromittierten Rechner nicht
zuverlässig vor Root, Keyloggern oder einem manipulierten Desktop schützen.
Prozessgrenzen, Speicherhärtung und Wayland reduzieren Risiken; sie sind keine
absolute Isolation gegenüber Schadsoftware desselben Benutzers. Dateiverschlüsselung
verhindert außerdem nicht das Zurückspielen einer älteren, gültigen Datei.

### Verbindliche Regeln

1. Geheimnisse und sensible Metadaten nur verschlüsselt speichern: auch Titel,
   Benutzernamen, URLs, Notizen, Tags, Token-Berechtigungen und Änderungshistorie.
2. Kein Klartext in SQLite/WAL, QSettings, Temp-Dateien, Logs, Crash-Recovery,
   Befehlsargumenten, persistenten Umgebungsvariablen, Suchindex oder Telemetrie.
3. Ein gesperrter Tresor zeigt keine Eintragsliste oder Suchtreffer. Nur ein bewusst
   gewählter, nicht sensibler Tresor-Anzeigename darf außerhalb der Datei liegen.
4. Keine automatische Weitergabe an Chat, Modelle, Wissen oder generische MCP-Tools.
5. Fehler führen zu einer Sperre oder einer klaren Fehlermeldung; kein Ersatzspeicher
   im Klartext, kein stiller Wechsel zu schwächerer Verschlüsselung.
6. Der allgemeine „Nicht mehr fragen“-Modus erteilt keinerlei Tresorberechtigung.

## 4. Speicherformat und technische Entscheidung

**Bevorzugt: KDBX 4.x, Ziel 4.1, mit Argon2id und AES-256 samt der im Format
vorgeschriebenen Integritätsprüfung.** Keine selbst entworfene Verschlüsselung,
kein eigener Passwort-Hash als Ersatz für die Verschlüsselung. KDF-Parameter werden
auf dem Zielgerät kalibriert (Entsperren ungefähr eine Sekunde); Speicherbedarf und
schwächere Zweitgeräte werden berücksichtigt. Ein vorhandener Tresor wird nicht
unbemerkt heruntergestuft. Zufallswerte stammen aus dem Betriebssystem-CSPRNG.

Die genaue Formatversion und optionale Funktionen richten sich nach nachgewiesener
Kompatibilität, nicht nach einem bloßen „KDBX unterstützt“-Häkchen. Persistente
Dateien, temporäre Schreibdateien und Sicherungskopien enthalten ausschließlich
authentifiziert verschlüsselte Daten. Dateirechte 0600, Verzeichnisse 0700.

### Backend-Auswahl als erste verbindliche Prüfstufe

| Kandidat | Vorteil | Noch zu klären / Entscheidung |
|---|---|---|
| KeePassXC als separat installierte Komponente | Etablierte Umsetzung, vorhandene Sicherheitsprüfungen, KDBX-Kompatibilität | Schnittstellen decken nicht automatisch unsere vollständige native CRUD-UI ab. Integrationsumfang, unterstützte Versionen, Prozess-/IPC-Modell und GPL-Verpflichtungen prüfen. Keine Audit-Zertifizierung auf Lumen übertragen. |
| Rust-Broker mit KDBX-Bibliothek | Kleine Secret-Grenze, gezielt löschbare Puffer, kein Secret in allgemeinen Python-Modellen | `keepass-rs` bezeichnet KDBX4.1-Schreiben ausdrücklich als experimentell. Kein Produktionsstandard nur wegen Rust oder MIT. Roundtrip-, Korruptions-, Kompatibilitäts- und Sicherheitsprüfung erforderlich. |
| Python-Bibliothek im bestehenden Vault-Prozess | Schneller Prototyp, vorhandenes Qt-Gerüst | Erhöht Kopien von Secrets in unveränderlichen Strings und die Angriffsfläche durch andere App-Module. Nicht der empfohlene Produktionsweg. Bibliothekslizenz gesondert prüfen. |

**Entscheidung:** KDBX ist die bevorzugte Dateibasis; eine bestimmte Engine wird erst
nach dieser Prüfstufe festgelegt. Wenn kein Kandidat die Anforderungen erfüllt,
bleibt die Funktion ein Prototyp mit synthetischen Daten. Kein Ausweichen auf schnell
selbst geschriebene Kryptografie. Abhängigkeiten werden in fester Version erfasst,
inklusive Lizenzinventar und Verfahren für Sicherheitsupdates.

### Prozessaufteilung

- Lumen-Ansicht: Eintragsverwaltung, Suche und maskierte Darstellung.
- Kleiner Tresor-Prozess: Entsperren, verschlüsseltes Lesen/Schreiben, Secret-Zugriff,
  Passwortgenerator und Sperrlogik; ohne LLM, Plugins oder allgemeine Shell-Funktion.
- Dedizierte sichere Eingabe-/Anzeigekomponente: Masterpasswort und freigegebene
  Secret-Felder gehen nicht durch allgemeine Python/QML-Datenmodelle. Dafür wird
  ein nativer Qt/C++-Baustein oder eine vergleichbar prüfbare Grenze evaluiert.
- Lokale private IPC, möglichst geerbte Kanäle statt offenem Desktop-Dienst.
  Begrenzte Nachrichten, echte Sitzungscapability, Peer-Prüfung und Ablaufzeiten.
  Gleiche UID oder eine vom Client behauptete App-ID allein sind kein Zugriffsnachweis.
- Schlüssel nur solange erforderlich im Speicher. Zeroization, Core-Dumps aus,
  soweit verfügbar gesperrte Speicherseiten. Keine Behauptung vollständiger
  Speicherlöschung durch Python-Garbage-Collection. Metadatenansichten beim Sperren
  ebenfalls verwerfen. Ein kompromittiertes Betriebssystem bleibt außerhalb der Garantie.

## 5. Funktionen und sichere Vorgaben

| Bereich | Erster Lieferumfang / Standard |
|---|---|
| Eintragstypen | Anmeldung, API-Token, sichere Notiz, Wiederherstellungscodes; frei benennbare geschützte Zusatzfelder |
| Anmeldung | Name, Website, Benutzername, Passwort, Notiz; alle Felder in verschlüsselter Datei |
| API-Token | Dienst, Secret, optionale Umgebung, dokumentierte Berechtigungen, Ablaufdatum; keine automatische Aussage über tatsächliche Provider-Rechte |
| Generator | Lokal, CSPRNG; standardmäßig 24 zufällige Zeichen oder Passphrase; keine KI-Erzeugung; Website-Regeln anpassbar |
| Organisation | Sammlungen, Favoriten, Tags, verschlüsselte Eintragshistorie und Papierkorb |
| Suche | Nur im entsperrten Tresor im RAM; keine Aufnahme in globale Dateisuche oder Lumen-Gedächtnis |
| Anzeigen | Maskiert; ausdrücklich kurz einblenden, nach 10 Sekunden wieder verbergen; kein Inhalt in Vorschauen/Tooltips |
| Sperren | Sofort bei Sitzungssperre und Suspend; nach 5 Minuten Tresor-Inaktivität; expliziter Sperrbutton; Wiederaufnahme gesperrt |
| Kopieren | Bewusster Klick, nach 20 Sekunden bereinigen, sofern noch der eigene Inhalt; fremde Zwischenablage nicht löschen |
| Zwischenablage-Historie | KDE-Kennzeichnung für sensible Inhalte, kein PRIMARY-Selection-Kopieren; Klipper und weitere Manager gezielt testen |
| System-Schlüsselbund | Hauptpasswort dort standardmäßig nicht hinterlegen. Bequeme Geräte-Entsperrung erst später, separat opt-in |
| Netzverkehr | Tresorkern lokal; keine automatischen Favicons, Leak-Abfragen, Cloud-Synchronisation oder KI-Verbindung |

Zwischenablage-Markierungen und späteres Leeren können fremde Programme nicht
zwingen, bereits gelesene Inhalte zu vergessen. Auch Bildschirmfotos lassen sich
nicht universell verhindern. Lumen-eigene Bildschirm-/Clipboard-Analyse muss
sensible Vault-Oberflächen explizit ausnehmen; nach dem Kopieren in fremde Apps
kann Vault nicht mehr jede Weitergabe kontrollieren.

TOTP folgt später optional. Passwörter und TOTP im selben Tresor sind bequem,
aber keine getrennten Faktoren gegenüber einem Tresorkompromiss. Passkeys und
Browser-Autofill sind eigene spätere Integrationen, kein beliebiges Textfeld und
kein pauschales „Tippe das Passwort ins aktive Fenster“.

## 6. Lumen, MCP und App-Zugänge

**V1:** MCP darf ausschließlich nicht sensible Zustände wie gesperrt/entsperrt
melden oder eine native Tresor-Ansicht öffnen. Keine Eintragsnamen/URL-Listen,
kein `get_password`, kein `get_token`, kein Tool-Ergebnis mit Geheimnissen.

**Später:** Lumen darf die *Verwendung* eines Zugangs für eine konkrete Aktion
anfragen. Die native Oberfläche lässt den Nutzer lokal einen Eintrag wählen und
zeigt an: „Lumen Inbox möchte diesen Zugang für mail.example verwenden.“

- Bindung an einen geprüften Connector, Ziel/Origin, konkreten Vorgang und kurze
  Lebensdauer; sichtbare Freigabe durch den Nutzer, standardmäßig einmalig.
- Der Broker übergibt das Secret direkt an den begrenzten Connector, nicht an das
  Modell, die Chat-Historie oder eine allgemeine Shell. Keine „beliebige URL mit
  Authorization-Header“-Funktion; Redirects dürfen keinen Secret-Abfluss erlauben.
- Ein Token muss beim autorisierten Zieldienst verwendet werden dürfen. Die Zusage
  heißt deshalb „nicht zum KI-Modell“, nicht „verlässt niemals den Rechner“.
- MCP erhält nur Ergebnisstatus/Fehler ohne Tokens. Auch Fehlermeldungen,
  Netzwerktraces und Debug-Logs des Connectors dürfen keine Secrets zurückgeben.
- Titel und Notizen im Tresor sind Daten, keine Ausführungsanweisungen. Webseiten
  oder Nachrichten können keine Tresorfreigabe erteilen (Prompt-Injection-Grenze).
- Existierende Inbox-/Restic-Schlüsselbunddaten werden nicht automatisch übernommen.
  Spätere Migration pro Konto mit geprüftem Rückweg; Hintergrund-Backups dürfen
  durch einen neu gesperrten Passworttresor nicht unbemerkt ausfallen.

### Bestehende Agent-Rechte ausdrücklich einbeziehen

Das heutige OpenCode-Backend kann allgemeine Systemwerkzeuge besitzen. Eine
MCP-Allowlist allein verhindert dann nicht, dass ein fehlgeleiteter Agent andere
Zugriffspfade versucht. Die Aussage „kein Secret zum Modell“ ist zunächst eine
Datenflussregel, keine garantierte Isolation gegen einen uneingeschränkten Agenten.

Vor einer Freigabe integrierter Secret-Verwendung muss die Agent-Ausführung
wirksam begrenzt sein: kein Tresor-IPC, Prozessspeicherzugriff, Clipboard-D-Bus,
Bildschirm-/Eingabezugriff oder Zugriff auf Entsperr-Capabilities. Die Grenzen
müssen unter KDE/Wayland praktisch nachgewiesen werden, z. B. durch eine passende
Sandbox mit eingeschränkten D-Bus-/Dateisystem-/Prozessrechten. Agentenaktionen,
die diese Grenze aufheben, dürfen nicht still durch „Don't ask“ freigegeben werden.
Vaults eigene UI und ein ausdrücklich autorisierter Connector sind getrennte
Vertrauensbereiche. Ohne diese Einschränkung kann Lumen keine absolute Garantie
gegen Secret-Abfluss durch beliebige Agent-Systemwerkzeuge geben; das bleibt eine
sichtbar dokumentierte Grenze und verhindert die Freigabe dieser Integration.

## 7. Sicherung, Wiederherstellung und NAS

- Nach jeder bestätigten Änderung atomar schreiben: verschlüsselte temporäre Datei,
  fsync, ersetzen, Verzeichnis synchronisieren; bei Fehlern alte Datei erhalten.
- Ein Schreiber pro Tresor. Vor dem Ersetzen Dateirevision prüfen; Konflikte zeigen,
  keine heimliche „letzte Änderung gewinnt“-Lösung. Sperre auf NAS nicht blind vertrauen.
- V1 arbeitet mit einer lokalen aktiven Datei. Das NAS ist ein optionales Ziel für
  verschlüsselte Kopien/Restic-Backups, zunächst kein gleichzeitig bearbeiteter Tresor.
- Bestehendes Vault sichert die bereits verschlüsselte Tresordatei, nicht deren
  entschlüsselte Einträge. Dadurch bleibt die Tresor-Verschlüsselung zusätzlich
  zur Restic-Verschlüsselung erhalten. Konsistenten Stand verwenden.
- Backup-Schlüssel darf für unbeaufsichtigte Backups nicht ausschließlich in dem
  gesperrten Tresor liegen, den dieses Backup erst sichern soll.
- Wiederherstellung auf leerem Testprofil mit Tresor-Hauptpasswort und ggf.
  Schlüsseldatei nachweisen. Restic-Wiederherstellung allein entsperrt KDBX nicht.
- Hauptpasswortverlust ohne weitere gültige Zugangsmittel ist nicht zurücksetzbar.
  V1 verspricht keinen separaten Wiederherstellungscode, den das gewählte Format
  nicht unterstützt. Optionales Notfallblatt enthält vom Nutzer gewählte Hinweise
  und Offline-Aufbewahrung; sensible Ausgabe nur ausdrücklich, nicht automatisch.
- Ein Hauptpasswortwechsel ändert keine schon vorhandenen Sicherungskopien.
  Ein gelöschter Eintrag kann in Historie/Backups verbleiben. Keine Garantie für
  physisches Löschen auf SSD, Copy-on-write-Dateisystemen oder alten Snapshots.

## 8. Vorschläge für die Oberfläche

### Entwurf 1 — Tresor-Verwaltung (Empfehlung)

Drei klare Bereiche: Sammlungen → Liste → Details. Die Suche bleibt oben in der
Liste. Sichtbare Aktionen direkt am Feld: Benutzername kopieren, Passwort kurz
anzeigen/kopieren. Eintragsbezogene App-Zugriffe stehen darunter, nicht in einem
versteckten globalen Einstellungsmenü. Gut für viele Konten, Server und Tokens.

Oben „Tresor | Sicherungen“, rechts immer „Sperren“. Unten diskreter Status für
lokale Speicherung und automatische Sperre. Keine pauschale grüne Aussage „Alles
sicher“. Ablaufdatum und konkrete Warnungen ersetzen einen dekorativen Sicherheitswert.

### Entwurf 2 — Schnellzugriff

Große lokale Suche, kleine Favoritenkacheln, darunter zuletzt verwendete Einträge.
Auswahl öffnet die Detailleiste. Weniger Verwaltungsgefühl; ideal für wenige häufig
benutzte Zugänge. Kacheln zeigen keine Secrets; Geheimnisse bleiben feldweise maskiert.

### Gemeinsamer Sperrzustand

Eine ruhige Sperrfläche ersetzt *sämtliche* Listen und Details: Tresorname,
Passwortfeld, „Entsperren“, alternative Schlüsseldatei unter „Weitere Optionen“.
Keine noch sichtbaren Namen im Hintergrund; auch keine unsichtbar weiterlebenden
Suchmodelle. Eine Sperre während Bearbeitung darf keinen Klartext-Entwurf schreiben.
Transaktionen werden vor Bestätigung sicher gespeichert; ungespeicherte sensible
Eingaben werden beim Sperren verworfen, mit klarer UI-Rückmeldung.

Die Mockups sind Zielbilder mit Beispieldaten. „Verwendung erlauben“ zeigt bereits
den späteren Integrationszustand; diese Aktion kommt erst nach der Broker-Prüfung.

## 9. Umsetzung in Reihenfolge

| Schritt | Ergebnis | Abnahme vor dem nächsten Schritt |
|---|---|---|
| 1. Engine-/Lizenzprüfung | Gewählte Engine, Formatmatrix, Bedrohungsmodell, begrenzte API | Erstellen/Ändern/Öffnen in Lumen-Prototyp und KeePassXC ohne Datenverlust; Lizenzinventar, keine als experimentell ungeprüft ausgelieferte Schreibfunktion |
| 2. Tresorkern | Erstellen, sperren, entsperren, Lesen/Schreiben, Generator | Falscher Schlüssel, manipulierte/trunkierte Dateien, teure KDF-Header, Limits für Archive/Anhänge, Parallelzugriff und Stromausfall-Simulation sicher behandelt |
| 3. Native Oberfläche | Entwurf 1, vier Themes, DE/EN, Tastatur, maskierte Felder | Keine Geheimnisse in UI-Modellen/Tooltips/Accessibility-Ausgaben beim Sperren; Race-Tests für Anzeigen/Kopieren/Suspend |
| 4. Import und Recovery | Erst KDBX, dann klar deklarierte CSV-/JSON-Importe; verschlüsselte Exporte/Backups | Import als begrenzte untrusted Daten, keine Skripte/URLs automatisch ausführen; Restore ohne Ursprungsrechner funktioniert; Originalimportdatei nicht automatisch löschen |
| 5. Systemintegration | App-Katalog, Settings, Setup, Panel, eingeschränkte MCP-Metadaten | Gesperrter Tresor bleibt überall undurchsuchbar; KI-/Crash-/Clipboard-/Backup-Ausschlüsse nachgewiesen |
| 6. Freigabe für reale Daten | Prüfbericht, aktualisierbare Pakete, dokumentierter Wiederherstellungsweg | Unabhängige fachkundige Sicherheitsprüfung des gewählten Integrationsstands; kritische/hohe Findings behoben und nachgeprüft |
| 7. Erweiterungen | App-gebundene Verwendung, optional TOTP/Browser/Sync | Je neue Grenze eigenes Bedrohungsmodell, Missbrauchstests und Review |

Sicherheitsprüfung bedeutet hier überprüfbare Arbeit, kein bloßes Label. Vor Schritt
6 ausschließlich synthetische Testdaten. Eine fremde Engine-Prüfung zertifiziert
weder Lumen noch unseren Broker, unsere Oberfläche oder unsere Zwischenablagewege.

### Konkrete Tests

- Synthetische Canary-Secrets speichern/kopieren/ändern; alle Logs, Dateien,
  SQLite/WAL, Crashzustände, Suchindex, Interop-Nachrichten und Modellanfragen
  prüfen. Erwartet: außerhalb der verschlüsselten Datei und erlaubter flüchtiger
  Zielkanäle keine Treffer. RAM-Tests gesondert, kein falscher Null-Risiko-Beweis.
- App-Sperre, Bildschirmsperre, Suspend/Resume, Prozessabsturz, fehlendes
  Lock-Signal, Datenbankkonflikt, voller Datenträger und unterbrochener Schreibvorgang.
- Clipboard: Klipper speichert nicht; fremder neuer Inhalt bleibt nach Ablauf
  erhalten; Vault-Inhalt wird nach Ablauf/Sperre/Beenden bereinigt, soweit OS erlaubt.
- Eingaben mit Unicode/mehreren Sprachen und langen Feldern; keine Wortfilter zur
  Feststellung, ob etwas ein Passwort ist. Schutz folgt Typ/Provenienz und Zugriffspfad.
- UI-Ende-zu-Ende über *echte* Startwege: Panel → Vault → Tresor; Einstellungen;
  globale Suche; nicht nur direkte CLI-Aufrufe.
- Import-Roundtrips mit benutzerdefinierten Feldern/History; unbekannte Funktionen
  im Zweifel nur lesend behandeln. Größen-/KDF-Limits verhindern Speicher-/CPU-DoS.
- Abhängigkeiten, signierte Lieferwege, Integrität der Updates und Fehlerberichte
  ohne geheime Inhalte. Kein Passwortmanager-Release ohne Verantwortlichkeit für Updates.

## 10. Quellen und offene Entscheidungen

Geprüfte Primärquellen (04.10.2026):

- [KDBX-Spezifikation](https://keepass.info/help/kb/kdbx.html): Format, KDF und Integrität.
- [KeePass-Sicherheitsmodell](https://keepass.info/help/base/security.html): Verschlüsselung und Schlüsselableitung.
- [KeePassXC-Handbuch](https://keepassxc.org/docs/KeePassXC_UserGuide): Konfiguration und Integrationsgrenzen.
- [KeePassXC-Prüfungen](https://keepassxc.org/audits/): ausdrücklich versions-/plattformgebunden.
- [keepass-rs](https://docs.rs/keepass/latest/keepass/): MIT, Schreiben als experimentell dokumentiert.
- [Secret-Service-Attribute](https://specifications.freedesktop.org/secret-service/latest/lookup-attributes.html): Suchattribute sind nicht das verschlüsselte Secret.
- [KeePassXC-Clipboard-Code](https://raw.githubusercontent.com/keepassxreboot/keepassxc/develop/src/gui/Clipboard.cpp): sensible MIME-Kennzeichnung; technische Referenz, kein zu kopierender GPL-Code.

Noch zu entscheiden: konkrete Engine nach Prüfstufe 1; Geräte-Entsperrung/Hardware-
Schlüssel; späteres Browser-/Mehrgeräte-Konzept. Vorgeschlagene V1 benötigt davon
nur die Engine-Entscheidung. Der Nutzer hat Architektur und Entwurf 1 am 04.10.2026
freigegeben. Gate 1 ist noch nicht bestanden, Gate 6 wurde nicht durchgeführt.

## 11. Umsetzungsstand 04.10.2026

- Eigenständige Qt-Quick-Designvorschau in `files/vault_preview.py` und
  `files/qml/vault/`, erreichbar über Vault → „Tresor · Vorschau“ oder
  `lumen-vault --preview`. Vier Themes, Deutsch/Englisch, Suche, Sammlungsfilter,
  Favoriten, Papierkorb/Wiederherstellen und zeitlich begrenztes Anzeigen fester
  Beispieldaten. Sperren zerstört Liste, Details und Suche.
- Keine freien Secret-Eingaben, Imports, Dateiablage, echte Entsperrfunktion oder
  Clipboard-Schreibzugriffe. „Neuer Eintrag“/„Bearbeiten“ erklären diesen Zustand.
  Der Vorschauprozess ist kein Tresorkern und kein sicherer Eingabebaustein.
  Python/Qt-Modelle enthalten ausschließlich veröffentlichbare synthetische Werte;
  reale Secrets dort einzusetzen ist ausdrücklich keine zulässige Integration.
- Restic-Sicherungen bleiben der Standardbereich. Keine Bestandsmigration.
- MCP `lumen_vault_secrets_status` meldet nur die fehlende Produktfreigabe, ohne
  eine Library, einen Tresor oder Nutzerdaten zu öffnen.
- KeePassXC CLI 2.7.12 wurde aus dem signaturgeprüften Distributionspaket für den
  Engine-Test installiert, nicht als neue Laufzeitabhängigkeit von Lumen.
- Reproduzierbarer Test: `python research/vault/probe_keepassxc.py`.
  `db-create -p -t 1000` und XML-Reimport ergaben **KDBX 3.1 / AES-KDF**.
  XML-Übergabe über anonymen geerbten Linux-Memory-FD funktioniert ohne
  Klartextdatei; falsches Passwort, manipulierte und trunkierte Datei wurden
  abgewiesen. Das reicht nicht für Gate 1. Die CLI bietet keine Argon2id-Auswahl;
  ein XML-Neuimport bewahrt die Verschlüsselungsparameter nicht.
- KeePassXC-Code wurde nicht kopiert oder verlinkt. Das Testprogramm ruft die
  separat installierte ausführbare Datei auf. Eine spätere produktive Integration
  braucht weiterhin Schnittstellen- und Lizenzprüfung. Der Repository-Lizenztext
  wurde nicht geändert.
- Nächster verbindlicher Schritt: Engine mit unterstützter vollständiger
  Schreibschnittstelle qualifizieren (KDBX4/Argon2id, Custom Fields/History,
  Roundtrips, Ressourcenlimits, native Secret-Grenze). Keine Freigabe echter Daten
  und kein improvisiertes Kryptografieformat, um diesen Schritt zu überspringen.

Die Vorschau ist eine separat prüfbare UI-Arbeit, keine vorgezogene Abnahme der
Schritte 2–6. Import, Recovery, native Secret-Eingabe, Clipboard-Härtung und
Agent-Isolation sind weiterhin **nicht implementiert/abgenommen**.

## 12. Rust-Kern: erster ausführbarer Nachweis (04.10.2026)

Auf die Freigabe „go“ folgt nun `native/vault-core/`: ein echter Rust-Lese-/
Schreibkern mit fest gepinntem `keepass` 0.15.0 und Cargo.lock, keine weitere
UI-Simulation. Der einzige ausführbare Einstieg nimmt keine Nutzereingaben an
und arbeitet ausschließlich mit selbst angelegten synthetischen Testtresoren.

Nachgewiesen: neue KDBX4.1-Datei mit AES-256/Argon2id, geschützte Felder und
Historie, Speichern/Sperren/Öffnen, zufällige neue Verschlüsselung beim Speichern,
verschlüsseltes Backup und Restore in frischem Verzeichnis. KeePassXC 2.7.12
liest den Rust-Tresor, ändert sein Beispielpasswort, anschließend liest Rust
geändertes Passwort, Unicode, Zusatzfeld und Historie wieder korrekt. KeePassXC
schreibt dieses Beispiel als KDBX4.0 zurück; die Kryptoparameter bleiben gleich
und der Leser unterstützt diesen geprüften Profilwechsel ausdrücklich.

Acht Tests, Formatprüfung, Clippy ohne Warnungen und RustSec-Audit bestanden.
Letzteres: 0 bekannte Schwachstellen / 0 Warnungen zum geprüften Stand. Tests
umfassen falschen Schlüssel, beschädigte/trunkierte Dateien, KDF-/Größenlimits,
Dateirechte/Symlinks, parallele Schreiber, erkannte Revisionkonflikte, einen echten
fehlgeschlagenen Backup-Rename und Prüfungen auf synthetische Klartextmarker.

**Noch keine vollständige Engine- oder Produktfreigabe:** Upstream-Schreiben bleibt
experimentell. Die Profile sind begrenzt (u. a. kein komprimierter Import), KDF
noch nicht gerätekalibriert, nicht alle Bibliothekspuffer nachweislich gelöscht.
Lock und Revisionprüfung schützen nicht atomar gegen fremde Programme, die das
Lock ignorieren. Stromausfall-/Dateisystemprüfung, sichere native Eingabe/IPC,
Clipboard, Agent-Isolation und externe Prüfung bleiben offen. Diese Grenzen
stehen mit konkreten nächsten Arbeiten in `native/vault-core/README.md`.

Der Desktop-Paketstand bleibt 1.2.0-66, die Passwort-UI weiterhin Beispieldaten.
Der Rust-Testkern wird nicht als freigegebener Passwortmanager installiert oder
an KI/MCP gekoppelt. Die Laufzeit benötigt keine neue Kryptografie-Implementierung;
Algorithmen und KDBX stammen aus den dokumentierten Bibliotheken. Kein KeePassXC-
Code wurde übernommen und keine Projektlizenz umgestellt.

## 13. Native Testversion und Lizenznachweise · 04.10.2026

C++/Qt-Widgets-Oberfläche mit Rust-Broker über ausschließlich geerbte private
Prozesskanäle implementiert. Erstellen/Entsperren, persistente geschützte Felder,
Generator, Sammlungen/Favoriten/Papierkorb, maskierte Anzeige, zeitbegrenztes
Kopieren, Sperren und verschlüsselte Sicherung/Wiederherstellung funktionieren
im Testdatenmodus. Deutsch/Englisch und die vier Lumen-Themes sind enthalten.

`lumen-vault --lab` startet die ausdrücklich installierte Testversion. Standard-
Installation bleibt bei der Designvorschau; Restic wird nicht migriert. MCP meldet
`native_laboratory` und weiterhin `available=false`/`real_secrets_supported=false`.
KDF für neue Labor-Dateien wird gerätebezogen angenähert kalibriert. Dateizugriffe
binden das Verzeichnis an einen offenen Deskriptor; fremde Programme können nach
wie vor eine finale Revisionsprüfung umgehen, wenn sie unser Lock ignorieren.

98 Rust-Abhängigkeiten samt tatsächlichen Notices, Paketmanifesten und Hashprüfung
erfasst; Qt LGPLv3/GPLv3-Texte und Rust-Laufzeithinweise liegen bei. CMake verwendet
nur dynamisches Qt Core/Gui/Widgets/DBus (Test zusätzlich in Tests). Kein KeePassXC-
Code kopiert/verlinkt, keine Projektlizenz geändert. Der lokale Installer legt
auch die neu kompilierbaren Quellen bei. Gesamtlizenzierung einschließlich
PyMuPDF/AGPL bleibt separat gemäß LICENSE-PLAN.md zu prüfen.

**Freigabe bleibt geschlossen:** Bibliotheks-/Qt-Speicherlebensdauer, breitere
Fault-/Fuzz-/Dateisystemprüfungen, echte KDE-Clipboard-/Sperrrennen und das externe
Expertenreview sind nicht durch die funktionierenden Tests ersetzt. Einzelne
Labor-Limits und verbleibende Produktionsarbeit stehen ausdrücklich in
`native/vault-ui/README.md` und `REVIEW.md`. Keine echte Zugangsdaten übernehmen.
