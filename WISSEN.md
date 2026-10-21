> Historischer Leitfaden zur früheren nativen App-Version. Notes, Vault und Inbox sind jetzt Server-Apps; lokale Sicherungen bleiben in Lumen System. Aktuell: [Desktop-Verantwortlichkeiten](docs/desktop-retirement.md).

# Lumen Wissen

Eine eigene native Wissens-App, erreichbar über das Anwendungsmenü, die Suche
oder `lumen-wissen`. Sie verwendet die vier Lumen-Themes und benötigt für lokale
Notizen kein laufendes OpenCode. **Einstellungen → Lumen einrichten** öffnet den
gemeinsamen Wizard.

## Zwei Bereiche

**Meine Notizen** ist dein persönliches Notizbuch. Bestehende und neue Notizen
werden nicht automatisch als Gesprächskontext verwendet. Die Schaltfläche
**Nur für mich** an der Notiz wechselt beim Anklicken zu **Für Lumen freigegeben**
und erlaubt passende Auszüge; erneutes Anklicken entzieht die Freigabe.
**Einstellungen → Ordnerfreigaben** gilt für einen ganzen
Unterordner. Eine individuelle Notizregel hat Vorrang. Die Regeln gelten nur für
den bestätigten Notizordner und seine Identität, auch bei einem NAS.

**Gedächtnis** öffnet Lumens Erinnerungen und liegt immer lokal im Lumen-Zustandsordner unter
`lumen-memory`. Es enthält Vorlieben, Fakten und Entscheidungen, übergreifend
oder bezogen auf ein Arbeitsverzeichnis. Bei jedem Eintrag stehen Herkunft,
Zeitpunkt und gegebenenfalls die zugrunde liegende Nutzeraussage. Automatisch
gelernte und von dir gepflegte Einträge sind unterscheidbar. Du kannst sie wie
Notizen bearbeiten; korrigierte Einträge werden nicht automatisch überschrieben.

Unter **Herkunft und Optionen** steuern **Gedächtnis verwenden** und
**Aus Gesprächen lernen** diese Funktionen getrennt. In frischen Profilen sind
beide zunächst aus. Bei aktivierter Nutzung
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

Links stehen die beiden Bereiche und Sammlungen, daneben die Notizliste, rechts
die Schreibfläche. **Neu** beziehungsweise Strg+N legt sofort eine Markdown-Datei
an und markiert ihren Titel zum direkten Schreiben. Eine Titeländerung lässt den
Dateinamen bestehen, damit vorhandene Verknüpfungen erhalten bleiben. Markdown-
Frontmatter bleibt erhalten; die erste Hauptüberschrift wird als Titel bearbeitet.

Unter dem Titel stehen Datum und lokale Uhrzeit: **Erstellt** und, bei einem
anderen Zeitpunkt, **Geändert**. Das gilt auch für übernommene Fundstellen und
Gedächtniseinträge; im Profil **Über dich** stehen die Zeitangaben direkt an den
Einträgen. Bei älteren Notizen ohne bekannte Erstellungszeit wird nur die letzte
Dateiänderung angezeigt. Die Zeitangaben gehören nicht zum bearbeitbaren Text.

Die Suche durchsucht Titel, Text, Herkunft und `#tags`. Sammlungen filtern nach
vorhandenen Unterordnern und Tags; im Gedächtnis nach Vorliebe/Fakt/Entscheidung.
**Neue Sammlung** unter „Sammlungen“ legt einen benannten Ordner im Notizbuch an.
Er bleibt auch ohne Notizen sichtbar. Nach Auswahl einer Sammlung erstellt **Neu**
die Notiz in diesem Ordner; bei einer Tag-Sammlung erhält sie den gewählten Tag.
Die ungefilterte Liste zeigt zuletzt bearbeitete Notizen zuerst. Unter **Mehr**
lassen sich Notizlinks, Bilder und Tags einsetzen. **Notiz verknüpfen** zeigt den
aktuellen Notiztitel und den Pfad, sodass auch gleiche Titel unterscheidbar sind.
Die Lesevorschau zeigt bei Links ohne eigenen Anzeigenamen den aktuellen Titel
der Zielnotiz. Dateinamen und bestehende Verknüpfungen bleiben erhalten.
`[[Notizname]]`, `[[datei.md|Anzeigename]]`
und gewöhnliche relative Markdown-Links verbinden Notizen. Mehrdeutige Namen
lassen sich über den vollständigen relativen Dateinamen auflösen.

**Mehr → Lesevorschau** zeigt formatierten Text und lokale Bilder. **Bearbeiten**
führt zum Markdown-Editor zurück. Unter der Notiz lassen sich **Verbindungen und
Herkunft** einblenden; die Details sind zunächst eingeklappt. **Mehr → Fokusmodus**
blendet die Navigation und Notizliste aus. **Wissenskarte** links zeigt die aktuelle Notiz
und bis zu 36 direkte Nachbarn. Ihre Knoten und die Verbindungsliste öffnen die
jeweilige Notiz; die Liste ist auch per Tastatur bedienbar.

