> **Historischer Entwurf oder Abnahmebeleg – keine aktuelle Installationsanleitung.** Diese datierte Abnahme gehört zum damaligen Kandidaten. Enthaltene lokale Notes-/Projekt-/Code-/Audio-Editoren sind inzwischen durch Server-Apps ersetzt; nur die Gestaltungsentscheidung bleibt als Referenz bestehen. Aktuelle Zuordnung: [Desktop-Verantwortlichkeiten](../desktop-retirement.md).

# Routinen und Automation: drei durchgängige Desktop-Abläufe

Nutzerziel: sowohl Bedienung als auch Funktionsumfang verbessern. Alle drei konkretisierten Wege gehören zum Umfang: neue/geänderte Datei → prüfen → ablegen; Zeitplan → Quelle lesen → Zusammenfassung; Lumen-Ereignis → Bedingung → Aktion. Der erste echte App-Auslöser ist die Änderung eines ausgewählten Projekts. Keine allgemeine Mail-/Kalenderanbindung daraus ableiten.

## Vertrag

Die bestehenden v3-Bausteine, Bedingungen, Verzweigungen und haltbaren Lauf-Checkpoints bleiben die Ausführung. Der erste Eingabebaustein erhält optional eine geprüfte `trigger`-Konfiguration: `clock`, `directory` oder `project`. Bestehende manuelle Pläne und v1-Routinen werden nicht migriert. Neue Auslöser sind standardmäßig aus. Aktivierung prüft den gesamten Plan, Quellen und Ziele; jede Planänderung oder Archivierung entzieht die alte Freigabe. Wiederverwendbare Vorlagen enthalten weiterhin keine lokalen Quellen oder Aktivierung.

Der vorhandene Benutzertimer prüft die freigegebenen Auslöser. Pro Ablauf läuft höchstens ein unbearbeiteter Durchlauf; offene Bestätigungen/Fehler halten weitere Starts an. Zeitpläne holen höchstens einen verpassten Start nach. Ordnerauslöser betrachten reguläre, nicht versteckte Dateien direkt im ausgewählten Ordner bis 20 MiB, ohne Rekursion/Symlinks; vorhandene Dateien werden bei Aktivierung als Ausgangsstand erfasst. Neue/geänderte Dateien brauchen zwei unveränderte Prüfungen. Ordneridentität und Dateifassung werden vor/bei dem Lesen geprüft. Ergebnisse im Eingangsordner und Rückschreiben in das auslösende Projekt werden bei Aktivierung abgelehnt, damit keine unmittelbare Selbstschleife entsteht.

Projektquellen unterstützen die aktuellen Projekte aus der `workbench`-Bibliothek einschließlich Vorhaben-/Aufgabenmetadaten. Historische verknüpfte Projektidentitäten bleiben kompatibel. Es werden keine angehefteten Dokumentinhalte oder Weblinks ungefragt geöffnet. Die vorhandene technische `room`-Speicherform ist nur eine Kompatibilitätsstelle, kein Produkt-Arbeitsraum.

Hintergrundläufe verwenden denselben Schritt-Runner. KI-Schritte senden ausschließlich den sichtbaren Auftrag und die bis dahin gelesenen Daten über den eingerichteten Anbieter, ohne Werkzeuge. Ein Bestätigungsbaustein wird niemals automatisch bestätigt. Lauf-/Auslöserpause, Versionsänderung und geändertes Notes-Ziel verhindern weitere Aktionen. Testläufe schreiben weiterhin ausschließlich in den privaten Testbereich.

## Abnahmeziele

- Alle drei Wege vom Erstellen bis zum tatsächlichen Ergebnis prüfen; kein Fenster für die Ausführung erforderlich.
- Gleiche Zeitplanauswahl beim Anlegen und Bearbeiten, Vorschau der nächsten Starts, ausdrücklich benannter Quellen-/Zielzugriff.
- Bausteinüberschriften nennen Auftrag/Ziel auch zugeklappt; Teststatus zeigt tatsächliche Eingabe, Ergebnis und Gründe für übersprungene Wege.
- Isolierte Profile mit beiden Lumen-Datenpfaden und privatem D-Bus, reale Qt-Ansichten in vier Themes und schmaler Ansicht, bestehende Code-/Timer-Regressionen.
- Installation erst nach Prüfung, ausschließlich betroffene Runtime-Dateien mit Hashprüfung/Rückweg. Keine persönlichen Apps als Testziel; keine Produktionsroutine durch den Agenten aktivieren.

## Umsetzung und Grenzen

Neue Routinen verwenden ebenfalls v3, mit eigener linearer Ansicht: Schritte links, Start/Zeitplan/Quelle rechts. Jeder KI-Schritt hat seinen eigenen Aufruf und eigenen Checkpoint; Aktionen sind echte Bausteine. Der Definitionswert `editor=routine` hält sie in der Sammlung unter Routinen und verhindert Verzweigungen in diesem einfacheren Weg. Automation behält Wenn/Und wenn/Dann und Verzweigungen. Die alte doppelte Routine-Erstellungsmaske wurde entfernt. Bestehende v1-Routinen behalten unverändert ihren kompatiblen Editor und ihre bisherigen Ausführungsgrenzen; keine stille Migration.

