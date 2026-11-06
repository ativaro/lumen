# Lumen Dranbleiben bei unterbrochenen Kopien

Auftrag: Entwurf „Dranbleiben“ als vollständigen Desktop-Weg umsetzen. Pro
gespeichertem Kopierauftrag lässt sich ausdrücklich auswählen, dass Lumen die
Verfügbarkeit erneut prüft und eine relevante Änderung meldet. Fortsetzen bleibt
eine ausdrückliche Aktion auf demselben Auftrag.

## Umfang und Abschlusskriterien

- [x] Standardmäßig aus; Aktivieren, Aufschieben und Ausschalten pro Transfer.
- [x] Nur unterbrochene native Kopien mit gespeichertem Kopierplan, einschließlich
  über das Dateisystem eingebundener SMB-Ziele. Keine neue Server-/Cloud-Freigabe.
- [x] Bestehender Minuten-Timer, gespeicherter Backoff und Wiederanlauf ohne Files.
- [x] Nur lesender Probe-Prozess mit Zeitlimit und exklusiver Lease; langsame oder
  hängende Ziele blockieren weder Oberfläche noch weitere Aufträge.
- [x] Ursprüngliches Ziel, Quellen und Kopierzwischenablage erneut prüfen.
  Erreichbarkeit ersetzt keine Inhaltsprüfung; der vorhandene Kopierkern prüft
  die Teildaten beim ausdrücklich gestarteten Fortsetzen.
- [x] Eine dauerhafte Meldung pro relevanter Zustandsänderung; keine Wiederholung
  bei unverändertem Zustand. Opt-out/Abbruch/Fortsetzen verhindert alte Ergebnisse.
- [x] Meldung öffnet und markiert denselben Transfer in Lumen Files. Native
  Betriebssystemmeldungen enthalten weiterhin keine privaten Dateinamen/Pfade.
- [x] Synthetischer Weg: Teilkopie → Ziel weg → wieder da → eine Meldung → manuell
  fortsetzen → bytegleiches Ergebnis; zusätzlich Ablehnung veränderter Bindungen,
  Zeitüberschreitung, Neustart, Aufschieben und Opt-out während einer Prüfung.
- [x] Tatsächliche UI bei Graphit/Atelier, DE/EN, schmal/normal und Tastatur prüfen;
  gemeinsame Panorama-Bausteine erhalten, keine zusätzliche App-Leiste.
- [ ] Quellcommit, Dateihashes und Prüfnachweise an Root/General übergeben;
  Installation und Rückweg ausschließlich über deren freigegebenen Prozess.

## Grenzen

Keine automatische Schreibaktion, kein automatisches Einbinden/Anmelden, keine
Modellabfrage und kein allgemeiner Heartbeat für andere Vorhaben. Ein neu
eingebundenes oder verändertes Ziel muss manuell überprüft werden. Vorhandene
Dateien, Transferkennungen und der technische historische Speicherschlüssel
`workplace/transfer/` bleiben erhalten; daraus entsteht kein Produkt-Arbeitsraum.

## Stand

Privater Desktop-Kandidat implementiert. 65 gezielte Prüfungen auf dem privaten
Abbild der tatsächlichen Installation bestanden; 27 davon prüfen Dranbleiben,
einschließlich echter Kopierworker und privater D-Bus-Verbindung. Ein alter oder
noch nicht gebundener Files-Empfänger nimmt den Transferaufruf nicht stillschweigend
an. Die Meldung bleibt in diesem Fall ungelesen. Ein ausgewählter Vorgang bleibt
auch bei mehr als 200 Tickets erreichbar. Ein unbekannter Transfer beim Kaltstart
erzeugt einen sichtbaren Fensterfehler über denselben Handler wie eine erneute
Aktivierung. Die normale geerbte Files-Aktivierung bleibt verfügbar.

Eine relevante Meldung reserviert ihre monotone Revision, Kennung und
`pending_notice` zuerst dauerhaft im bestehenden Followup-Datensatz. Erst danach
publiziert eine zweite kurze Store-Transaktion die Meldung und quittiert sie.
Der Store-Schreiblock schützt dabei gegen paralleles Ausschalten oder erneutes
Aktivieren. Schreib- oder Commitfehler nach der Publikation lassen die gespeicherte
Absicht für einen begrenzten Wiederholungsversuch erhalten; die gleiche Revision
erzeugt keinen zweiten Popup. Ausschalten kennt auch dann die bereits reservierte
Meldungskennung. Erneutes Aktivieren verwendet die nächste Revision, sodass eine
vom Nutzer archivierte Karte die neue Meldung nicht unterdrückt. Reservierungs-,
Schreib- und Commitfehler, Ausschalten, Archivieren und erneutes Aktivieren sind
gezielt geprüft. Es gibt keine zusätzliche Datenbank oder Ausführungseinheit.

Der aktivierte vorhandene Timer prüft fällige Vorgänge bei seinen Läufen. Nach
Fehlern steigt die Wartezeit von einer Minute bis auf 30 Minuten. Höchstens drei
Prüfversuche pro Lauf und ein gleichzeitig lebender Probe-Prozess verhindern
unbegrenzte Folgeprozesse; ein belegter Probe-Platz verschiebt die Prüfung ohne
Änderung der letzten Bereitschaft. Bereits laufende gewöhnliche Jobs können den
nächsten Timerlauf verzögern. Der Schalter startet den vorhandenen Timer asynchron;
Fehlschlag und Zeitüberschreitung lassen Dranbleiben ausgeschaltet. Dieser
Systemd-Aufruf wurde im privaten UI-Test simuliert, kein persönlicher Timer aktiviert.

Native Bilder: Graphit 1120×860 sowie Graphit/Atelier 1000×680, Deutsch/Englisch,
aus/wartend/erreichbar und Tab-Reihenfolge. Files besitzt schon vorher eine
Mindestbreite von 1000; eine Anforderung von 800 ergibt deshalb 1000 tatsächliche
Pixel. Die vorhandene Vorschauüberschrift wird bei 680 Höhe teilweise abgeschnitten;
die ergänzten Transferaktionen und Hilfetexte bleiben vollständig erreichbar.
Keine neue Mindestgröße, Palette oder globale App-Leiste.

Die tatsächliche Installation enthält unabhängige Änderungen in `app.py` und
`lumen_notifications.py`. Im privaten Mischstand wurden nur die vorab per AST
verglichenen Funktionen `activate_files`/`main` und die drei Zeilen für `transfer:`
ergänzt; insbesondere der installierte `local-task:`-Benachrichtigungsweg bleibt
erhalten. Unabhängige Sicht-/Code-Abnahme, Integration und Installation stehen
noch aus. Der zuständige Installationsagent erhält Dateihashes und begrenzte
Patches; der Quellstand darf den installierten Mischstand nicht ersetzen.

Nicht geprüft: echtes NAS/SMB-Rebinding, Kernel-D-State, persönlicher Wayland-Desktop
oder Screenreader. Ein Timeout/unkündbarer Probe-Prozess und eine belegte Lease
werden gezielt simuliert; keine persönlichen Dateien oder realen Transfers benutzt.