Nach etwa einer Sekunde Schreibpause speichert Lumen automatisch. Währenddessen
kannst du weiterschreiben; Cursor und Rückgängig-Verlauf bleiben erhalten.
**Mehr → Jetzt speichern** oder Strg+S schreibt sofort. Beim Wechsel der Notiz oder
normalen Schließen wird ebenfalls gespeichert. Ein privater lokaler Entwurf wird
bereits nach kürzerer Pause gesichert. Änderungen aus anderen
Editoren werden etwa alle fünf Sekunden erkannt. Bei einem Konflikt bleibt der
Entwurf erhalten: **Externe Fassung laden** verwirft ihn nach Bestätigung,
**Entwurf als Kopie** legt eine zusätzliche Notiz an.

Vor dem Überschreiben oder Entfernen speichert Lumen eine lokale Fassung.
**Frühere Fassungen** unter **Mehr** oder **Einstellungen** bringt sie zurück. Diese Kopien sind keine Btrfs-Snapshots
und ersetzen keine Sicherung des Notizordners. Sie werden nicht automatisch
bereinigt und können entsprechend Speicher belegen. Die Aktion **Vergessen** im
Lumen-Gedächtnis entfernt auch diese Fassungen des jeweiligen Eintrags.

## Eigener Ordner und offene Dateien

Beim ersten Start wird `~/.local/state/lumen/wissen` angelegt; `LUMEN_DATA` bzw.
`XDG_STATE_HOME` können den Basisort ändern. **Einstellungen → Notizordner wählen** öffnet einen
anderen vorhandenen Ordner, etwa unter Dokumente oder auf einem eingebundenen
NAS. Es verschiebt keine Dateien. **Einstellungen → Aktuellen Ordner öffnen** zeigt den Speicherort im
Dateimanager. `lumen-wissen "/pfad/zur/notiz.md"` öffnet eine Datei innerhalb des
gewählten Ordners auch im bereits laufenden Fenster.

Notizen sind gewöhnliche UTF-8-Markdown-Dateien. Ein optionaler HTML-Kommentar
hält Herkunft, Übernahme-ID und bei neuen Notizen die Erstellungszeit fest.
Bearbeiten und Wiederherstellen erhalten diese Zeit. Bestehende Dateien werden
beim Öffnen dafür nicht verändert. Fremde Frontmatter bleibt als Text erhalten.
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

## Persönliche Notizen mit Lumen Server abgleichen

Nach der Gerätekopplung im Server die Fähigkeit **Notizen synchronisieren**
freigeben. In **Lumen Wissen → Einstellungen → Serverabgleich …** werden Server,
Konto und persönlicher Ordner angezeigt. Erst **Diesen Notizordner synchronisieren**
aktiviert den Abgleich; bei Installation und Kopplung bleibt er ausgeschaltet.

Markdown-Texte werden mit dem privaten Serverbereich abgeglichen, manuell oder
alle 60 Sekunden bei geöffnetem Wissen. Der Editor bleibt währenddessen nutzbar.
Neue Servernotizen und erhaltene Konfliktfassungen erscheinen in der Sammlung
**Server**. Parallele Änderungen sowie Änderung gegen Löschung behalten die
bearbeitete Fassung; laufende Entwürfe werden nicht überschrieben. Löschungen
werden ebenfalls übertragen, frühere lokale Fassungen bleiben im Verlauf.

Anhänge, Ordnerstruktur, das Lumen-Gedächtnis und Team-Bereiche sind nicht Teil
dieses Abgleichs. Text ist am Server lesbar, keine Ende-zu-Ende-Verschlüsselung.
Maximal 5000 Servernotizen einschließlich Löschmarkern, 200 Titelzeichen und
200.000 Textzeichen. Deaktivieren und Widerruf löschen keine vorhandenen Kopien;
eine neue Gerätekopplung benötigt eine neue Aktivierung.

## Prüfung

`PYTHONPATH=files QT_QPA_PLATFORM=offscreen python3 -m unittest test_memory test_wissen test_wissen_sync -v`
prüft Bereichstrennung, Freigaben, Lernen, Projektkontext, Vergessen, Abbruch,
Migration, Konflikte, Wiederherstellung, Pfadgrenzen und die native Oberfläche.
Die Modellintegration verwendet einen lokalen Testserver mit synthetischen
Antworten. `python3 tests/check-reader-launch.py` prüft Kalt-/Warmstart
und Notizübergabe mit einem temporären Profil; ein optionales Argument wählt das
Starter-Verzeichnis der installierten Version.
