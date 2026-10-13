# Lumen Werkbank

Die Desktop-Werkbank verbindet das Gespräch mit der aktuellen Antwort und
ausdrücklich bereitgestellten Dateien. Auf breiten Fenstern stehen beide Bereiche
nebeneinander; in schmalen Fenstern wechselt die Ergebnistaste zur Vorschau und
deren Schließen-Taste zurück zum Gespräch. Anhänge und Dateipfade im Antworttext
werden nicht automatisch geöffnet. Antworten bleiben inert gerendertes Markdown.

Speichern verwendet die vorhandenen Wege für persönliche Notizen, Wissen und
Dateiaktionen. Die Auftragsübersicht verwendet den bestehenden Store und Tracker;
Freigaben, Wiederaufnahme und Rücknahme bleiben deren Verantwortung.

Akzeptanz: Gesprächsentwürfe und Sitzungsidentitäten bleiben erhalten. Aufträge
sind durchsuchbar und nach Zustand gruppiert; Ergebnis und passende Steuerung
stehen im Detailbereich, Ausführungsdetails sind aufklappbar. Laufende lokale
KI-Aufträge werden durch den Tracker pausiert, native Abläufe an Schrittgrenzen.
Ein Gesprächslink öffnet nur die gespeicherte Sitzung, ohne einen Auftrag zu starten.

Erfolgreiche Durchläufe hinterlegen im bestehenden Ereignisverlauf
`conversation_turn` mit Sitzung und Anfrage-ID. Ergebnisaktionen verwenden diese
Identitäten, auch wenn mehrere Werkzeugrunden Antworttexte geliefert haben oder
zwei Aufträge denselben Text zurückgeben. Wiederherstellung behält diese IDs.
Ältere Aufträge ohne diese Verknüpfung bleiben in der Auftragsübersicht nutzbar;
aus Textgleichheit wird keine Zuordnung geraten. Das rechte Speichermenü verwendet
ausschließlich die rechte Auswahl oder die aktuelle Antwort. Export als Datei
verwendet das vollständige gespeicherte Auftragsergebnis, einschließlich
etwaiger Antworttexte früherer Werkzeugrunden desselben Durchlaufs.

Die Übersicht zeigt Pause nur für unterstützte lokale Ausführung. Serveraufträge
verwenden weiterhin deren Abbruchfunktion. Ein unabhängiger nativer Ablauf kann
auch während eines laufenden KI-Gesprächs gestartet werden. Ein fremdes Gespräch
lässt sich erst öffnen, wenn der aktuelle Entwurf, Anhänge und laufende Arbeit
abgeschlossen sind; ein Link zum bereits offenen Gespräch lässt diese unberührt.

Implementierung isoliert ab `2ac3447` auf `feature/desktop-workbench`. Parallel
bearbeitet der Gesprächs-Agent Backend und Gedächtnis; hier entstehen weder neue
Gedächtnisabrufe noch Server-Schemata. Die spätere lokale Installation vom 08.10.2026 ist in
`desktop-workbench-installation.md` dokumentiert.

Prüfung: `QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s files -v`.
Native Studio-Tests verwenden private Einstellungen und einen temporären Store.

## Prüfstand vom 08.10.2026

- 31 gezielte Tests bestehen: `test_studio`, `test_assistant`, `test_desktop`,
  `test_file_actions`, `test_studio_results`, `test_lumen_os.LumenIntegrationTest`.
  Darunter echte native Dateischritte über den Auftragsknopf, Datei-Export,
  Pausieren/Fortsetzen, fremde Entwürfe, identische Antworttexte unterschiedlicher
  Durchläufe, rechte Textauswahl, Wiederherstellung und D-Bus-Aktivierung.
- Die Ablauf-Fixture deaktiviert Aktivitätspausen ausschließlich in ihrem privaten
  Test-Store. Ein auf dem Rechner laufendes Steam-Spiel blockierte zuvor diesen
  UI-Test; die Produktvoreinstellung wurde nicht verändert.
- Gesamtlauf auf privatem D-Bus: 612 Tests, 6 Failures, 10 Errors, 4 Skips.
  Der separat entpackte Ausgangsstand `2ac3447` hat bei demselben Lauf 607 Tests,
  6 Failures, 11 Errors, 4 Skips. Kein neu fehlgeschlagener Test; die korrigierte
  Ablauf-Fixture besteht zusätzlich. Die Suite ist weiterhin nicht insgesamt grün.
