# Lumen Automation: ein gemeinsamer Editor

Nutzerfreigabe: klickbarer Entwurf „Automation klar“, 19.10.2026. Desktop folgt
Panorama ohne zusätzliche App-Leiste. Erstellung und Bearbeitung verwenden
`SectionsEditor`: lesbare Abfolge links, genau ein ausgewählter Eintrag rechts.
Schmale Fenster ordnen die Einstellung unter der Abfolge an. Auslöser,
optionale Startbedingung und Aktionen bleiben getrennt. Untergeordnete Wege
und Wiederholungen bleiben sichtbar und bearbeitbar. Formulierungshilfen sind
sekundäre, ausdrücklich aufzurufende Vorschläge mit anschließender Prüfung.

Der bisher zusätzlich verwendete `code_blocks_editor.py` ist entfernt. Beide
gespeicherten Ausführungsformate verwenden dieselbe Oberfläche. Version 2
behält manuelle Starts, Kennungen, Reihenfolge, PDF-Sonst-Verhalten und bereits
gespeicherte Checkpoints. Version 3 behält Auslöser, Bedingungen, Wege und
Wiederholungen. Es gibt keine Datenmigration und keine stillschweigende
Umwandlung alter Abläufe. Auch Reparaturvorschläge behalten das Ausgangsformat.

Gespeicherte Einträge haben die Ansichten **Ablauf** und **Test & Ergebnis**.
Der zweite Bereich zeigt den letzten tatsächlichen Durchlauf mit Zuständen,
Ergebnissen und Freigabe-/Fortsetzungsaktionen. Frühere Ergebnisse bleiben
als zum früheren Entwurf gehörend gekennzeichnet. Vor einer neuen Aktivierung
muss ein erfolgreicher Test desselben gespeicherten Plans vorliegen. Eine
Bearbeitung pausiert einen aktiven Auslöser sofort. Speichern aktiviert nichts.
Der bestehende Hintergrunddienst, Rechteprüfungen und Freigaben bleiben erhalten.
Der jüngste Test dieses Plans zählt: offene/fehlgeschlagene Tests und ein
Durchlauf, der alle Aktionen überspringt, erlauben keine Aktivierung.

Wichtig: Der Produkt-Test ist keine Beispieldaten-Simulation wie im Entwurf.
Dateien werden tatsächlich gelesen; KI-Schritte nutzen nach Bestätigung den
eingerichteten Anbieter. Schreibaktionen bleiben beim Test im privaten
Testordner und erzeugen keine App-Einträge oder Benachrichtigungen. Nicht jeder
KI-Auftrag erkennt fehlende Belegdaten automatisch: dafür stehen die vorhandene
KI-Prüffrage und explizite Bedingungen/Wege zur Verfügung. Keine neuen
Home-Assistant-, Mail- oder Kalenderereignisse und keine neuen Drive-APIs.

Abnahmebelege und kontrollierter Installationsrückweg:
`~/.local/state/lumen/automation-unified-20261019/`.
Prüfung mit getrennten HOME-/XDG-/Lumen-Verzeichnissen, privatem D-Bus und
PID-/Mount-/Netz-Namensräumen; persönliche Apps werden nicht neu gestartet.
Server/Mobile und persönliche Automationen werden nicht verändert.

59 gezielte Quellprüfungen und 59 Prüfungen gegen installierte Module bestanden,
einschließlich echter privater Testausgaben, alter PDF-Wege, verschachtelter
Aktionen, wartender Freigaben, Wiederöffnen und Aktivierungsentzug. 24 native
Aufnahmen in vier Themes und drei Fenstergrößen stimmen Quelle/installiert
überein. Die breite Code-Suite hat einen unveränderten WebEngine-Fehler beim
Bereitwerden einer gesperrten Ressourcen-Vorschau; derselbe Fall scheitert auch
mit den unveränderten installierten Modulen. Keine Tests entfernt/übersprungen.
Ein anfänglicher Fixture-Pfadfehler des isolierten Prüfladers ist korrigiert.
Keine echten Anbieter-/Modelläufe und keine persönliche Hardwareabnahme.

Fünf Runtime-Dateien ersetzt, den alten separaten Editor entfernt; 633 andere
Codeassets und der Vault-Broker unverändert. Keine persönlichen Apps beendet.
Der kombinierte Rückweg ist an einer Wegwerf-Fixture mit nur sechs Code-Dateien
geprüft: zuerst `automation-unified-test-validation-20261019/install-desktop.py
rollback --apply`, danach `automation-unified-20261019/install-desktop.py rollback
--apply`. Erst anschließend ältere Code-/Panorama-Rückwege verwenden.
