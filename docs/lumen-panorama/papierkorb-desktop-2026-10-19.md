> **Datierter Abnahmebeleg.** Quellpin, Screenshots und Laufzahlen gelten für den beschriebenen Kandidaten. Sie sind keine Prüfung einer heutigen Installation. Für aktuelle App-Zuständigkeiten gilt [Desktop-Verantwortlichkeiten](../desktop-retirement.md), für weitere Gestaltung [Panorama](standard.md).

# Lumen Desktop: Papierkorb mit Wiederherstellen

Installiert und gezielt geprüft am 19.10.2026. Bestehende Archivierung wird als Papierkorb zugänglich, ohne neue Datenbankstruktur, Hard-Delete-API oder Abhängigkeit.

## Bedienung und Datenerhalt

Lumen Code & Automation: Sammlungseinträge über Auswahl, Kontextmenü oder Entf-Taste in den Papierkorb verschieben. Spezialisierte Detailansichten nutzen dieselbe Bestätigung. Der Bereich Papierkorb bietet Wiederherstellen. Ein geöffnetes Code-Projekt muss über seinen regulären Entwurfs-/Schließweg zu den Sammlungsdetails zurückkehren; kein unsichtbares Schließen oder Abbrechen.

Lumen Projekte: Projekte, Vorhaben und Aufgaben über ihre direkten Aktionen entfernen und wiederherstellen. Untergeordnete Elemente bleiben zugeordnet; zuerst den entfernten übergeordneten Eintrag wiederherstellen. Bei Materialien und Ablaufverknüpfungen entfernt Zuordnung entfernen ausschließlich den Bezug zum Projekt.

Originaldateien und Projektverzeichnisse, Definitionen, Versionen, bisherige Ergebnisse, IDs und Rechte bleiben erhalten. Automatische Starts werden pausiert; Wiederherstellen aktiviert sie nicht. Aktive Vorgänge und aktivierte oder laufende verknüpfte native Abläufe blockieren das Entfernen verständlich. Diese Prüfung liest den nativen Zustand, verändert aber weder Ablauf noch laufenden Auftrag. Abbrechen, veraltete Revisionen, Leserechte und ungespeicherte Änderungen dürfen keine Teiländerung auslösen. Code speichert und archiviert einen geänderten Eintrag atomar.

## Umfang und Quelle

Freigegebene Pins: Code `b94be257205e84137380e13aab74f962b43c0a14`; Projekte `d66d57ccbd296b9909eaa323bfa6cb39213a32fc` plus `037c974f38c37aee9537bb56014c77b2a3297e6c`. Kanonische Integrationen: `9b6aeb8875bc50badd278dd7b0858df927d63d1b`, `b5db09d23a8fe30bc67c3c448f396fe30d09a685`, `dcc5453b4ac4542e8a882e25585c3cb8dd4df565`.

13 Laufzeitdateien / 215393 Bytes: code_blocks_window.py, code_library.py, code_library_window.py, code_session.py, code_trash.py, translations/en/code-trash.json; project_editor.py, projects_home.py, projects_journal_ui.py, projects_overview.py, projects_trash.py, tools_workbench.py, translations/en/projects-trash.json. Alle unter files/. Keine Änderung an tools_data.py; bekannte Mischstände in app.py und setup_dialog.py bleiben ebenfalls erhalten.

## Nachweise

183 eindeutige Fälle gegen denselben kombinierten tatsächlichen Runtime-Stand und anschließend dieselben 183 gegen installierte Module: Code116 einschließlich drei unabhängiger Zusatzproben, Projekte67. Getrennte private Profile für die bestehenden Code- und Projektprüfungen; Projektprüfungen nutzen den nativen Notes-Fallback. Nur Quellwurzel-Lookups dreier ausgelagerter Testfixtures wurden auf /source abgebildet, ihre Assertions blieben unverändert. Für den bestehenden MCP-Setupcheck wurden sechs vorhandene statische Assets aus der Runtime übernommen.

Echte installierte Graphit-Ansichten (Code960×800, Projekte960×720) und das Projekt-Wiederherstellen-Menü geöffnet und mit den freigegebenen gleich großen Quellbildern verglichen. Geometrie, Typografie, Navigation und Aktionen stimmen überein. Code zeigt zusätzlich den normalen Tastaturfokus und Entfernen-Hinweis; Projektzeitstempel unterscheiden sich. Beide Wiederherstellen-Aktionen zusätzlich im privaten UI-Profil ausgeführt; Originale erhalten. Quellbilder stammen ehrlich von Code62cb0f0 / Projektd66; die freigegebenen Folgepins ändern ausschließlich Logik. Installierte Bilder verwenden die finalen13 Payloads.

Exakte Hashes/Dateimodi, 636 übrige Codeassets und unveränderter Vault-Broker geprüft. Vollständige 13-Dateien-Installation und Rücknahme auf begrenzter Wegwerfkopie bestanden; installierter Rückweg zusätzlich ohne Ausführung geprüft. Keine persönlichen Fenster, Panels oder KWin neu gestartet; kein Push, Server-/Mobile-Deployment oder Test mit persönlichem Profil.

Belege: ~/.local/state/lumen/desktop-trash-install-20261019/verification.json, test-id-audit.json, manifest.json, installed/receipt.json, combined-rollback-selfcheck.json und installed-trash-views-captures/. Root-Quell-/Sichtfreigabe: ../desktop-trash-20261019/root-source-visual-acceptance.json. Quellbilder, Originalpins und Rückwegsicherungen bleiben erhalten.

## Rückweg und Grenzen

Im Belegverzeichnis zuerst `python3 install-desktop.py rollback`, danach bei gewünschter Rücknahme `python3 install-desktop.py rollback --apply`. Der Installer verweigert inzwischen fremd geänderte Zieldateien und ersetzt keine übrigen Dateien. Neuere aufbauende Installationen zuerst zurücknehmen; bereits gestartete persönliche Apps regulär schließen und wieder öffnen.

Ein isolierter WebEngine-Vorschau-Readiness-Test scheitert bereits auf dem Ausgangsstand identisch; er gehört nicht zu den akzeptierten116 Codefällen und gilt nicht als behoben. Keine neue vollständige Betriebssystem-, Hardware-, Screenreader-, Modell- oder Sicherheitsabnahme.

Technische Arbeitsraumreste ausdrücklich nicht als Produktmodell eingeführt: tools_workbench.open_section(rooms) bleibt ein alter Verweisalias, code_blocks_run.py behält historische settings/.../room/-Referenzen zum Erhalt bestehender Daten-/Rechtebezüge. Keine neue globale Arbeitsraum-Auswahl oder Migration.