- Bestehende Fehler: Plasma-Aufruf auf privatem D-Bus, Crash-Recovery-Timeouts,
  mehrfache QApplication-Erzeugung, fehlende lokale Stimme, Vision-Fixture,
  Systemintegrations-Fixture, Katalogkonflikte/fehlende ältere Übersetzungen sowie
  Reihenfolgeeffekte bei Galerie und Mausnavigation. Diese wurden nicht verdeckt.
- Neue UI-Texte haben englische Einträge; geänderte Python-Dateien kompilieren,
  `git diff --check` ist sauber. Native Ansichten wurden mit Graphit und Atelier,
  Deutsch und Englisch sowie bei 1480 × 900 und 760 × 600 geprüft. Kleine Fenster
  wechseln zwischen Gespräch und Ergebnis; lange Auftragsdetails sind scrollbar.
- Unabhängiger statischer Review: APPROVED nach Korrektur der zwei Befunde zu
  Durchlaufidentität und rechter Auswahl. Keine neuen Freigabe- oder Speicherwege.
- Git-Probezusammenführung mit dem separaten Gedächtnisstand `12ab5d1` ist
  konfliktfrei. Das ist keine gemeinsame Laufzeitabnahme. Keine Installation.

Lokale Prüfprotokolle liegen unter `/tmp/lumen-workbench-final-focused.log`,
`/tmp/lumen-workbench-final-suite.log` und `/tmp/lumen-workbench-baseline-full.log`.
Die nativen Vorschauen liegen im Arbeitsordner
`lumen-desktop-entwuerfe/output/native/` neben den ursprünglichen HTML-Entwürfen.

## Visuelle Korrektur nach den Nutzerbildern

Die erste Umsetzung übernahm die Funktionen, aber nicht die gewünschte Gestaltung.
Die Werkbank behält Gesprächsspalte und Ergebnisfläche mit fester Aktionsleiste.
Nach der folgenden Nutzerkorrektur erben jedoch alle Oberflächen die vorhandene
Lumen-/KDE-Palette; feste helle bzw. dunkle Farben wurden wieder entfernt. Die
Sidebar ist in allen Ansichten 220 px breit, mit direkt sichtbaren letzten
Gesprächen und einem eigenen neuen Gespräch. Die Auftragsübersicht verwendet
breite Statuskarten und einen schmalen Inspektor. DM Sans wird mit OFL-Lizenz
lokal ausgeliefert.

Die Vorschaukarten verwenden ausschließlich vorhandene Aufträge und gespeicherte
Zustände. Schrittzahlen sind nur verfügbar, wenn echte Schritte vorliegen. Die
Beispielzahlen der Entwürfe werden nicht in Benutzerdaten übernommen. Ergebnisse
sind im Gespräch und am Auftrag erreichbar; weitere Apps und Einstellungen
liegen im Arbeitsraum-Menü. Die Anzeige automatischer Werkzeugfreigaben folgt der
wirklich eingestellten Freigabeoption.

37 gezielte Tests bestehen (`test_studio`, `test_assistant`, `test_desktop`,
`test_file_actions`, `test_studio_results`, `test_lumen_os.LumenIntegrationTest`,
`test_lumen_activation`, `test_vault_activation`). Der unabhängige statische Review
ist nach Korrektur des Freigabehinweises APPROVED. Der separate globale
Übersetzungstest hat weiterhin die bereits dokumentierten Katalogkonflikte und
neun ältere fehlende Texte; alle hier hinzugefügten Texte sind übersetzt.

`python3 scripts/render_desktop_workbench.py` erzeugt native Qt-Screenshots in
`/tmp/lumen-desktop-render`, wahlweise mit `LUMEN_RENDER_OUTPUT` und
`LUMEN_LANGUAGE=en`. Das Skript nutzt ein temporäres Home und einen privaten
Test-Store mit synthetischen Daten. Geprüft: Deutsch/Englisch, 1360 × 722 und
760 × 600. Aktuelle Bilder: `lumen-desktop-entwuerfe/output/native-corrected/`
im benachbarten Arbeitsordner.

## Theme- und Navigationskorrektur

