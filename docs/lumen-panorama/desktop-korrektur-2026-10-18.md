# Panorama: Desktop-Korrektur nach Nutzerfeedback

Stand: 18.10.2026. Die frühere zusätzliche App-Leiste war eine falsche Interpretation. Desktop benötigt konsistente bestehende Ansichten und Menüs. Server-/Mobile-Laufzeiten werden durch diese Korrektur nicht verändert.

## Änderung

- Globale Desktop-App-Leiste samt Pythonmodul, acht exklusiven SVG-Kopien und Tests entfernt. Vorhandene App-Zugänge bleiben erhalten.
- Gemeinsame native Kopfzeile und Menügestaltung in `files/desktop_design.py`: Titel26px/500, Untertitel12px, Bedienung14px, Rand24px, Abschnitt16px. Notes, Projekte, Code und Audio Studio verwenden dieselbe Hierarchie; Files behält seine Dateitabs und erhält die passende Titelbehandlung.
- Abweichende Projekt-Heroschrift, Serifentitel, Code-Brandingstreifen und doppelte Projekt-Fontdateien entfernt. Bestehende Aktionen und Seiteneditoren bleiben erreichbar.
- Notes verwendet tatsächlich einen offline WebEngine-Editor. Dessen ursprüngliche Gestaltung wurde bereinigt: fast3.000 Zeilen allgemeiner Server-Stile und weitere ungenutzte Gedächtnis-/Navigation-/Layoutregeln entfallen. Keine zusätzliche `desktop.css` oder `panorama.css` über den alten Regeln. Dieselben gebündelten Schriftdateien wie Qt; keine neuen Pakete. Schmale Fenster behalten die Notizbearbeitung mit kompakter Navigation.
- Audio Studio behält beide Bibliotheken; die gemeinsame Einstellungsschaltfläche öffnet die Einstellungen des aktiven Bereichs. Die bisherigen Abbruch-/Speicherabläufe bleiben erhalten.
- Native C++Vault-UI: ausschließlich Schrift, Titel, Menüabstände und Seitenleistenbreite in `native/vault-ui/vault.cpp`. Broker, Kern, Consent, Policy, Sicherheitsflags und Daten-/Zugriffswege unverändert. Keine Übernahme des parallelen Vault-Sicherheitskandidaten.

## Prüfung

Echte Apps mit synthetischen Daten in temporären Profilen, privater D-Bus-Sitzung und offscreen Qt/Chromium: vier Themes bei1280×900. Vergleich der tatsächlich gerenderten Kopfzeilen, Schriftfamilien, Titelgewichte, Positionen, Höhen und Tastaturmenüs. Zusätzlich Notes960×800, Prüfung gegen überlappende Titel/Listen-/Tagtexte, Audio-Bereichswechsel und Erreichbarkeit der Einstellungen beider Bibliotheken.

84 Code-Tests, Notes-Webeditor3, Notes-Themes1, Projekte-Themes1, Gesprächsfokus2, Startisolation2, Werkzeuginstallation3 sowie der neue gemeinsame UI-Vertrag1 bestanden. Native C++Vault17 UI-Fälle einschließlich Passkey-, Sperr-, Sicherungs-, Clipboard- und Vierthemenfällen bestanden; keine Sicherheitszertifizierung daraus ableiten.

Vergleichsbilder, Logs und Installationsrückweg: `/home/example/.local/state/lumen/panorama-desktop-correction-20261018/`. Der persönliche Desktop und das iPhone sind keine Testgeräte; F585 bleibt bei der anderen Vault-Session. Keine persönlichen Apps werden beendet oder neu gestartet.

## Auslieferungsstand und Grenzen

Quellcode und isolierter visueller Vergleich sind abgeschlossen. Die lokale Installation wird im zugehörigen `installed/receipt.json` mit vorherigen/nachherigen Hashes belegt. Der ältere installierte Files-Code wird ausschließlich gezielt angepasst; keine fremden neuen Dateimanagerfunktionen werden untergeschoben. Rückweg verweigert das Überschreiben später veränderter Dateien.

Diese Prüfung umfasst die genannten Hauptansichten und betroffenen Bedienwege. Sie behauptet keine vollständige Abnahme jedes seltenen Dialogs, Aufnahmehardware, jeder Barrierefreiheitskombination oder aller Server-/Mobile-Ansichten.
