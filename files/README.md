> This directory implements **Lumen Files**, the assistant's integrated **Dateien** page and shared native components. `lumen-files` opens the standalone file manager; both entry points use the same settings and AI integration. See [Lumen guide](../LUMEN-GUIDE.md).

# Lumen Files

Native Dateiverwaltung für Linux/KDE mit großer Vorschauleiste, laufender Dateinamensuche und Inhaltssuche, lokal und auf Netzwerkservern. Nutzt die bereits installierten Bibliotheken und Werkzeuge.

Die Oberfläche orientiert sich an Apples [Werkzeugleisten](https://developer.apple.com/design/human-interface-guidelines/toolbars)
und [Seitenleisten](https://developer.apple.com/design/human-interface-guidelines/sidebars):
kompakte Navigation, dezente Typografie, klare Dateiliste und eine eigene Vorschau.
KDE-Farben und Systemschrift werden automatisch übernommen, auch in offenen Fenstern.
Bei Iconsets mit installierter Hell-/Dunkelvariante wählt Files die zu den Farben
passende Variante. Die Desktop-Einstellungen selbst bleiben erhalten.

Dateisymbole werden anhand des Dateinamens ermittelt und nach Typ zwischengespeichert.
So bleibt auch das Wiederöffnen großer, gemischter Ordner bedienbar. Unbekannte
Dateitypen erhalten ein allgemeines Symbol; die Vorschau liest Inhalte weiterhin
bei Bedarf. Der eigenständige Starter stellt gespeicherte Tabs wieder her, während
die eingebettete Dateien-Seite im aktuellen Lumen-Arbeitsordner beginnt.

Der aktuelle Entwurf nutzt eine gemeinsame Navigationszeile unter den Tabs,
ruhige Flächen und gut lesbare Ortsnamen. Graphit verbindet dunkles Anthrazit mit
türkisen Akzenten und blauen Ordnersymbolen. Miniaturregler und Sammelfläche sitzen
kompakt unten; lange Pfade halten den aktuellen Ordner sichtbar. Das kompakte
Raster und die weichen Farbverläufe folgen dem Entwurf. Die konfigurierten
Standardordner erhalten eigene Symbole auch in Liste und Bibliothek; Verknüpfungen
behalten ihre native Markierung. Lokale Ordner wiederholen „Dieser PC“ nicht
unter jedem Symbol, gemeinsame Bibliotheken und Netzwerkorte zeigen ihre Herkunft.

## Start

Im Anwendungsmenü **Lumen Files** wählen, oder:

```bash
lumen-files
```

Ein Ordnerpfad oder eine Netzwerkadresse kann als Argument übergeben werden. Aus dem Checkout startet `./bin/lumen-files`, aus dem Paket `/usr/bin/lumen-files` mit den Quellen unter `/usr/share/lumen/files/`.

## Bedienung

- **Einstellungen / Strg+Komma:** gemeinsame Einstellungen für Lumen und Files. Startordner, versteckte Dateien, Vorschau, Suchverzögerung und Trefferlimit; gespeicherte Orte/Server entfernen. Änderungen wirken im aktuellen Files-Fenster, der Startordner im nächsten Fenster.
- **Strg+F:** aktueller Ordner einschließlich Unterordner durchsuchen. Alle eingegebenen Wörter müssen im Dateinamen vorkommen, Großschreibung ist egal. Treffer erscheinen laufend; **Esc** beendet die Suche. Typfilter begrenzen die Anzeige.
- **Rechtes Symbol im Suchfeld / Strg+Umschalt+F:** Text-, Code- und PDF-Inhalte im aktuellen Ordner einschließlich Unterordnern durchsuchen; Treffer zeigen echte Textstellen und eine Vorschau.
- **Einmal auswählen:** Vorschauleiste. **Leertaste:** große Vorschau. Bilder, SVG, blätterbare PDFs, Text/Code, Video-Standbilder und Audio-Wellenformen. Medienwiedergabe über die Standard-App.
- **Strg+L:** Pfad eingeben. **Alt+Links/Rechts/Hoch:** Verlauf / übergeordneter Ordner. Die seitlichen **Vor-/Zurück-Tasten der Maus** navigieren ebenfalls im Verlauf, unabhängig davon, über welchem Fensterbereich die Maus steht. Als Browser-Tasten gemeldete Signale werden ebenfalls unterstützt. In der Bildgalerie wechseln sie das Bild. **Strg+T / Strg+W:** Tab öffnen / schließen. **Strg+Tab:** nächster Tab.
- **Strg+C / X / V:** kopieren / ausschneiden / einfügen. **F2:** umbenennen. **Strg+Umschalt+N:** Ordner erstellen. **Entf:** nach Bestätigung in den Systempapierkorb verschieben.
- **Strg+H:** versteckte Dateien. **Ort merken** über das Lesezeichen-Symbol neben „Server verbinden“ ergänzt einen Favoriten. Rechtsklick auf einen gemerkten Ort entfernt ihn wieder. Die kompakte Seitenleiste zeigt bis zu zehn Orte auch bei 1000 × 640 Pixeln ohne Scrollen; lange Namen werden gekürzt, vollständige Pfade stehen im Tooltip.
- Ziehen von Dateien kopiert sie in den Zielordner. Bestehende Ziele werden mit einer Fehlermeldung beibehalten.

## Gemeinsame Einstellungen

In beiden Apps über **Einstellungen** oder **Strg+Komma**; direkter Start mit
`lumen-files --settings` oder `lumen-agent-app --page settings`.

Die Navigation hat sechs Hauptbereiche: **Darstellung & Desktop**, **KI & Sprache**,
**Dateien & Speicher**, **Apps**, **Datenschutz & Freigaben** und **Wartung**.
Jeder Bereich öffnet eine kurze Übersicht seiner Unterseiten. Alle bisherigen
Optionen, App-Verknüpfungen und nativen KDE-Dialoge bleiben erreichbar.

Die Suche oben (auch **Strg+F**) findet einzelne Einstellungen und springt mit
**Enter** direkt zum passenden Feld. Zugeklappte Details werden dabei geöffnet;
persönliche Feldwerte wie Ordnerpfade oder Modellnamen werden nicht durchsucht.
**KI & Sprache → Spracheingabe / Stimme & Vorlesen** bietet die laufenden
Sprachoptionen direkt; der Einrichtungsassistent bleibt für Installation und Tests.
Seltene Suchparameter und die Verwaltung von Orten liegen in aufklappbaren
Bereichen. Seitenwechsel und Suche erhalten ungespeicherte Änderungen und führen
keine Aktionen aus. Gespeichert wird weiterhin ausdrücklich über „Übernehmen“.

- **Lumen:** Arbeitsordner, Standardmodus, Übersetzungssprache, Modell aus den
  eingerichteten Providern und „Nicht mehr nachfragen“. Die Modellwahl gilt ab
  der nächsten Anfrage auch für intelligente Dateiaktionen. Provider-/Auth-
  Konfiguration bleibt erhalten. Werkzeugfreigaben ändern sich im aktuellen
  Chat nur, wenn genau dieser Schalter im zugehörigen Einstellungsfenster
  übernommen wird; andere offene Fenster behalten ihre sichtbare Wahl.
- **Tastenkürzel:** die vier registrierten globalen Lumen-Aktionen direkt ändern
  oder durch Leeren deaktivieren, mit Prüfung auf bereits belegte Kombinationen.
  Lokale Files-/Galerie-Kürzel sind als Übersicht vorhanden.
- **Darstellung:** **Klar & hell**, **Warmes Studio**, **Graphit** oder **KDE-Systemstil**,
  gemeinsam für Lumen und Lumen Files. Übernehmen aktualisiert offene Fenster;
  die Systemschrift bleibt erhalten. Die drei Designs ändern keine KDE-Einstellungen.
  KDE-Farben, Themes, Icons, Schriften, Kvantum, Effekte und weitere Desktop-
  Einstellungen öffnen den jeweiligen nativen Editor.
- **Leisten:** echte Panels nach Bildschirm, Position und ID auswählen. Größe,
  Position, Schweben und Sichtbarkeit ändern; pro Element den nativen Editor
  öffnen, etwa für Systemablage, Uhr, Startmenü oder Taskleiste. Vor Änderungen
  wird der Panelzustand unter `~/.local/state/lumen/settings-backups/`
  gesichert. Das ist eine Referenzkopie, kein automatischer Rückgängig-Knopf.
- **Dienste & Berichte:** reale Aktivierungszustände, gezieltes Ein-/Ausschalten,
  tägliche Uhrzeiten und automatische Analyse. Berichtsoptionen verwenden nur
  eigene `lumen-settings.conf`-Drop-ins unter `~/.config/systemd/user/`.
  Systemdienste benötigen gegebenenfalls die native Administratorabfrage.
  Die D-Bus-Systemintegration kann trotz abgeschaltetem Autostart bei Bedarf
  durch Lumen wieder starten.
- **Integrationen:** KRunner, Autostart, Standardprogramme, Netzwerk,
  Benachrichtigungen und die vorhandene Systemdokumentation.

Beim Öffnen werden nur Werte gelesen. Änderungen brauchen den jeweiligen
Übernehmen-Schalter; gleichzeitig in anderen Fenstern geänderte Werte werden
nicht überschrieben. Umfangreiche KDE-Optionen werden im KDE-Editor gespeichert.

## Lumen-Integration

Im schmalen Lumen-Panel bleiben **Dateien** und **Bildschirm** direkt sichtbar.
Das Menü **···** darunter enthält Zwischenablage, Diktieren und Kontext leeren.
**···** im Kopf öffnet Gesprächsverlauf, Arbeitsweise und „Schritte erklären“.

## Bibliotheken, Sammelfläche und Arbeitsräume

**Dokumente, Bilder, Musik und Videos** können mehrere lokale und Netzwerkordner
zusammen anzeigen. **Quellen …** öffnet deren Verwaltung; eigene Bibliotheken
entstehen über Einstellungen → Dateien → Bibliotheken und Quellen verwalten.
Jede Datei zeigt ihre **Herkunft**, auch im Bildraster. Gleiche Namen aus verschiedenen
Quellen bleiben getrennt. Unterordner öffnen am ursprünglichen Ort; die
Dateinamensuche durchsucht alle Quellen und deren Unterordner. Inhaltssuche und
Speicheranalyse fragen hier nach einem konkreten Ordner.

Bis zu 24 Quellen je Bibliothek, vier gleichzeitig. Nicht erreichbare Quellen
erscheinen unter **Hinweise (Details)**; andere Ergebnisse bleiben sichtbar.
Ein Quelldurchlauf ist auf 30 Sekunden und 100.000 geprüfte Einträge begrenzt,
zusätzlich gilt das Trefferlimit aus den Einstellungen. **Stoppen** beendet das
Laden, **F5** versucht es erneut. KDE-Anmeldungen haben bis zu 120 Sekunden Zeit.

Die **Sammelfläche** unten nimmt Dateiverweise per Drag-and-drop, Kontextmenü oder
**+** neben der Sammelfläche auf. **···** öffnet ihre Aktionen. Ihre Ansicht nutzt dieselben Vorschauen und Dateiaktionen.
**Verweise entfernen/leeren** lässt Originale bestehen; normale Dateiaktionen wie
Umbenennen oder Papierkorb wirken auf die Originale. Einfügen, neue Ordner und
Kopien aus einer Bibliothek fragen nach einem Ziel. Intelligentes Umbenennen und
Sortieren bleiben im jeweiligen Herkunftsordner.

**Arbeitsräume** oben speichern Tabs, Ansicht, Auswahl, Sammelfläche sowie das
Lumen-Gespräch mit Entwurf und Dateikontext. Jeder Arbeitsraum hat eine eigene
Sammlung; offene Fenster desselben Raums teilen deren Verweise. Wechseln und
Schließen speichern den aktiven Raum. Bestehende Aufträge lassen sich zuordnen;
ein Raumwechsel sendet keine Anfrage und wartet auf laufende Datei-/Lumen-Vorgänge.
Bei gleichzeitig geänderten Raumdaten erscheint ein Konflikthinweis. Bibliotheken,
Referenzen und Räume liegen in der vorhandenen Lumen-Datenbank, ohne Dateikopien.

**Lumen** in der Werkzeugleiste oder **Strg+J** öffnet das native Seitenpanel.
Rechtsklick → **Lumen** übernimmt alle ausgewählten Dateien:

- **Mit Lumen öffnen:** eigene Frage eingeben.
- **Erklären:** direkte Ergebnisansicht mit kurzer Erklärung und „Mehr Details“.
- **Fehler beheben:** native Fortschrittsanzeige, anschließend Ergebnis, Änderungen und Prüfung. „Ergebnis prüfen“ untersucht das Resultat nochmals ohne Bearbeitung.
- **Git-Diff prüfen:** eigene Ergebnisansicht für die Prüfung ohne Bearbeitung.

Diese Dateiaktionen zeigen ihre Ergebnisse ohne Chat-Eingabe, Gesprächsauswahl,
Moduswahl oder interne Auftragstexte. „Erneut versuchen“, „Kopieren“ und „Schließen“
sind direkt verfügbar; Abbrechen, Freigaben und Rückfragen bleiben im selben Panel.
Der freie Chat über **Lumen / Strg+J / Mit Lumen öffnen** bleibt separat erreichbar.
**Strg+Enter** sendet; „Neues Gespräch“ und die Gesprächsauswahl verwalten
Lumen-Unterhaltungen im Arbeitsordner. Der Kontext bleibt sichtbar, auch wenn
man im Dateimanager weiter navigiert. Netzwerkdateien nutzen ihren lokalen
KIO-FUSE-Pfad. Bilder/PDFs werden als Anhänge übergeben.

OpenCode arbeitet als lokale Hintergrund-Engine mit der bestehenden
Konfiguration. Dateien lassen sich auch ohne laufende Engine verwalten.

**Nicht mehr nachfragen** im Lumen-Bereich erlaubt Werkzeugfreigaben automatisch,
auch Befehle und Dateiänderungen. Der Schalter ist im freien Chat und bei
Erklären/Beheben/Prüfen sichtbar. Einschalten übernimmt bereits wartende
Freigaben; Ausschalten fragt bei der nächsten noch nicht erteilten Freigabe
wieder nach. Inhaltliche Rückfragen bleiben als Formular erhalten.

Standardmäßig ausgeschaltet. Die Auswahl wird unter `~/.config/Lumen/Assistant.conf`
für neue Lumen-Fenster und Files-Panels gespeichert; bereits offene Fenster
behalten ihre sichtbare Einstellung. Automatische Freigaben gelten nur für das
aktuelle Gespräch und dessen Unteraufgaben. Explizite OpenCode-Verbote und der
Lesemodus bleiben wirksam; Umbenennen/Sortieren und Suchbegriffe behalten ihre
Werkzeugsperre. Es werden keine globalen OpenCode-Regeln geändert.

## Intelligent umbenennen und sortieren

Dateien markieren → Rechtsklick → **Lumen → Intelligent umbenennen …** oder
**Dateien sortieren …**. Bei mehreren ausgewählten Dateien öffnet auch **F2**
das intelligente Umbenennen. Eine optionale Vorgabe wie „Datum und Thema im
Namen“ ergänzen und **Vorschläge erstellen** anklicken.

Die native Tabelle zeigt bisherige Namen, editierbare Ziele und Begründungen.
Ziele mit Doppelklick/F2 bearbeiten, unerwünschte Vorschläge abwählen.
Erst **Änderungen anwenden** verändert Dateien. Umbenennen erhält den bisherigen
Ordner und die Endung; Sortieren erhält den Namen und erstellt Unterordner im
aktuellen Ordner. Belegte, doppelte, überlappende oder ungültige Ziele werden
markiert. Nachträglich geänderte Dateien werden nicht verschoben.

**Rückgängig** im Dialog oder **Letzte Lumen-Dateiaktion rückgängig …** im
Datei-Kontextmenü stellt den letzten Durchlauf wieder her, auch nach einem
Neustart. Ein neuer Durchlauf ersetzt die vorherige Rückgängig-Möglichkeit.
Das Journal liegt unter `~/.local/share/Lumen Files/organize-undo.json` (bzw.
unter dem entsprechenden XDG-Datenpfad). Bei Teilfehlern/Abbruch werden bereits
ausgeführte Änderungen angezeigt; verbleibende Undo-Konflikte bleiben im
Journal. Leere neu angelegte Zielordner bleiben erhalten. Auch Undo überschreibt
keine Dateien und lässt inzwischen bearbeitete Dateien unangetastet.

Bis zu 100 reguläre Dateien je Durchlauf, keine Ordnerauswahl oder Symlinks.
Lumen erhält höchstens 4.096 Zeichen Text je Datei, Text aus den ersten drei
PDF-Seiten und bis zu zwölf Bildvorschauen mit maximal 1.024 Pixeln Kantenlänge;
sonst nur Namen/Größen. Gescannte PDFs benötigen Text, es gibt hier kein OCR.
Inhalte werden über deine bestehende Modellkonfiguration verarbeitet. Die
Vorschlagssitzung sperrt alle Werkzeuge über die
[OpenCode-Berechtigungen](https://opencode.ai/docs/permissions/); Files führt
bestätigte Änderungen selbst aus. Vorschläge erscheinen nicht im Chatverlauf.
Verschieben erfordert einen nativen Move innerhalb desselben Dateisystems;
Netzwerk-Backends ohne diese Unterstützung melden einen Fehler, ohne auf
Kopieren/Löschen auszuweichen. Keine neuen Bibliotheken nötig.

## Inhalte suchen

Das **rechte Symbol im Suchfeld** oder **Strg+Umschalt+F** öffnet die native
Suchansicht. Eine Frage wie „Die Rechnung für meinen Monitor“ sucht lokal nach
den wichtigen Begriffen. Mehrere Begriffe müssen im Dokument vorkommen;
Anführungszeichen verbinden Wörter zu einer Phrase. Treffer erscheinen laufend
mit Originaltext, Zeile oder PDF-Seite. Auswählen zeigt die Fundstelle und springt
in der PDF-Vorschau zur passenden Seite. **Datei öffnen** und **Ordner öffnen**
führen direkt zum Ergebnis. **Stoppen**, eine neue Anfrage und Schließen beenden
den Suchprozess einschließlich eines laufenden PDF-Decoders.

Optional ergänzt **Mit Lumen erweitern** verwandte Begriffe, etwa „Bildschirm“
für „Monitor“. Dafür gehen die Suchfrage und die eingerichteten persönlichen
Lumen-Anweisungen an dein konfiguriertes Modell. Gefundene Dokumente werden
nicht angehängt. Die Sitzung läuft mit gesperrten Werkzeugen in einem leeren
Arbeitsordner; Projektanweisungen aus dem durchsuchten Ordner werden nicht
automatisch geladen. Modellfehler lassen bisherige lokale Treffer erhalten.

Ohne persistenten Index: bis zu 1 MiB Text pro Datei, PDF-Textextraktion mit
`pdftotext` bis 128 MiB Dateigröße und 12 Sekunden pro PDF. Maximal 500 Treffer
oder 100.000 besuchte Einträge je Suche. Teilweise durchsuchte, nicht lesbare und
textlose Dateien werden im Ergebnisstatus gezählt. Versteckte Einträge sind
optional, Symlinks und Spezialdateien werden ausgelassen. Keine OCR- oder
Office-Inhaltssuche; gescannte PDFs brauchen bereits eine Textebene. Große Bäume
und Netzwerkordner dauern länger und können Daten vom Server herunterladen.

## Bildgalerie und einfache Bearbeitung

Die dunkle Großansicht zeigt unten einen Filmstreifen. Ein Klick springt direkt zum Bild;
ungespeicherte Änderungen werden dabei geschützt. Nur sichtbare Miniaturen und der
Randbereich werden geladen, maximal 48 kleine Vorschauen bleiben im Cache.
**Bearbeiten** blendet die Leiste mit Drehen, Spiegeln, Rückgängig, Speichern und
Papierkorb ein. Das lokale/NAS-Ziel steht oben; die Galerie bleibt in allen Designs dunkel.
In der Seitenvorschau stehen Bild, Name, Dateigröße, Auflösung und Herkunft sowie
**Groß öffnen** und **Bild bearbeiten** direkt bereit.

Größere Fotos werden im separaten Bildprozess mit begrenzter Parallelität geladen.
Damit bleiben NAS-Vorschau, Miniaturen und Galerie auch auf Rechnern mit vielen
CPU-Kernen innerhalb des Speicherlimits; Schutz vor übergroßen Bildern bleibt aktiv.

Ein Bild doppelklicken oder mit **Leertaste** öffnen. Die Galerie übernimmt die Bilder und Sortierung der aktuellen Ansicht, auch bei Suchergebnissen. **Links/Rechts** wechseln das Bild; Nachbarbilder werden vorgeladen. **Mausrad / + / −** zoomen, Ziehen verschiebt das Bild, **0** passt es ein, **F11** schaltet Vollbild um. **Esc / Leertaste** schließen die Galerie.

**R / Umschalt+R** drehen rechts / links, **H** spiegelt horizontal, **Strg+Z** nimmt einen Schritt zurück. **Strg+S** speichert JPEG, PNG oder einzelne WebP-Bilder in voller Auflösung. EXIF-Ausrichtung wird berücksichtigt. JPEG wird mit hoher Qualität neu komprimiert; PNG und WebP werden verlustfrei geschrieben. Die Bildschirmvorschau ist für schnelles Blättern auf 2560 Pixel begrenzt; sie ist keine pixelgenaue Originalansicht.

Vor jedem Speichern entsteht eine bytegenaue Sicherung in **`.lumen-originals` neben dem Bild**, sichtbar mit **Strg+H**. Die Sicherung bleibt auch bei weiteren Bearbeitungen erhalten und kann bei Bedarf zurückkopiert werden. Dateien werden zunächst separat geschrieben und anschließend ersetzt. Erkannte externe Änderungen brechen das Speichern ab. Animationen, andere Formate und symbolische Links werden nicht überschrieben. Bei Netzwerkdateien muss der Server Sicherung und Ersetzen unterstützen; Fehler werden angezeigt.

**Entf / Papierkorb** verschiebt das aktuelle Bild nach Bestätigung in den Systempapierkorb und zeigt das nächste. Ein nicht unterstützter Papierkorb führt zu einer Fehlermeldung. Ungespeicherte Bearbeitungen lassen sich beim Bildwechsel speichern, verwerfen oder durch Abbrechen behalten.

## Speicheranalyse

In der Spalte **Größe** zeigen Dateien ihre Dateigröße. Bei Ordnern steht zunächst
**Berechnen**: Ein Klick öffnet die abbrechbare Speicheranalyse mit logischen
Dateigrößen. Nach erfolgreicher Berechnung steht die Gesamtgröße inklusive
Unterordnern direkt in der Liste, auch in Bibliotheken und Suchergebnissen.
Alternativ: Rechtsklick → **Ordnergröße berechnen**. Leere Ordner zeigen **0 B**;
abgebrochene oder unvollständige Berechnungen liefern keinen neuen Spaltenwert.
Berechnete Größen sind Momentaufnahmen, werden numerisch sortiert und mit **F5**
oder beim Ordnerwechsel zurückgesetzt. NAS-Ordner werden nicht automatisch rekursiv
durchsucht. Dateien mit mehreren Hardlinks werden je Analyselauf einmal gezählt.

**Speicheranalyse** in der Seitenleiste untersucht den aktuellen Ordner. **Ordner wählen** erlaubt andere Verzeichnisse oder Laufwerke; der Rechtsklick auf einen Ordner bietet dieselbe Funktion. Der Größenbaum ist sortierbar und zeigt den Anteil am jeweiligen Elternordner. Beim Aufklappen werden Unterordner genauer analysiert. **Ordner öffnen** wechselt zur ausgewählten Stelle im Dateimanager.

Standardmäßig wird belegter Speicher gezählt; die Checkbox wechselt zur logischen Dateigröße. Versteckte Dateien sind enthalten, Verzeichnis-Symlinks werden nicht verfolgt, andere Dateisysteme nicht durchlaufen. Ein anderes Laufwerk separat auswählen. Hardlinks werden je Analyselauf einmal gezählt; beim erneuten Untersuchen eines Teilbaums kann sich ihre Zuordnung ändern. Komprimierte oder gemeinsam genutzte Datenblöcke können zu Abweichungen gegenüber dem freien Laufwerksspeicher führen.

Die Analyse nutzt GNU `du` und `find` in eigenen Prozessen, ist mit **Stoppen** abbrechbar und verändert keine Dateien. Unlesbare Bereiche werden als unvollständig gemeldet. Pro aufgeklapptem Ordner erscheinen höchstens die größten 5.000 direkten Einträge; die Gesamtgröße umfasst weiterhin alle gezählten Einträge. Große Unterbäume werden beim ersten Aufklappen erneut durchlaufen.

Tabs stehen oberhalb aller Bedienelemente. Der automatische Seitenleisteneintrag `/mnt/games` entfällt. Eigene Spieleordner können weiterhin über **Ort merken** hinzugefügt werden.

Beim nächsten Start werden offene Tabs, der aktive Tab, Sortierung und die Breite der Vorschauleiste wiederhergestellt. Nicht mehr vorhandene lokale Ordner werden übersprungen; Netzwerk-Tabs verbinden sich erst beim Aktivieren. Ein ausdrücklich übergebener Startordner hat Vorrang. In den Einstellungen lässt sich die Tab-Wiederherstellung abschalten.

**Strg+1 / Strg+2** oder die beiden Ansichtsschalter wechseln zwischen Liste und Bildraster. Auswahl, Suche, Typfilter, Ziehen/Kopieren und die Galerie funktionieren in beiden Ansichten. Der Regler über dem Raster passt die Miniaturgröße an; Ansicht und Größe bleiben gespeichert. Fotos bleiben vollständig sichtbar, die Auswahl erhält einen feinen Rahmen. Das Raster lädt sichtbare Bilder in einem separaten Prozess und hält höchstens 256 Miniaturen mit maximal 256 Pixeln im Speicher. Defekte Bilder behalten ihr Dateisymbol. **F5** lädt die Miniaturen neu, etwa bei verzögerten Änderungen auf Netzlaufwerken.

## Netzwerkserver

Für SMB reicht der **Servername**, etwa `nas.local` oder `smb://nas/`.
Gespeicherte Server öffnen direkt ihre Freigaben als Ordner. Beim Öffnen einer
geschützten Freigabe erscheint bei Bedarf die native Anmeldung mit Benutzername
und Passwort, ohne zusätzliches Formular für Ort oder Freigabename.
Vollständige Freigabeadressen wie `smb://name@nas/Fotos` funktionieren weiterhin.
Passwörter werden nicht in Lumen-Adressen gespeichert. „Verbunden“ erscheint erst nach
erfolgreichem Lesen des Verzeichnisses. Eine fehlerhafte Anmeldung wird als Fehler
angezeigt, statt wie ein leerer Ordner zu wirken.
Vor SMB-Verbindungen nutzt Lumen das vorhandene `kioclient --interactive ls` für den nativen
KDE-Anmeldedialog, damit auch ältere KIO-FUSE-Versionen Zugangsdaten anfordern.
Der Helfer läuft unsichtbar; Lumen erhält und speichert dabei kein Passwort.
Fehlt er, zeigt Lumen einen konkreten Hinweis auf das Paket `kde-cli-tools`.

**Server verbinden** in der Seitenleiste oder **Strg+K** öffnet den Verbindungsdialog. Unterstützt werden die installierten KDE-Protokolle SMB, SFTP, WebDAV, FTP und NFS. Beispiele:

| Verbindung | Adresse |
|---|---|
| NAS / Windows-Freigabe | `smb://nas.local/` zum Durchsuchen oder `\\nas.local\Freigabe` direkt |
| SSH / SFTP | `sftp://name@server:22/ordner` |
| WebDAV mit TLS | `webdavs://cloud.example/remote.php/dav/files/name/` |
| WebDAV ohne TLS | `webdav://server/ordner` |
| NFS | `nfs://server/export` |
| FTP | `ftp://name@server/ordner` |

Im Dialog reichen `nas.local` und das ausgewählte Protokoll; der Freigabename ist optional. Vollständige Netzwerkadressen lassen sich direkt über **Strg+L** eingeben; HTTPS-/HTTP-Adressen werden dort als WebDAV interpretiert. Netzwerksuche nach unbekannten Geräten ist nicht enthalten.

KDE übernimmt die Anmeldung und gegebenenfalls KWallet. Passwörter in Adressen werden abgewiesen und nicht in Lumen-Einstellungen gespeichert. **Server merken** speichert nach erfolgreichem Öffnen die Adresse in der Seitenleiste. Rechtsklick öffnet einen neuen Tab oder entfernt den gemerkten Ort. **Ort merken** speichert auch Unterordner einer Verbindung. Pfadleiste, Verlauf und Neustart verwenden die Serveradresse.

Die Anbindung erfolgt über den bereits installierten [KIO-FUSE-Dienst](https://github.com/KDE/kio-fuse/blob/master/README.md). Verbundene Ordner nutzen dieselbe Suche, Vorschau und Dateiaktionen. Übertragungen laufen im Hintergrund; Vorschauen können Daten vom Server herunterladen. Kopien **auf** eine KIO-Netzwerkfreigabe übernehmen Inhalte und Verzeichnisstruktur, aber erzwingen keine Unix-Rechte, Eigentümer oder Zeitstempel, die beispielsweise WebDAV nicht unterstützt. Namenskonflikte überschreiben keine bestehenden Dateien.

**Abbrechen / Esc** verwirft die wartende Verbindung in Lumen. Der gemeinsame KDE-Dienst kann eine bereits laufende Anmeldung noch abschließen; Lumen öffnet oder speichert diese verspätete Verbindung nicht. Einzelne KIO-Verbindungen werden nicht ausgehängt, da sie auch andere KDE-Anwendungen verwenden können. Dateisystem-/Server-Caches können Änderungen verzögert anzeigen. Papierkorb funktioniert nur, wenn der Server bzw. Mount ihn unterstützt; ein Fehler führt nie zum endgültigen Löschen.

SMB/SFTP/NFS/FTP sind über die installierten KDE-Module angebunden. Der automatisierte End-to-End-Test verwendet einen echten, ausschließlich auf `127.0.0.1` erreichbaren WebDAV-Testserver und prüft Navigation, Neustart, Suche, Textvorschau, Upload/Download, Ordnerkopie, Verschieben, Konflikte, Fehler und verspätete Antworten. Eine Anmeldung an deinem eigenen NAS oder SSH-Server ist damit noch nicht geprüft.

## Verhalten und Grenzen der ersten Version

Die Dateinamensuche arbeitet direkt auf dem Dateisystem, **ohne Index**. Sie folgt keinen Verzeichnis-Symlinks und endet standardmäßig bei 5.000 Treffern mit einem Hinweis (in den Einstellungen 100–50.000). Bei großen Verzeichnisbäumen oder langsamen Netzlaufwerken dauert ein vollständiger Durchlauf länger. Nicht lesbare Einträge werden gezählt. Der Typfilter wirkt auf die gefundenen Treffer. Für Textinhalte gibt es die separate Inhaltssuche mit den oben genannten Grenzen.

Textvorschauen lesen maximal 128 KB, Bilder maximal 128 MB / 80 Megapixel. Metadatenabfrage und Decoder laufen außerhalb der Oberfläche und werden jeweils nach 12 Sekunden beendet. Videos zeigen das erste Bild, Audio zeigt eine Wellenform der ersten 30 Sekunden. Keine Office-Vorschau oder integrierte Medienwiedergabe.

Kopien werden zunächst in einem temporären Ordner auf dem Ziellaufwerk erstellt und erst bei Erfolg sichtbar gemacht; bestehende Dateien werden nie still überschrieben. Bei Prozessabsturz können `.lumen-copy-*`-Ordner zurückbleiben. Kopiervorgänge lassen sich derzeit nicht abbrechen; das Fenster bleibt bis zum Ende offen. Ordner zwischen verschiedenen Dateisystemen zu verschieben kann GIO ablehnen; dafür zuerst kopieren und erst nach Kontrolle das Original in den Papierkorb verschieben. System-Papierkorb und Wiederherstellung können weiterhin in Dolphin genutzt werden.

Einstellungen und Favoriten: `~/.config/Lumen/Files.conf`. Es werden keine Standardzuordnungen geändert.

## Prüfung

```bash
cd files
QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest -v
/usr/bin/python3 -m compileall -q .
```

Die Prüfungen verwenden temporäre Dateien: rekursive Suche, versteckte Dateien, Symlink-Schleife, ungültige Namen, Kopieren ohne Überschreiben, Tabs/Verlauf, Suchwechsel, Bild/SVG/PDF/Text/Video/Audio, defekte Dateien, Spezialdateien, Zwischenablage, Umbenennen/Verschieben und wiederherstellbarer Papierkorb. Der Papierkorb-Test hat ein isoliertes Datenverzeichnis.

Zusätzlich geprüft: Tabs oberhalb der Suche, Galerie-Aufruf und Bildfolge, vorgeladene Nachbarbilder, Drehen/Spiegeln, EXIF-Ausrichtung, Original-Sicherung, Änderungskonflikte, Schutz von Animationen und Symlinks, Papierkorb-Erfolg/Fehler in der Galerie sowie Speichergrößen, Sparse-Dateien, Hardlinks, Verzeichnis-Symlinks, Zugriffsfehler und Abbruch. Diagnose-Screenshots werden lokal unter `artifacts/` erzeugt und nicht veröffentlicht.

Vor/Zurück wird an der Dateiliste selbst und ihrer inneren Fläche, Seitenleiste,
Vorschau, Suche, Tabs und Galerie geprüft, mit Mausklicks und Browser-Tasten.
Zusätzlicher Laufzeittest über X11-Ereignisse: Buttons 8/9 und XF86Back/Forward.
Die Dateiliste darf `QWidget.window()` nicht mit einem Instanzattribut verdecken;
die frühere Kollision verursachte Fehler bei direkt an die Liste gelieferten Ereignissen.

Die Inhaltssuche prüft echte Text-/PDF-Fundstellen, deutsche Suchbegriffe,
Synonyme, PDF-Seitensprung, Grenzen, versteckte Einträge, Symlink-Austausch,
fehlerhafte Modellantworten und das Beenden laufender Decoder bei Abbruch oder
Scanner-Ausfall. Zusätzlich wurde die Begriffserweiterung mit der echten Engine
an temporären Text- und PDF-Dateien geprüft.

Gemessener Suchkern: 30.000 kleine Dateien in 100 Ordnern, 100 Treffer, erster Treffer nach 0,0002 s und Abschluss nach 0,0176 s. Synthetischer warmer Cache auf diesem Rechner, ohne UI und ohne 250-ms-Eingabeverzögerung; kein allgemeines Leistungsversprechen.

## Voraussetzungen

Python 3, PySide6/Qt 6 einschließlich QtDBus, QtSvg und QtQuick (`pyside6`), PyGObject/GIO, Pillow, GNU `du`/`find`, Poppler (`pdfinfo`, `pdftoppm`, `pdftotext`), FFmpeg (`ffprobe`, `ffmpeg`), KIO-FUSE und KIO-Extras. Sämtliche Komponenten waren auf diesem Rechner vorhanden. Dateioperationen nutzen die dokumentierte [GIO-Semantik](https://docs.gtk.org/gio/method.File.move.html); Bildvorschauen die [Qt-Bilddekodierung](https://doc.qt.io/qt-6/qimagereader.html), mit Prüfung gegen Qt 6.

## Entfernen

Die beiden Starter `~/.local/share/applications/lumen-files.desktop` und `~/.local/bin/lumen-files` entfernen. Optional zusätzlich das Projektverzeichnis und `~/.config/Lumen/Files.conf` entfernen. Dolphin bleibt installiert und unverändert zugeordnet.
# Arbeitsplatz

Im Menü **Arbeitsplatz · Projekte & Verlauf** öffnen. Projekte verbinden benannte
Quellen auf PC/NAS mit gespeicherten Dateitabs, explizit ausgewählten Programmen,
Webseiten und einer Notiz. „Weiterarbeiten“ stellt diesen Stand wieder her;
„Aktuellen Stand merken“ übernimmt die aktuelle Ansicht. „Quellen prüfen“ zeigt
Erreichbarkeit und die zuletzt geänderten Dateien eines begrenzten Scans. Offline
bleiben bekannte Dateien als solche gekennzeichnet sichtbar.

Arbeitsmodi bündeln Audio, Benachrichtigungen, Fenster und Netzwerkordner. Transfers
und der geprüfte Änderungsverlauf sind mit der Lumen-App geteilt. Downloads werden
in Lumen gestartet; fremde Browser-Downloads sind nicht eingebunden. Bei Kopien und
Verschiebungen werden nach einem Fehler verbleibende Einträge erneut versucht.
Vorhandene Ziele werden nie überschrieben. Native Dateiaktionen lassen sich nur
zurücknehmen, solange der aufgezeichnete Zustand unverändert ist; Papierkorb-
Aktionen selbst bleiben reine Verlaufseinträge.

### Desktop-Suche und Einstellungen

`lumen-search` öffnet eine native gemeinsame App-/Dateisuche mit Gespräch. Enter
öffnet den gewählten Treffer; Strg+Enter fragt direkt. Natürlich formulierte Fragen
stehen als Gesprächstreffer oben. Antworten und Folgefragen bleiben im Fenster.
„Neue Suche“ beginnt neu; Schließen blendet die Suche aus und erhält das Gespräch.
Die persönliche Dateisuche ist auf 100 Treffer, 100.000 Einträge und acht Sekunden
begrenzt. Die vorhandenen Freigaben/Rückfragen bleiben direkt im Gespräch bedienbar.
`lumen-settings` öffnet die gemeinsamen Einstellungen ohne das Hauptfenster.

### Gemeinsame Themes

**Glas** ist der Standard: Rauchblau, mintfarbene Hauptaktionen und runde Buttons.
**Graphit**, **Atelier** und **Mitternacht** bieten matte, warme helle bzw. klare
dunkle Alternativen. Auswahl unter **Einstellungen → Erscheinungsbild** oder
**Themes** in der rechten Lumen-Leiste. „Design übernehmen“ speichert gemeinsam
für Lumen, Suche, Files, Bilder, Plasma-Leisten samt Panels und native
Fensterdekorationen. Uhr, Systemablage und Titelleisten übernehmen die passende
Palette; laufende aktuelle App-Versionen wechseln mit. Die Suche liest das Design
auch beim erneuten Öffnen ein; Gespräch und Entwurf bleiben erhalten.
Alte App-Prozesse nach einem Programmupdate benötigen einmal die neue Version.
KDE-Systemstil und die nativen Desktop-Einstellungen bleiben verfügbar.

### Offline-NAS-Ordner

Im Kontextmenü eines verbundenen Netzwerkordners oder gemerkten Servers **Offline verfügbar machen** wählen. Die lokale Arbeitskopie erscheint unter den Orten und ist auch ohne NAS erreichbar. **Menü → Offline verfügbare Ordner** zeigt Status, Konflikte und Sicherungen. Während Files läuft, wird im Hintergrund jede Minute versucht abzugleichen; **Jetzt abgleichen** öffnet bei Bedarf die native KDE-Anmeldung.

Unabhängige Änderungen werden in beide Richtungen übernommen. Bei konkurrierenden Änderungen oder Löschen/Ändern wird keine Fassung automatisch gewählt. Beide Fassungen können geöffnet werden; eine Entscheidung wird nur bei unveränderten Inhalten übernommen. Ersetzte und gelöschte Dateien bleiben im privaten Sicherungsordner. „Nicht mehr abgleichen“ entfernt nur die Registrierung, niemals lokale Daten. Symlinks werden abgelehnt; pro Ordner gilt ein ausdrücklich gemeldetes Limit von 50.000 Dateien. Zugangsdaten werden nicht im Offline-Katalog gespeichert.

### Bilder und Scans suchen

**Strg+Umschalt+F** durchsucht Texte, PDFs, Bildbeschreibungen und optional lokal erkannte Schrift in Bildern/scannierten PDF-Seiten. Die Treffer zeigen Fundstelle, PDF-Seite, Herkunft und Vorschau. OCR nutzt Tesseract (Deutsch/Englisch) und Poppler; fehlende Pakete sind über **Texterkennung einrichten** installierbar. Ergebnisse werden privat zwischengespeichert und nach Dateiänderungen neu berechnet. OCR ist auf 80 Seiten pro PDF und 128 MiB pro Datei begrenzt; unvollständige und nicht lesbare Dateien werden gezählt.

Die ausdrücklich auswählbare **Bildinhalte mit Lumen erkennen**-Option sendet verkleinerte Bilder an den eingerichteten Modellanbieter (ein bildfähiges Modell ist nötig). Bis zu 100 neue Beschreibungen werden pro Suche angelegt. Spätere Suchläufe verwenden diese lokal, ohne die Bilder erneut zu senden; **Mit Lumen erweitern** ergänzt deutsche/englische Synonyme. Bilder und OCR-Texte bleiben außerhalb des Repositories. Die technische OCR-Anbindung folgt der [Tesseract-Dokumentation](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html).

### Dateiversionen

**Menü → Dateiversionen → Ordner sichern** aktiviert eine unabhängige, beim Anmelden wieder startende Sicherung. Sie erfasst auch externe Änderungen; Standard: alle 30 Sekunden, 20 Fassungen pro Datei, 90 Tage, insgesamt 5 GiB. Diese Grenzen sind unter **Überwachte Ordner** einstellbar. Sehr kurze Zwischenstände zwischen zwei Prüfungen können fehlen. Versionen liegen lokal und ersetzen kein Backup gegen einen Defekt dieses Datenträgers.

Über das Kontextmenü einer Datei lassen sich Fassungen mit der aktuellen Datei vergleichen (Textvergleich bis 200 KiB und native Dateivorschau). Wiederherstellen sichert zuerst die aktuelle Fassung und verweigert die Aktion, wenn diese seit dem Vergleich verändert wurde. Gelöschte Dateien bleiben über **Alle Dateien** erreichbar. Nicht mehr überwachte Ordner werden nicht weiter gelesen; vorhandene Versionen unterliegen weiterhin der Aufbewahrung beim nächsten Sicherungslauf. Eine einzelne Datei über der Speichergrenze sowie unlesbare Ordner werden als Sicherungsfehler protokolliert.

### Sprachgespräch

Das Mikrofon sitzt direkt in der gemeinsamen Sucheingabe und im Chat von Lumen/Files. **Sprechen** startet automatische Runden: Sprechpause → lokale Whisper-Erkennung → bestehendes OpenCode-Gespräch → lokale deutsche Piper-Ausgabe → wieder zuhören. Audio bleibt lokal; der erkannte Text nutzt den bisherigen Modellanbieter, einschließlich Ollama Cloud. Freigaben und Rückfragen bleiben im vorhandenen nativen Dialog.

**Unterbrechen** beendet die laufende Antwort/Ausgabe und schaltet wieder auf Zuhören. Während der Ausgabe ist das Mikrofon aus (keine automatische Unterbrechung durch Hineinsprechen und keine Lautsprecher-Rückkopplung). **Beenden** oder Fenster ausblenden schaltet das Mikrofon aus. Unter **Weitere Kontextaktionen → Sprachgespräch einstellen** sind Mikrofonschwelle und Sprechpause einstellbar. Nach drei Minuten ohne erkannte Sprache endet die Aufnahme.

Optional lässt sich unter **Einrichtung → Sprache → Mehrsprachige Stimme einrichten** Qwen3-TTS 0.6B installieren. Die Stimme verarbeitet Deutsch und Englisch im selben Text, auch bisher unbekannte englische Begriffe; es gibt keine manuell gepflegte Wortliste. Das Modell benötigt etwa 2,5 GB, die zusätzliche Python-/GPU-Laufzeit mehrere weitere GB. NVIDIA CUDA wird automatisch genutzt, sonst die CPU (deutlich langsamer). Die bisherige deutsche Thorsten-Stimme bleibt als sparsame Alternative verfügbar. Die gemeinsame Auswahl unter **Sprachausgabe** gilt für Gespräche, Reader, Radio und vorgelesene Projektstände. Das Erkennungsmodell für das Mikrofon ist davon unabhängig.

Die mehrsprachige Stimme bleibt während eines aktiven Gesprächs geladen; Beenden oder Unterbrechen gibt den Prozess und seinen Grafikspeicher frei. Bei der nächsten Ausgabe wird sie bei Bedarf neu geladen. Es gibt keinen Netzwerkdienst; Texte gehen über eine lokale Prozess-Pipe. Modelldateien stammen aus einer festgelegten Revision, werden per SHA-256 geprüft und vor der Freigabe mit einer lokalen Probe ausgeführt. Die Ausgabe läuft danach offline. `~` wird nur im gesprochenen Text als „Tilde“, `~/` als „Benutzerordner/“ normalisiert. Dokumente, Antworten und Radio-Quellenpositionen bleiben unverändert. Bereits erzeugte Audiodateien ändern sich erst beim erneuten Erzeugen.

Mehrsprachigkeit garantiert keine fehlerfreie Aussprache jedes Eigennamens. Qwen3-TTS verwendet eine andere Stimme und benötigt mehr Zeit als Piper; auf der getesteten RTX 4090 lagen kurze warme Ausgaben bei etwa 3–5 Sekunden, das erste Laden bei etwa 4 Sekunden zusätzlich. Quelle: [offizielles Qwen3-TTS-Projekt](https://github.com/QwenLM/Qwen3-TTS).

Der Einrichtungsassistent installiert Whisper sowie Piper 1.8.0 in einer privaten Python-Umgebung und die deutsche Thorsten-Stimme (63 MB, CC0-Datensatz); Modelldateien werden per SHA-256 geprüft. Quellen: [Piper CLI](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md), [PipeWire-Aufnahme](https://docs.pipewire.org/1.4/page_man_pw-cat_1.html). Das ist ein lokaler Audioablauf mit turnweisen Modellantworten; Latenz hängt von Aufnahme, Erkennung und Modellanbieter ab.

### Eigene Dateiaktionen

Nach einer erfolgreichen Lumen-Aufgabe erscheint **Als Dateiaktion speichern**; dieselbe Funktion gibt es in der Aufgabenansicht. Der vorhandene Ablaufeditor zeigt Namen, Schritte beziehungsweise KI-Auftrag und Platzhalter: `{{datei}}`, `{{ordner}}`, `{{name}}`, `{{stamm}}`, `{{endung}}`, `{{auswahl}}`. Gespeicherte Aktionen erscheinen in Files unter **Kontextmenü → Eigene Aktionen** und lassen sich unter **Abläufe** entfernen.

Vor jeder Anwendung werden die neue Auswahl und die daraus erzeugten Schritte beziehungsweise der Auftrag im nativen Editor gezeigt. Gleichnamige Ausgabeziele für mehrere Dateien werden abgelehnt. Native Dateischritte verwenden den bestehenden geprüften Auftragsrunner; KI-Arbeiten wie „Bilder verkleinern, benennen und zippen“ verwenden die gespeicherte Anweisung im normalen Lumen-Gespräch mit den bisherigen Werkzeugfreigaben. Systemschritte bleiben normale Abläufe. Persönliche Aktionen und ihre Eingaben werden nicht veröffentlicht.

### Dokumentenwerkstatt

PDFs auswählen und **Kontextmenü → Dokumentenwerkstatt** öffnen (oder über das Files-Menü). Weitere PDFs hinzufügen, Seiten durch Ziehen umordnen, drehen oder aus der Arbeitsmappe entfernen. **Auswahl als PDF** extrahiert markierte Seiten, **Alles als PDF** verbindet die gesamte Reihenfolge. Jede Ausgabe erhält einen neuen Namen; vorhandene Dateien werden nicht überschrieben.

**Schwärzen** aktivieren und Bereiche in der großen Vorschau aufziehen. Beim Export werden Inhalte tatsächlich entfernt und betroffene Seiten anschließend als neues Bild aufgebaut, damit alte Inhalte und versteckte Textebenen dieser Seiten nicht enthalten bleiben. Die optionale lokale Texterkennung erzeugt danach eine neue Textebene aus dem sichtbaren Ergebnis. Die Qualität ist mit 150/200/300 dpi wählbar. Originale bleiben unangetastet. Strg+Mausrad vergrößert die Vorschau.

Benötigt das optionale Paket `python-pymupdf`, für OCR außerdem Tesseract-Sprachdaten; beides im Setup verfügbar. Unterstützt unverschlüsselte PDFs bis 512 MiB und Arbeitsmappen bis 2.000 Seiten. Quelldateien werden gegen Änderungen während der Bearbeitung geprüft; Exporte werden vor der Veröffentlichung erneut geöffnet und geprüft. Grundlage: [PyMuPDF-Seitenbearbeitung](https://pymupdf.readthedocs.io/en/latest/page.html).

Die Dokumentenwerkstatt ist standardmäßig ausgeschaltet. Unter **Einstellungen →
Lumen Files → PDF-Bearbeitung → Dokumentenwerkstatt aktivieren** einschalten und
„Files-Einstellungen übernehmen“ wählen. Erst dann erscheint sie im Menü und im
PDF-Kontextmenü. PDF-Vorschau und Öffnen mit der Standard-App bleiben verfügbar.

### Local photo tools and hardware

- `••• → Bilder nach Motiv suchen` (also from content search): describe an image
  in German or another supported language. The first run prepares a local index
  for the selected folder and its subfolders; later runs reuse unchanged vectors.
  Results show relative motif similarity, not a probability or certainty score.
- Set up the optional image search once in Settings → Einrichtung. The wizard
  downloads a CPU runtime and multilingual CLIP models into the user profile
  (roughly 2 GB download / 2.5 GB installed). Photos and queries stay local.
- `••• → Fotos aufräumen`: review capture-time series, low-detail images and
  screenshots. Nothing is preselected or deleted automatically. Double-click for
  the existing gallery/editor. The normal trash worker rechecks each file's
  identity before moving it. Missing network trash support keeps the original.
- Gallery previews persist locally at 192/640/full-view sizes. A small preview
  appears while the detailed view loads; both neighbors are prefetched. The cache
  is invalidated by file identity/size/timestamps and capped at 512 MiB / 2048
  images. It is disposable under `$XDG_CACHE_HOME/lumen/previews`.
- Settings → Hardware & Aktivität shows available temperatures, fans and power.
  It does not change hardware settings. Game/recorder deferral is enabled by
  default and configurable there, including extra process names. Steam detection
  uses process metadata independent of game/library location; Gamescope, active
  GameMode and common recorder programs are also recognized. An open recorder is
  conservatively treated as busy; Lumen does not claim to know whether it records.
- Scheduled jobs, knowledge indexing and photo analysis honor that policy and the
  existing GPU/pause settings. Photo analysis can explicitly bypass it for one run.
  Interactive file navigation and previews remain available.

Photo analysis skips hidden folders, symlinks, animations and unsupported formats.
It processes regular images up to 128 MiB / 80 MP, at most 10,000 enumerated files
per search or 3,000 per cleanup review. Limits/skipped files are reported. Burst
suggestions require compatible capture metadata and a similar visual fingerprint;
low-detail suggestions can include intentionally soft or plain images. No face
recognition or automatic library import is performed.

Implementation/provenance: Lumen's own native Python code applies the cache and
review concepts explored in Pictus and the Linux telemetry/activity concepts in
Numen. No Numen source was copied (its LICENSE and README disagree). Models are
optional upstream downloads at pinned revisions: [CLIP image encoder](https://huggingface.co/sentence-transformers/clip-ViT-B-32)
and [multilingual text encoder](https://huggingface.co/sentence-transformers/clip-ViT-B-32-multilingual-v1).
Their model cards/licenses are downloaded alongside the safe-tensor weights.
No PostgreSQL, server, Node/Electron runtime or private Pictus/Numen data is needed.


## Lumen Translate

`lumen-translate` opens the native text workbench. **Translate**, **Rewrite** and
**Correct spelling** share a two-pane original/result view. Rewrite stays in the
source language; correction preserves the author's tone and wording. Choose neutral,
professional, casual, friendly or concise style when translating/rewriting. Paste
explicitly, or use `lumen-translate --clipboard`; opening content never starts AI.
Drafts/results are kept in the local app library and can be archived. Defaults live
under Settings → Lumen Translate; both German and English UI use the shared themes.

The shared “Send to Lumen” menu accepts selected text from Wissen, Reader, Inbox and
other apps. Files can send a PDF. Results can return to notes, mail drafts and projects.
Translate records participate in local object search and Vault app backups.

PDF is an additional tab, for documents with a text layer (optional PyMuPDF dependency
in the setup wizard). Original/result page previews and new-file export preserve the
original. Page boxes, images, vector lines and links are retained; fonts may be
substituted or reduced to fit. Always review the output. Scans, annotations, forms,
signatures and rotated text are refused; embedded image text requires separate OCR.
Limits: 12,000 characters per text, 50 MiB / 100 pages / 100,000 characters per PDF.

MCP exposes `lumen_translate_options`, `lumen_translate_text` (modes: translate,
rewrite, correct), and `lumen_translate_pdf`. The PDF tool requires the existing
`LUMEN_MCP_ACTIONS=1` gate and a new absolute output path. Model calls use the current
Lumen provider with tools and memory disabled; no new Translate library entry is
created by MCP. Calls can take up to 150 seconds for text or 240 seconds for PDF;
clients should allow a 300,000 ms MCP timeout. Existing client timeouts are preserved.

Sibling app launches resolve against the running installation, rather than an old
Plasma PATH entry. After a package update, close and reopen older windows to load the
new code; updating does not replace an already running Python process.


The Lumen panel menu lists the shared app catalogue in a compact four/five-column
grid above its task list. App launches use `lumen-panel --open-app <id>` with an
allowlisted app ID. Tasks scroll independently, keep active/input-needed tasks first,
and load older records in batches via `--task-limit` (20 per group initially).
The full task view remains available from the footer.

### Personality

Settings → AI & Speech → Personality provides Guide (default), Professional,
Companion, Sparring partner and Workshop partner. Expand Personalize for persona
and user names, presentation, form of address, closeness, response length,
directness, humor and initiative. The illustrative preview is local and makes no
model call. Voice selection remains separate under Voice & Reading.

The shared OpenCode backend reads the validated `personaProfile` preference at
submission time. Changes apply from the next message in updated Lumen, Search and
Files processes. Conversation options can override the style preset for one chat;
identity remains global. Overrides are stored locally by session ID; new chats use
the global profile. Recovery preserves a choice made before the first message.

Personality does not modify tool permissions, memory consent or model selection.
Initiative is bounded by the user's existing task authorization. Explicit task
formats take precedence; structured file proposals and Translate bypass persona
instructions. Names are length-limited, quoted labels, never instructions.
Individual settings take precedence over the preset's default description.

### Personal learning

Wissen → Memory → About you is a view over the same editable memories, grouped
into preferences, facts and decisions. Corrections and Solutions have their own
filters. Opening a profile entry uses the existing editor, provenance, history and
forget controls; project-specific knowledge stays outside the global profile.

With both memory use and conversation learning enabled, the configured LLM reviews
completed conversation turns in the background. Intent and language are interpreted
by the model, without keyword triggers, a language list or fixed success phrases.
It distinguishes durable corrections from one-off requests and may replace matching
automatic entries. Manually maintained entries are protected by hash checks.

The previous completed assistant answer provides context for user feedback. Only
an LLM-classified explicit success confirmation, a quote from the current user
message and a matching answer ID allow an automatic solution record. Failed or
unfinished answers, other conversations and raw tool logs are not used. Saved
solutions describe conditions and steps; their reuse requires checking the current
situation and does not grant execution permissions. Relevant excerpts remain normal
memory context. This is memory-assisted inference, not model training.

The model receives the current user message, bounded existing-memory candidates
and (when available) the previous answer. Quality depends on the configured model.
The application validates evidence, bounds, scope, consent and conflicting edits;
it does not replace semantic understanding with per-language code. Existing memory
and learning switches remain unchanged by installation.

For recall beyond the initial bounded context, the read-only MCP capabilities
`lumen_memory_list` and `lumen_memory_read` let the agent browse titles/summaries
and choose relevant entries semantically, even when the user's language differs
from the stored memory. Both recheck memory enablement, project scope and forgetting;
private notebook notes are not part of this catalogue. No extra permissions enabled.


### Empfohlene Einrichtung

Der Einrichtungsassistent bietet fünf kurze Schritte mit einem Standardweg.
Assistenz, Vorschauen und Netzwerkfunktionen sind vorausgewählt; bestehende
Komponenten werden wiederverwendet. „Einrichten und weiter“ installiert die
Auswahl und geht nur bei Erfolg weiter. „Ohne Ergänzungen weiter“ überspringt sie.
Unter „Anpassen“ bleiben zusätzliche Komponenten, Modellwahl, Sprachmodelle und
Designs erreichbar. Große Downloads und Desktop-Aktivierung bleiben ausdrücklich
wählbar. Die letzte Seite zeigt Persönlichkeit und Gedächtnis; Änderungen daran
werden erst beim Beenden gespeichert. Bestehende Entscheidungen bleiben erhalten,
bei frischen Profilen ist Lernen aus. Abweichende Änderungen in anderen Fenstern
werden nicht überschrieben. Der Assistent bleibt unter Einstellungen → Einrichtung
und über `lumen-setup-wizard` erreichbar.


### Lumen Studio

Die Desktop-App verwendet eine ruhige Navigation mit Gesprächen, Aufträgen und
Arbeitsräumen. Die fünf letzten tatsächlichen Gespräche stehen direkt darunter; „Mehr laden“
blendet jeweils fünf weitere ein. Apps,
Einstellungen und alle weiteren bisherigen Bereiche bleiben erreichbar. Die
Seitenindizes für CLI/D-Bus bleiben unverändert. Der Chat verwendet native,
selektierbare Nachrichtenflächen und eine kompakte Eingabe mit Kontextmenü,
Sprachgespräch und Senden. Ausgabeaktionen liegen unter „Antwort verwenden“.

Ausgewählte Dateien öffnen rechts die gemeinsame asynchrone Files-Vorschau mit
Bildfilmstreifen, PDF-Seiten, Text sowie Zugang zur bestehenden Bildbearbeitung.
Schließen der Vorschau beendet deren Worker, ohne den Chatkontext zu entfernen.
Auf kleinen Fenstern kann die Vorschau die Gesprächsansicht vorübergehend ersetzen.
Vorschauen ändern keine Dateien und laden keine vom Modell genannten URLs.
Der Chat in Files und die Suche behalten ihre eigenen bisherigen Oberflächen.
Alle vier Themes und Deutsch/Englisch werden unterstützt.
