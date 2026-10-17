# Lumen Code: vom Ziel zum geprüften Helfer

Freigegeben: Nutzer „Go“, 18.10.2026. Bestehende Apps, Entwürfe, Projekte,
Berechtigungen und Automationen bleiben erhalten. Kein Arbeitsraum-Modell.

## Module und Reihenfolge

| Schritt | Bedienung und Ergebnis | Bestehender Weg / Änderung |
| --- | --- | --- |
| 1 Ziel | „Rechnungen auf fehlende Angaben prüfen“ → begründeter Vorschlag Werkzeug; änderbar, noch keine Ausführung | CreationDialog / NewCreation, tools-freie KI-Vorschläge |
| 2 Probelauf | Beispieleingaben, Erwartung und tatsächliches Ergebnis prüfen, erneut verwenden | AppPreview / Preview und vorhandener tool-test; keine neue Ausführungsengine |
| 3 Daten | Ausgewählte Drive-Dokumente lesen, Ergebnis vor dem Anlegen einer Notes-Notiz prüfen | bestehende Quellen-/Dateirechte, Kontext und Notes-Belege; keine freien iframe-API-Aufrufe |
| 4 Versionen | Eine frühere App-Fassung als Entwurf laden, ausprobieren und nach Vergleich übernehmen | bestehender Entwurf/Commit mit Revisionsprüfung; begrenzter Verlauf |
| 5 Fehler | Schritt, Ergebnis und Fehler sehen; Reparatur als überprüfbaren Entwurf vorschlagen lassen | vorhandene Aufgaben-/Bausteinläufe, App-Änderungsweg |

## Abnahme

- Zieltext bleibt bei Zurück, Fehler und Artwechsel erhalten. Klassifikation durch
  eingerichtete KI, sprachunabhängig, strikt validierte Antwort, manuelle Auswahl
  auch bei ausgeschalteter KI. Keine Schlüsselwort-Router.
- Planungs-/Testaufrufe führen keine Ergebnisaktionen aus. Eingaben werden nur
  nach ausdrücklicher Auswahl an das konfigurierte Modell übergeben. Keine
  Passwörter, Dateieingabefelder oder versteckten Felder in gespeicherten Tests.
- Jeder Test zeigt, zu welcher Code-/Regelfassung er gehört; Änderungen machen
  den alten Befund sichtbar veraltet. Abbruch/Fehler erhalten den Entwurf.
- Quelldaten werden pro Nutzung mit aktuellen Kontorechten gelesen. Keine
  implicit-all-Dateiauswahl, kein Netzwerk-/Dateizugriff aus der App. Schreiben
  nur nach sichtbarer Prüfung, wiederholte Zustellung idempotent.
- Verlauf enthält App-Code und Metadaten, keine Laufzeiteingaben; Speicher ist
  begrenzt. Server-Inhalte folgen konfiguriertem App-Datenspeicher, kein stiller
  Ersatz auf der Systemdisk. Wiederherstellung ersetzt nicht sofort die App.
- Fehlerhilfe erweitert weder Rechte noch startet sie selbständig neue Aktionen.
- Funktions-/Fehler-/Rechte-/Konflikttests, echte Browser-/native synthetische
  Übergänge, DE/EN und schmale Darstellung prüfen. Persönliche Geräte bleiben
  Produktionsgeräte. Staging vor gezielter Installation/Promotion.

## Arbeitsstand

- [x] 1 Zielorientierter Einstieg Desktop / Server
- [x] 2 Wiederholbare Probeläufe
- [x] 3 Ausgewählte Lumen-Daten und geprüfte Ausgabe
- [x] 4 Begrenzter Versionsverlauf und Wiederherstellung als Entwurf
- [x] 5 Durchläufe und Reparaturvorschläge
- [ ] Regression, Staging, Veröffentlichung auf privatem Forgejo, Promotion

Mobile behält die sichere App-Nutzung. Neue native Bearbeitungsfunktionen werden
nur nach eigenem Simulatornachweis als vorhanden ausgewiesen.

## Konkrete Anschlüsse und Grenzen

- Server: `POST /api/code-library/creation-plan`, danach validierter Vorschlag
  über `GET /creation-plan/{task}`. `code_goal.py` und `code_app_checks.py`
  verwenden auf Desktop und Server denselben Vertrag. Keine Schlüsselwortfilter.
- Kleine Apps: `app-tests`, `app-versions` und `app-source` unter dem jeweiligen
  Sammlungseintrag. Quellen gehen nur über die Host-Oberfläche in gewählte
  Textfelder; kein API-/Datei-Zugriff aus dem iframe.
- Höchstens fünf Prüfbeispiele: gewöhnliche Formularwerte und sichtbarer
  Ergebnistext nach input/change. Keine beliebigen aufgezeichneten Klickfolgen;
  keine Aussage über die vollständige Korrektheit einer App.
- Zehn ersetzte App-Fassungen; Wiederherstellung benutzt den bestehenden
  Entwurf/Commit mit Revisionsprüfung. Neue Historie und Prüfbeispiele liegen
  serverseitig im konfigurierten App-Datenspeicher. Das bestehende Speicherformat
  der aktuellen Definition und des Entwurfs wurde nicht migriert.
- Serverquellen: freigegebene Notes sowie Drive-Text/Markdown/JSON/CSV und PDFs
  mit Textebene; pro App-Textfeld 20.000 Zeichen. Desktop nutzt ausdrücklich
  ausgewählte lokale/synchronisierte Dokumente. Native Notes-Übergabe samt
  Rückverweis auf die Code-App nutzt intern die bestehende Kompatibilitäts-ID
  `wissen.import`; die Oberfläche heißt Lumen Notes.
- Fehlerhilfe bereitet bearbeitbaren Text vor. Baustein-Reparaturen übernehmen
  keine Laufdaten, Pfade oder Zielrechte; Quellen/Ziele werden neu gewählt.
- Mobile bleibt beim Benutzen vorhandener Apps. Kein neuer nativer Mobile-Editor
  und keine neue TestFlight-Veröffentlichung durch diesen Schritt.

Eingebettete Desktop-App-Vorschauen benötigen das bereits optionale Qt WebEngine
(`qt6-webengine` im Arch-Paket). Es wurden keine neuen Bibliotheken eingebunden.