Drei Regressionstests reproduzierten zuerst das erzwungene Weiß, die gemeinsame
Auftrags-/Ergebnisseite und die versteckte Gesprächsliste. Alle drei sind behoben.
Ergebnisse haben eine eigene Seite (`--page results`) mit unabhängigem Such- und
Auswahlzustand, sofort sichtbarer Vorschau sowie bestehenden Speicher-/Dateiaktions-
und Ablaufwegen. Ausschließlich abgeschlossene Aufträge mit tatsächlichem Ergebnis
erscheinen dort; Schließen in der Auftragsübersicht entfernt keine Ergebnisse.
Alle Ergebnisaktionen verwenden ausdrücklich die ID aus der Ergebnisliste.

Ein Entwurf oder Anhänge blockieren einen Gesprächswechsel, ohne Daten zu verlieren;
die Sidebar markiert dabei weiterhin die tatsächlich aktive Sitzung. Der
Regressionstest klickt dafür die reale native Listenzeile an. Ausführungsfreigaben,
Tracker und Gedächtniswege wurden nicht ersetzt.

39 gezielte Tests bestehen. Native Screenshots prüfen Glas, Graphit, Atelier,
Mitternacht, Deutsch/Englisch und große/kleine Fenster. Das Render-Skript unterstützt
nun `LUMEN_RENDER_THEME` und bildet auch die eigene Ergebnisseite ab. Bilder stehen
in `lumen-desktop-entwuerfe/output/navigation-fix/` im benachbarten Arbeitsordner.
Die bekannten Fehler der gesamten Basissuite sind hiervon unabhängig.

## Verstellbare Sidebar

Die Sidebar lässt sich am rechten Rand zwischen 200 und 420 Pixeln ziehen. Ein
nativer Qt-Splitter ersetzt die feste Breite und die dauerhafte vertikale Linie;
der acht Pixel breite Griff wird beim Überfahren sichtbar. Qt speichert die
gewählte Aufteilung in den bestehenden Einstellungen. Seitenwechsel behalten die
Breite. Der zusätzliche Sidebar-Punkt „Ergebnisse“ entfällt; Ergebnisse bleiben
im Gespräch und am Auftrag verfügbar, ebenso der bisherige direkte Seitenaufruf.

Ein Regressionstest zieht den echten Splitter mit Mausereignissen, wechselt die
Seite und öffnet eine neue Fensterinstanz. Er prüft auch die Mindestgröße 760 × 600.
Native Graphit-Screenshots: `lumen-desktop-entwuerfe/output/sidebar-resize/`.

## Live-Modellverlauf in Arbeitsschritte

Der Werkbank-Tab „Arbeitsschritte“ zeigt die vom bestehenden Engine-Polling
gelieferten Nachrichten des aktuellen Turns: Denktext, Modelltext und
Werkzeugaufrufe einschließlich Status, Eingaben, Ausgaben und Fehlern. Er liest
nicht mehr das gespeicherte Auftragsprotokoll, dessen Abschlussereignis lediglich
das fertige Ergebnis enthielt. Die Engine-Anbindung bleibt unverändert (450 ms
Pause zwischen Polling-Durchläufen). Denktext ist nur vorhanden, wenn das Modell
ihn liefert. Die Server-Bridge liefert aktuell keine solchen Parts; dort erscheint
ein entsprechender Hinweis anstelle eines vorgetäuschten Streams.

Markdown wird mit dem bestehenden sicheren Qt-Dokument dargestellt, Werkzeugdaten
als escaped Text. Kein automatisches Laden von Bildern oder Öffnen von Links.
Neue Ausgabe folgt am unteren Rand; beim Zurückscrollen bleibt die Leseposition
erhalten. Ein neuer Turn oder Gesprächswechsel ersetzt den bisherigen Verlauf.
Der Regressionstest prüft wachsenden Denktext, Werkzeugzustände, formatierten
Antworttext, Lesen während des Streams sowie Turn-/Session-Wechsel. Die 20
Studio-Tests bestehen; unabhängiger statischer Review APPROVED.

Die Ergebnisleiste wechselt bei Arbeitsbeginn automatisch auf „Arbeitsschritte“.
Eine erfolgreiche fertige Textantwort oder neu bereitgestellte Dateien wählen
„Ergebnis“. Zwischenmeldungen, ein Abbruch oder ein leeres Ergebnis lösen diesen
Wechsel nicht aus. Wiederholte Statusmeldungen überschreiben eine manuelle
Tab-Auswahl nicht. Die Tab-Automatik selbst öffnet keine geschlossene Leiste.
