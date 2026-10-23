> **Datierter Abnahmebeleg.** Quellpin, Screenshots und Laufzahlen gelten für den beschriebenen Kandidaten. Sie sind keine Prüfung einer heutigen Installation. Für aktuelle App-Zuständigkeiten gilt [Desktop-Verantwortlichkeiten](../desktop-retirement.md), für weitere Gestaltung [Panorama](standard.md).

# Lumen Compose und Reader: Abstand und kompakte Lektüre

UI-Kandidat auf Basis `29d08e3b1c438952be706ddac5e71d28640a4236`.
Keine eigene Installation oder Veröffentlichung. Die bestehende
[Panorama-Vorgabe](standard.md) bleibt verbindlich.

Compose verwendet im vorhandenen Text-Splitter `PAGE_SPACING` (16). Original
und Ergebnis erhalten damit Abstand; beide Editoren bleiben per Splitter
vergrößerbar. Der Griff ist transparent statt einer breiten Trennleiste.
Übersetzungs-, PDF-, Zwischenablage- und Providerwege bleiben unverändert.

Reader verwendet seinen vorhandenen Lesemodus für aktive Lektüre unter
1000 logischen Einheiten Fensterbreite. Bibliothek und Randnotizen werden
ausgeblendet; der gleiche bestehende Knopf heißt dann ausdrücklich
„Bibliothek und Gedanken anzeigen“. Er zeigt beide Bereiche wieder an.
Beim automatischen Wechsel zurück zum breiten Fenster wird die vorherige
Sichtbarkeit wiederhergestellt. Eine manuelle Umschaltung hat Vorrang.

Es werden keine Widgets oder Notizen neu aufgebaut und keine Einstellungen
gespeichert. Leere/deaktivierte Lektüre behält die Buchauswahl in der
Bibliothek. Der in Files eingebettete Reader wird nicht automatisch
umgeschaltet; dessen vorhandene Hostnavigation bleibt zuständig.

Vier kleine native Prüfungen bestätigen Editorabstand/erreichbare Hauptaktion,
Lesemodus und Rückweg mit unverändertem Randnotiztext, manuelle Auswahl und
automatische Wiederherstellung, erreichbare leere Bibliothek sowie unveränderte
eingebettete Navigation. Die ersten beiden Layoutprüfungen schlugen auf der
unveränderten Basis fehl. Kein neues Testframework und keine erneuten
111-Code-Fälle.

Echte unveränderte Qt-Bilder mit identischen synthetischen Texten vor/nach:
960×640 und 1280×800, Glas/DE und Graphit/EN; zusätzlich Livewechsel auf Atelier
sowie die längste bestehende Compose-Aktion. Reader-Lesefläche im kompakten
deutschen Vergleich: 363 auf 912 logische Einheiten. Im fokussierten Zustand
entfällt der linke Bibliotheks-Innenabstand; außen bleiben beidseits 24 Einheiten.
Beim Zurückschalten wird der bisherige innere Abstand von 16 wiederhergestellt.
Der Seitenbereich-Rückweg
wurde zusätzlich sichtbar aufgenommen. Keine kritische Aktionskürzung in diesen
Szenen. Die gemeinsame Shell/Bibliotheksbreite ist weiterhin Generals Bereich.

Alle Daten liegen in privaten temporären HOME-/Lumen-/Tools-/XDG-Pfaden;
privater D-Bus und getrennte PID-/Netzräume. Keine persönlichen Fenster
gestartet/beendet. Reader-Inhalt wurde direkt im vorhandenen Textwidget
synthetisch gesetzt; kein Dokumentimport oder PDF-/EPUB-Renderer-Test.
Compose-Ausgabe ist synthetisch; keine Übersetzung, LLM-, Vorlese-, Clipboard-
oder Dateiaktion ausgelöst. Datenformate und Ausführungsrechte unverändert.

Belege, Quellpin, Vorher-/Nachherbilder und genaue Größen:
`~/.local/state/lumen/compose-reader-ui-20261019/`.
Root prüft die Bilder, General integriert danach den konkreten Kandidaten.
