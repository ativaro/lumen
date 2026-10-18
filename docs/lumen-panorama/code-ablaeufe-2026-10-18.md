# Lumen Code: die vier gewählten Abläufe

Die frühere Panorama-Korrektur hatte die gemeinsame Kopfzeile angeglichen, aber die vier fachlichen Wege weiterhin in einer Sammlungsnavigation und uneinheitlichen Detail-/Bearbeitungsformularen präsentiert. Dieser Schritt korrigiert die tatsächlichen nativen Ansichten und Übergänge.

## Verbindliche Entscheidungen und Befund

Abgeglichen mit den Nutzerentscheidungen im Chat „Lumen Code“: Werkzeuge „Eingabe und Ergebnis“, Code „Projekt zuerst“, danach kleine Apps vorerst durch Zeitpläne/Routinen ersetzen und Automation wie Home Assistant mit „Wenn / Und wenn / Dann“ und Klappblöcken. Die letzten konkreten Entwürfe liegen im Chat-Verzeichnis `2026/10/16/01a14388-18f2-7232-a9ea-e57a689ae422`: `lumen-neu-werkzeug-verfeinert.html`, `lumen-neu-code-verfeinert.html`, `lumen-zeitplaene-routinen-varianten.html` und `lumen-automation-ha-varianten.html`. Sie sind Designreferenzen mit simulierten Aktionen, keine Implementierungsnachweise.

| Weg | Bisherige Abweichung | Korrektur |
| --- | --- | --- |
| Werkzeug | Test unter dem scrollenden Formular; nach dem Öffnen generische Auftragsmaske. Im Editor änderte „Was soll das Werkzeug machen?“ lediglich die Beschreibung. | Eingabe/Ergebnis, wirksamer Auftrag und Regeln links; echter Beispieltest rechts. Benutzen zeigt neue Eingabe und Ergebnis. Bearbeiten liest und ändert denselben tatsächlichen Auftrag; optionale Beschreibung bleibt getrennt erhalten. |
| Routine | Anlegen öffnete sofort noch einen anderen Editor. Detailansicht bot eine Eingabe für den Durchlauf und einen generischen Auftrag an. | Schritte und Zeitplan nebeneinander; nach dem Anlegen verständliche Übersicht mit Start und Ergebnis. Quellen und Freigaben über den bestehenden Routine-/Zeitplaneditor ändern; kein zweiter unerwarteter Erstellungsdialog. |
| Automation | Neben der Liste standen weitere generische Navigations-/Reiterleisten. | Bestehende Wenn/Und-wenn/Dann-Liste in einem eigenen Editor. Formulierungshilfen direkt am betreffenden Abschnitt, mit Rückweg und ausdrücklicher Übernahme. Mehrere Wege, Bedingungen, Quellen und Prüf-/Fortsetzfunktionen bleiben erhalten. |
| Code | Sammlungsnavigation, allgemeiner Name vor dem Projekt, zusätzliche Ergebnisansicht im Programmiergespräch. | Projektquelle zuerst; Bezeichnung optional, andernfalls Ordnername. Danach echtes Projektgespräch als Hauptansicht, daneben Arbeitsschritte/Dateien/Änderungen/Prüfung. Generierte Dateien bleiben über die vorhandene Dateiansicht erreichbar; finale Antwort bleibt im Gespräch. |

Die Sammlung besitzt weiterhin ihre echte Bereichsnavigation. Ihre primäre Aktion heißt passend Werkzeug erstellen, Routine zusammenstellen, Automation erstellen oder Code-Projekt öffnen. Die Bearbeitungs-/Ablauffenster haben diese Navigation nicht mehr: Deren alte Einträge schlossen teilweise nur das Fenster. Bestehende kleine Apps bleiben nutzbar und heißen in der Liste „Bestehende Apps“; neue kleine Apps werden nicht angeboten.

## Code und Daten

Gemeinsamer nativer Editoraufbau in `code_design.py`, direkt verwendet von `code_creation.py`, `code_edit_window.py`, `code_blocks_window.py` und `code_session.py`. `code_creation_forms.py`, `code_sections_editor.py` und `code_library_window.py` stellen die vorhandenen Inhalte und Aktionen passend dar. Neue Texte stehen zusätzlich in `translations/en/code-panorama.json`.

Das erste gespeicherte Werkzeugregel-Element wird im Editor als tatsächlicher Auftrag angezeigt; weitere Regeln bleiben zusätzliche Regeln. Die Grenze bleibt acht Regeln insgesamt. Beim Speichern werden Reihenfolge und effektive Anweisungen korrekt zurückgeschrieben. Bestehende freie Aufträge bleiben beim bloßen Umbenennen unverändert. Beschreibung, Projektzuordnung, Werkzeugfassungen, Tests, Berechtigungen, Lauf-Checkpoints und vorhandene Daten werden nicht migriert oder gelöscht. Ein geänderter Auftrag wird erst nach der bisherigen ausdrücklichen Prüfung gespeichert.

