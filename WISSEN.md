# Lumen Wissen

Eine eigene native Wissens-App, erreichbar über das Anwendungsmenü, die Suche
oder `lumen-wissen`. Sie verwendet die vier Lumen-Themes und benötigt für lokale
Notizen kein laufendes OpenCode. **Einrichtung** öffnet den gemeinsamen Wizard.

## Zwei Bereiche

**Mein Bereich** ist dein persönliches Notizbuch. Bestehende und neue Notizen
werden nicht automatisch als Gesprächskontext verwendet. **Diese Notiz für Lumen
freigeben** erlaubt passende Auszüge; **Ordnerfreigaben** gilt für einen ganzen
Unterordner. Eine individuelle Notizregel hat Vorrang. Die Regeln gelten nur für
den bestätigten Notizordner und seine Identität, auch bei einem NAS.

**Lumen-Gedächtnis** liegt immer lokal im Lumen-Zustandsordner unter
`lumen-memory`. Es enthält Vorlieben, Fakten und Entscheidungen, übergreifend
oder bezogen auf ein Arbeitsverzeichnis. Bei jedem Eintrag stehen Herkunft,
Zeitpunkt und gegebenenfalls die zugrunde liegende Nutzeraussage. Automatisch
gelernte und von dir gepflegte Einträge sind unterscheidbar. Du kannst sie wie
Notizen bearbeiten; korrigierte Einträge werden nicht automatisch überschrieben.

**Gedächtnis verwenden** und **Aus Gesprächen lernen** steuern diese Funktionen
getrennt. In frischen Profilen sind beide zunächst aus. Bei aktivierter Nutzung
erhalten spätere Lumen-, Files- und Suchanfragen bis zu sechs passende
Erinnerungen und vier freigegebene Notizauszüge, insgesamt höchstens 18.000 Zeichen.
Inbox kann beim ausdrücklich gestarteten Entwurf ebenfalls Kontext verwenden;
aus Nachrichtentexten wird kein Gedächtnis gelernt. Andere isolierte native
Vorschlagsaufträge und die Quellenfragen in Wissen bleiben bei ihren gewählten
Quellen.

Automatisches Lernen verwendet nach einem erfolgreichen Gespräch eine zusätzliche
Anfrage an denselben eingerichteten Anbieter, der auch in der Cloud liegen kann.
Grundlage ist die ursprüngliche Nutzernachricht, nicht die Lumen-Antwort oder
angehängte Dateien. Nachrichten von 8 bis 6.000 Zeichen mit passenden sprachlichen
Hinweisen werden auf höchstens drei dauerhafte Aussagen geprüft. Jeder Vorschlag
braucht einen wörtlichen Beleg. Die Modellanweisung schließt Geheimnisse,
sensible Profile und zitierte Fremdinhalte aus; typische Zugangsdatenmuster werden
zusätzlich abgewiesen. Eine Modellinterpretation kann dennoch falsch sein:
Herkunft und Bearbeitung bleiben deshalb sichtbar. Es werden keine ganzen Chats
ins Gedächtnis kopiert. Lernfehler verhindern die eigentliche Antwort nicht.

Im Gespräch speichert **Für mich speichern** die Auswahl oder letzte Antwort in
deinem Notizbuch; **Merk dir das** legt sie ausdrücklich im Lumen-Gedächtnis ab.
Diese beiden Speicheraktionen benötigen keinen weiteren Modellaufruf.

**Vergessen** entfernt eine Erinnerung und ihre lokalen Wiederherstellungskopien.
Inhaltsfreie Fingerabdrücke blockieren erneutes automatisches Speichern bekannter
identischer Titel, Texte oder Belege; anders formulierte Aussagen lassen sich
damit nicht vollständig erkennen. Ausdrückliches erneutes Merken bleibt möglich.
Nach Vergessen, Korrektur, Freigabeänderung oder Abschalten beginnt die nächste
Anfrage einen frischen Modellkontext. Frühere Chats und bereits an einen Anbieter
übermittelte Daten werden dadurch nicht rückwirkend gelöscht.

## Schreiben und verbinden

**Neue Notiz** beziehungsweise Strg+N legt eine Markdown-Datei an. Die Suche
durchsucht Titel, Text, Herkunft und `#tags`. Unter **Einfügen** lassen sich
Notizlinks, Bilder und Tags einsetzen. `[[Notizname]]`, `[[datei.md|Anzeigename]]`
und gewöhnliche relative Markdown-Links verbinden Notizen. Mehrdeutige Namen
lassen sich über den vollständigen relativen Dateinamen auflösen.

**Vorschau** zeigt formatierten Text und lokale Bilder. **Bearbeiten** führt zum
Markdown-Editor zurück. **Verbindungen** zeigt ausgehende Links und Rückverweise;
bei schmalen Fenstern bleibt diese Spalte zunächst eingeklappt. **Fokus** blendet
die Seitenleisten aus. Die optionale **Wissenskarte** zeigt die aktuelle Notiz
und bis zu 36 direkte Nachbarn. Ihre Knoten und die Verbindungsliste öffnen die
jeweilige Notiz; die Liste ist auch per Tastatur bedienbar.

