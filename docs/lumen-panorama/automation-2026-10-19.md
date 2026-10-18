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

Implementierungs- und Installationsnachweise werden nach Abschluss ergänzt. Diese Beschreibung allein ist kein Abnahmenachweis.