Bei Routinen ist der Quellordner in der allgemeinen Metadatenansicht schreibgeschützt; Änderungen laufen über den vorhandenen Routineeditor mit Pause/Freigabe. Die Programmieransicht verwendet die bestehende Gesprächsoberfläche mit Gesprächsfokus und die vorhandenen Datei-/Git-Leser. Sie startet keinen neuen Auftrag beim Öffnen. Entwürfe, Sessions, Freigaben, Rückkehr zur Sammlung und eigene Code-Icons bleiben erhalten. Keine Änderungen an Startern, Notes-/System-Startschutz, Server oder Mobile.

## Abnahme

88 Code-Regressionstests, zwei Gesprächsfokus-Tests sowie der reale gemeinsame Kopfzeilen-/Menütest für Notes/Projekte/Code/Audio bestanden. Neue bzw. angepasste Fälle prüfen wirksamen Werkzeugauftrag versus Beschreibung, unveränderte freie Bestandsaufträge, Kontextwechsel mit erhaltenen Entwürfen, optionale Code-Bezeichnung, Projektöffnung erst nach Bestätigung, Routine ohne zweiten Dialog, richtige Routine-Quellrechte, Rückwege der Formulierungshilfe, Gesprächsfokus und weiter erreichbare generierte Dateien.

Echte Qt-Ansichten mit synthetischen Daten bei 1280×900 und 960×800: die vier Erstellungswege, Bearbeiten, Werkzeug-/Routinennutzung, Projektgespräch und Dateiansicht. 95 Aufnahmen über Graphit/Glas/Atelier/Mitternacht sowie eine zusätzliche englische Prüfrunde. Mit den gewählten Entwürfen auf gleiche Inhaltsarten und Hierarchie abgeglichen; keine neue globale App-Leiste. Persönliche Fenster sind keine Testziele. Alle Prüfungen verwenden explizite getrennte Lumen-/Tools-/XDG-Daten und privaten D-Bus.

## Fortbestehende Funktionsgrenzen

Dies ist keine neue Ausführungsengine. Baustein-Automationen starten weiterhin manuell; zeitgesteuerte Hintergrundausführung verwendet den Routinenweg. Eingefügte Nachrichten/Termindaten sind weiterhin keine automatischen Mail-/Kalenderereignisse. Die Projektquelle umfasst weiterhin Name/Notiz, nicht ungefragt alle Materialien. Die in älteren Studien gezeigten fertigen Kalender-/Projektaktionen wurden damit nicht zusätzlich angebunden. Alte v2-Abläufe und vorhandene kleine Apps behalten ihre kompatiblen Editorwege. Reale KI-/Dienstaufrufe, private SSH-Anmeldung, vollständige Screenreader-Abnahme und neue Server-/Mobile-Funktionen werden durch diese UI-Prüfung nicht behauptet.

Belege, Hashmanifest, frühere Runtime-Dateien, Prüfprotokolle und Rückweg: `~/.local/state/lumen/code-panorama-20261018/`. Installation nur der acht betroffenen Python-Module und der Übersetzungsdatei; geöffnete persönliche Apps werden nicht automatisch beendet oder neu gestartet.

## Installierter Nachweis

UI-/Funktionspin `d4861f17b36d9253de07d2dc4a30a70a505feb93`: neun Dateien nach Prüfung gegen den bisherigen Stand atomar übernommen. 626 andere Codeassets und der Vault-Broker sind unverändert. Alle 91 Prüfungen bestehen auch gegen die installierten Produktionsmodule. Die 95 installierten Qt-Aufnahmen stimmen bytegleich mit dem geprüften Quellstand überein. Ein anfänglicher Fehler im installierten Teststarter betraf ausschließlich den nicht geladenen Testhelfer `test_code_flow`; der Helfer wird nun ausdrücklich aus der Testquelle geladen. Produktionsimporte bleiben nachweislich aus der installierten Runtime. Der erste Fehlerbericht bleibt im Belegverzeichnis erhalten.

Der Rückweg ist auf Hash-/Driftkonsistenz geprüft: `python ~/.local/state/lumen/code-panorama-20261018/install-desktop.py rollback` prüft, `rollback --apply` nimmt ausschließlich diese neun Dateien zurück. Vorherige Dateien und Rechte sind gesichert; persönliche Daten, Sitzungen und laufende Fenster werden damit nicht zurückgesetzt. Diesen neuesten Code-Stand vor älteren Audio-/Desktop-Rückwegen zurücknehmen. Bereits geöffnete Code-Fenster benötigen normales Schließen und erneutes Öffnen.
