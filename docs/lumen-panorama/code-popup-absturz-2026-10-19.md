# Lumen Code: Absturz bei der Auslöserauswahl

Am 19.10.2026 gezielt installiert. Genau eine Laufzeitdatei geändert: files/code_sections_editor.py, 49254 Bytes, SHA-256 e46c6a9a57f0ef368a88a752277c930a12e51096400728d379bc083aea3a63be, Modus0644. Freigegebener Pin a45d20f3144094335f86da2a195644e1041b1829 auf f925818e2704f30bd07553529860fd7a4555b0af; kanonischer Integrationscommit eb384b4ef434807d80b2b7b393e8c690c75ce2fd. test_code_popup_lifetime.py ist ausschließlich Source/Prüfung, nicht mitinstalliert.

## Ursache und Korrektur

Beim Anlegen einer Automation und Auswählen eines Zeit-Auslösers wurde synchron der Formularinhalt ersetzt. QScrollArea.setWidget löschte dabei den bisherigen Inhalt samt QComboBox, während deren Popup noch das Mausauswahlsignal verarbeitete. Der private Ausgangsstand stürzte in vier Popupfällen ab; die Qt-Frames stimmen mit den beiden realen SIGSEGV-Berichten überein. Eine native PlanDialog-Kontrolle blieb grün. Die Eingabequellenauswahl wurde zusätzlich unabhängig bei vorkonfigurierter Uhr geprüft und reproduzierte ebenfalls den Fehler.

Alle drei Inhaltswechsel des bestehenden Editors nutzen nun dieselbe minimale Ablösung: bisherigen Inhalt mit takeWidget herausnehmen, ausblenden, per deleteLater nach Rückkehr in die Ereignisverarbeitung freigeben, dann neuen Inhalt einsetzen. Modelländerungen und Validierung bleiben synchron. Keine neue Warteschlange, Abhängigkeit, Gestaltung, Rechteänderung oder Timeraktivierung.

## Prüfung und Gestaltung

108 eindeutige betroffene Fälle gegen einen begrenzten tatsächlichen Runtime-Kandidaten und dieselben108 gegen installierte Module bestanden. Die sechs endgültigen Popupfälle liefen zusätzlich separat grün; sie sind in108 enthalten und erhöhen die Zahl nicht auf114. Owner-/Overlay-/Installed-IDmengen geprüft, Testfixtures vom freigegebenen Pin unverändert. Der private Prüfaufbau gibt den Popup-Unterprozessen /source/files als Python-Suchpfad, da die Fixtures getrennt von Produktmodulen liegen.

Echte Qt-Mausauswahl prüft genau ein activated-Signal, gültigen Sender während des Rückrufs und geschlossenes Popup. Wiederholte Auslöserwahl, unabhängige Eingabequelle, Routine-Auslöser und Aktion hinzufügen sowie verzögerte tatsächliche Widgetfreigabe sind abgedeckt. Daily09:15 bleibt nach Übernehmen, Speichern und erneutem Öffnen erhalten. Abbrechen verändert weder gespeicherten Eintrag noch ursprünglichen Plan; keine Workflowaktivierung.

Die tatsächlichen installierten Graphit-Ansichten (Zeitdialog720×600, Routine960×800) wurden geöffnet und mit den freigegebenen Sourcebildern verglichen: beide bytegleich. Vier Source-Vorher-/Nachherpaare (GraphitDE100 und AtelierEN125) waren bereits bytegleich und durch Root visuell angenommen. Keine UI-Änderung gebündelt. Der alte Kontrastfehler des ausgewählten Texts in der rohen Routine-Komponente bleibt unverändert; er wurde getrennt an den zuständigen Code-Chat gemeldet.

## Installation, Belege und Rückweg

Frische Zielhash-/Dateimodus-/Mischstandsprüfung, vollständige private Ein-Dateien-Installation und Rücknahme sowie installierter Rückweg-Dryrun bestanden. 648 andere Codeassets und Vault-Broker unverändert. Bekannte Mischstände app.py, setup_dialog.py und tools_data.py erhalten; parallele Fenstersteuerungsarbeiten nicht überschrieben. Alle eigenen Qt-Prüfungen mit privaten HOME/XDG/Lumen-Pfaden, D-Bus und PID/Mount/Netz-Namensräumen, Core-Dateien deaktiviert, keine verbliebenen Namespaceprozesse.

Belege: ~/.local/state/lumen/code-trigger-sigsegv-install-20261019/{verification.json,test-id-audit.json,manifest.json,installed/receipt.json,rollback-selfcheck.json,installed-clock-graphite/}. Source-/Sichtfreigabe und ursprüngliche Crashbelege liegen daneben in code-time-trigger-crash-20261019/. Für Baselinebehauptungen ausschließlich before-popup-crashes2 und before-source-popup verwenden. Der später before-final-popup-regressions genannte Lauf benutzte schon den Fix und gilt ausdrücklich nicht als Ausgangsbeleg.

Rückweg im Installationsbelegverzeichnis: zuerst python3 install-desktop.py rollback prüfen, dann bei gewünschter Rücknahme python3 install-desktop.py rollback --apply. Fremde zwischenzeitliche Zieländerungen werden verweigert; neuere aufbauende Installationen zuerst zurücknehmen. Sicherungen, Originalpins, Logs und Bilder bleiben erhalten.

Keine persönlichen Fenster neu gestartet, keine persönlichen Daten, echten Timer oder Modelle benutzt; kein Push oder Server-/Mobile-Deployment. Bereits geladene Lumen-Code-Fenster erhalten den Fix nach regulärem Schließen und erneutem Öffnen. Keine zusätzliche Wayland-/Compositor-/Hardware-/Screenreader-, WebEngine- oder Sicherheitsgesamtabnahme.
