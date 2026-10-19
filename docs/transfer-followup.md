# Lumen Dranbleiben bei unterbrochenen Kopien

Auftrag: Entwurf „Dranbleiben“ als vollständigen Desktop-Weg umsetzen. Pro
gespeichertem Kopierauftrag lässt sich ausdrücklich auswählen, dass Lumen die
Verfügbarkeit erneut prüft und eine relevante Änderung meldet. Fortsetzen bleibt
eine ausdrückliche Aktion auf demselben Auftrag.

## Umfang und Abschlusskriterien

- [ ] Standardmäßig aus; Aktivieren, Aufschieben und Ausschalten pro Transfer.
- [ ] Nur unterbrochene native Kopien mit gespeichertem Kopierplan, einschließlich
  über das Dateisystem eingebundener SMB-Ziele. Keine neue Server-/Cloud-Freigabe.
- [ ] Bestehender Minuten-Timer, gespeicherter Backoff und Wiederanlauf ohne Files.
- [ ] Nur lesender Probe-Prozess mit Zeitlimit und exklusiver Lease; langsame oder
  hängende Ziele blockieren weder Oberfläche noch weitere Aufträge.
- [ ] Ursprüngliches Ziel, Quellen und Kopierzwischenablage erneut prüfen.
  Erreichbarkeit ersetzt keine Inhaltsprüfung; der vorhandene Kopierkern prüft
  die Teildaten beim ausdrücklich gestarteten Fortsetzen.
- [ ] Eine dauerhafte Meldung pro relevanter Zustandsänderung; keine Wiederholung
  bei unverändertem Zustand. Opt-out/Abbruch/Fortsetzen verhindert alte Ergebnisse.
- [ ] Meldung öffnet und markiert denselben Transfer in Lumen Files. Native
  Betriebssystemmeldungen enthalten weiterhin keine privaten Dateinamen/Pfade.
- [ ] Synthetischer Weg: Teilkopie → Ziel weg → wieder da → eine Meldung → manuell
  fortsetzen → bytegleiches Ergebnis; zusätzlich Ablehnung veränderter Bindungen,
  Zeitüberschreitung, Neustart, Aufschieben und Opt-out während einer Prüfung.
- [ ] Tatsächliche UI bei Graphit/Atelier, DE/EN, schmal/normal und Tastatur prüfen;
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

Umfang festgelegt. Implementierung, Prüfungen und Installation noch offen.