**Speichern** oder Strg+S schreibt die Datei. Beim Wechsel der Notiz oder beim
normalen Schließen wird ebenfalls gespeichert. Während des Schreibens wird
nach kurzer Pause ein privater lokaler Entwurf gesichert. Änderungen aus anderen
Editoren werden etwa alle fünf Sekunden erkannt. Bei einem Konflikt bleibt der
Entwurf erhalten: **Externe Fassung laden** verwirft ihn nach Bestätigung,
**Entwurf als Kopie** legt eine zusätzliche Notiz an.

Vor dem Überschreiben oder Entfernen speichert Lumen eine lokale Fassung.
**Wiederherstellen** bringt sie zurück. Diese Kopien sind keine Btrfs-Snapshots
und ersetzen keine Sicherung des Notizordners. Sie werden nicht automatisch
bereinigt und können entsprechend Speicher belegen. Die Aktion **Vergessen** im
Lumen-Gedächtnis entfernt auch diese Fassungen des jeweiligen Eintrags.

## Eigener Ordner und offene Dateien

Beim ersten Start wird `~/.local/state/lumen/wissen` angelegt; `LUMEN_DATA` bzw.
`XDG_STATE_HOME` können den Basisort ändern. **Ordner wählen** öffnet einen
anderen vorhandenen Ordner, etwa unter Dokumente oder auf einem eingebundenen
NAS. Es verschiebt keine Dateien. **Ordner öffnen** zeigt den Speicherort im
Dateimanager. `lumen-wissen "/pfad/zur/notiz.md"` öffnet eine Datei innerhalb des
gewählten Ordners auch im bereits laufenden Fenster.

Notizen sind gewöhnliche UTF-8-Markdown-Dateien. Ein optionaler HTML-Kommentar
hält Herkunft und Übernahme-ID fest. Fremde Frontmatter bleibt als Text erhalten.
Bilder werden bewusst als relative PNG-Anhänge in `attachments` kopiert und bei
Bedarf verkleinert. Obsidian kann denselben Ordner lesen; Obsidian-Plugins,
Canvas-Dateien und spezielle Frontmatter-Auswertungen werden nicht nachgebildet.
Externe Umbenennungen schreiben vorhandene Verknüpfungen nicht automatisch um.

Fehlt das NAS oder wurde der Ordner ersetzt, meldet Lumen den Fehler und behält
den lokalen Entwurf. Nach einem erneuten Einbinden kann **Ordner wählen** den
Speicherort ausdrücklich neu bestätigen. Lumen folgt keinen Symlinks im
Notizordner. Der Scan ist auf 5.000 Notizen, 32 MiB Text und 10.000 Einträge
begrenzt; eine Notiz auf 1 MiB. Überschreitungen erscheinen im Status.

## Fundstellen und Fragen

**Ins Lumen-Wissen** übernimmt in Reader eine gewählte Textstelle oder Markierung
mit Quelle und Seite. In Inbox übernimmt es die Auswahl oder den Nachrichtentext
mit Absender, Datum und Betreff, bis 20.000 Zeichen. **Ergebnis ins Wissen**
übernimmt das ausgewählte Lumen-Auftragsergebnis mit Herkunft. Diese Aktionen
senden nichts an ein Modell.

Im Reiter **Fragen** sucht **Quellen finden** lokal nach passenden Notizen.
Die Häkchen bestimmen, welche davon verwendet werden. Erst **Lumen fragen**
übermittelt bis zu acht frisch gelesene Auszüge von jeweils rund 3.000 Zeichen
an den in Lumen eingerichteten Anbieter. Dieser kann ein Cloud-Anbieter sein.
Andere Dateien und Werkzeuge sind für diese Anfrage gesperrt. Die Antwort wird
mit nummerierten Quellen angefordert; ihre Fundstellen bleiben darunter
anklickbar. Zitate und Aussagen sind prüfbar, aber nicht automatisch verifiziert.
**Antwort als Notiz** speichert die Antwort samt Verknüpfungen zurück.

Bestehende SQLite-Erinnerungen werden beim ersten Öffnen kopiert; die Originale
bleiben in der Datenbank. Wiederholte Starts erzeugen keine Duplikate. Änderungen
aus noch laufenden alten Lumen-Fenstern werden als zusätzliche Fassung übernommen
und überschreiben keine Markdown-Bearbeitung. Gelöschte Notizen entstehen durch
die unveränderte alte Erinnerung nicht erneut.

Entwürfe liegen privat unter dem Lumen-Zustandsordner in `wissen-drafts`, frühere
Fassungen in `wissen-history`. Fensterzustand und letzte Notiz liegen unter
`~/.local/share/lumen-tools/wissen`. Diese Daten gehören nicht ins Quellcode-Repo.
Gedächtnisregister, Freigaben und Einstellungen liegen in der privaten lokalen
Lumen-Datenbank; die Gedächtnisinhalte bleiben Markdown-Dateien.

## Prüfung

`PYTHONPATH=files QT_QPA_PLATFORM=offscreen python3 -m unittest test_memory test_wissen -v`
prüft Bereichstrennung, Freigaben, Lernen, Projektkontext, Vergessen, Abbruch,
Migration, Konflikte, Wiederherstellung, Pfadgrenzen und die native Oberfläche.
Die Modellintegration verwendet einen lokalen Testserver mit synthetischen
Antworten. `python3 tests/check-reader-launch.py` prüft Kalt-/Warmstart
und Notizübergabe mit einem temporären Profil; ein optionales Argument wählt das
Starter-Verzeichnis der installierten Version.