Ein gemeinsamer Zeitplanbaustein ersetzt die frühere Kopie im alten Bearbeitungsdialog. Der nächste Start ist sichtbar, weitere Starts über den Hinweistext zugänglich. Aktionstitel nennen Notes, Inbox beziehungsweise Projektnotiz ausdrücklich. Neue Abläufe sind nach dem Speichern pausiert. Nur der ausdrückliche Aktivierungsdialog startet den vorhandenen Benutzertimer; dessen Fehler pausiert den Auslöser wieder. Der Agent aktiviert keine persönliche Routine und startet keine persönliche App neu.

Hintergrund-KI ist an den eingerichteten Anbieter gebunden. Die Abnahme nutzt eine synthetische asynchrone Modellantwort; keine echten Modell-/Cloudaufrufe. Projektänderungen umfassen die ausgewählte Projektübersicht/Vorhaben/Aufgaben, keine allgemeinen Mail-/Kalenderereignisse. Ordner werden ungefähr minütlich geprüft; stabiler Eingang benötigt zwei Prüfungen. Ohne laufenden Rechner/Benutzertimer erfolgt keine Ausführung. Das ist keine Ausführung auf Lumen Server/Mobile.

Neue Triggerpläne und die Routine-Editorzuordnung bleiben bei einem Code-Rollback als Daten erhalten, benötigen zum Öffnen aber den neuen Code. Keine Tabellen oder Nutzerdaten werden für einen Rollback gelöscht.

## Abnahme

105 Code-Prüfungen, der gemeinsame reale App-Kopfzeilentest, zwei Gesprächsfokus-Prüfungen und der gezielte bestehende Timer-/Wiederanlauftest: 109 eindeutige Prüfungen. Darunter echte Datei-Ausgabe ohne Fenster, Projektänderung aus der aktuellen Projektbibliothek, Stabilität/Deduplizierung/Einmalstart, getrennte KI-Schritte mit synthetischer Antwort, Quellen-/Notes-Zielwechsel, Timerfehler, explizite Aktivierung, Bestätigungswartepunkt, Read-only-Projekt und bestehende v1-Datenwege. Auch „Routine aus Werkzeug“ verwendet denselben neuen Weg und eine eingefrorene Kopie der Werkzeuganweisung. Zugeklappte Vorschauen bleiben nach Bearbeiten aktuell.

Ein zusätzlich versuchter alter gesamter `test_lumen_os.py` ist nicht grün: Vision-Launcher-Ausgabevertrag und die inzwischen überholte Annahme eines eingebetteten Files-Fensters scheitern. Die von diesem Fall gestarteten zwei isolierten System-/Settings-Unterprozesse wurden nach Profilprüfung exakt per PIDFD beendet; kein persönliches Datenprofil. Fehlprotokoll und Prozessnachweis bleiben erhalten. Den breiten alten Integrationsfall nicht als Abnahme zählen und nicht unkontrolliert wiederholen. Der gezielte Timer-Fall besteht separat.

Echte native Qt-Aufnahmen prüfen alle drei Wege bei 1280×900 und 960×800 sowie die gespeicherte Routine in Graphit/Glas/Atelier/Mitternacht. Befunde: Routine zeigt alle Schritte vorrangig links; Quelle und nächster Start rechts. Automation behält die gewählten Abschnittsüberschriften. Schmale Ansichten scrollen vertikal; wesentliche Aktionen bleiben im festen Fußbereich. Keine zusätzliche globale App-Leiste.

## Installierter Nachweis

Codepin `cb0358480d9ed2ecba6b560277096c1a9eeb545b`: genau 17 Runtime-Dateien nach Hashvergleich mit der vorherigen Fassung übernommen. 622 andere Codeassets und der Vault-Broker bleiben beim Installieren bytegleich. 109 gezielte Prüfungen bestehen auch gegen die installierten Produktionsmodule. 28 native Qt-Aufnahmen Quelle/installiert stimmen bytegleich überein; keine persönlichen Fenster neu gestartet. Belege: `~/.local/state/lumen/schedule-automation-20261019/verification.json`.

Der geprüfte Rückweg `install-desktop.py rollback` prüft, `rollback --apply` nimmt ausschließlich diese Dateien zurück. Private Vorher-Dateien und Rechte liegen im dortigen `installed/`-Verzeichnis. Diesen Stand vor älteren Code-/Audio-/Desktop-Rückwegen zurücknehmen; Nutzerdaten und neue Triggerdefinitionen werden nicht gelöscht. Ein geöffnetes Code-Fenster lädt die neue Version erst nach normalem Schließen und Öffnen.

Der separate native Alt-Integrationstest stubbt nun ausdrücklich seine externen App-Routen, statt beim Prüfen eingebetteter Seiten echte abgekoppelte Programme zu öffnen. Eine gezielte absichtlich ausgelöste Assertionsstörung prüft das bei gesperrtem `QProcess.startDetached`; sie besteht und verändert keine Laufzeitdatei. Die beiden alten fachlichen Fehlschläge bleiben bestehen und werden dadurch nicht zu bestanden umgedeutet. Keine neue vollständige OS-/Launcher- oder Notes-Abnahme daraus ableiten.
