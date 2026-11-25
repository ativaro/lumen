> **Historischer Entwurf oder Abnahmebeleg – keine aktuelle Installationsanleitung.** Der frühere lokale Notes-Editor und sein eigener Notizabgleich sind stillgelegt. Das lokale Gedächtnis bleibt getrennt erhalten; Notes verwendet den Server-Host. Aktuelle Zuordnung: [Desktop-Verantwortlichkeiten](docs/desktop-retirement.md).

# Lumen Wissen

Vom Nutzer angenommener Umfang: eigenständige native Wissens-App mit offenem
Markdown-Ordner, angenehmem Editor/Vorschau, Bildern, Tags, internen Links und
Rückverweisen, optionaler Wissenskarte und Fragen mit ausgewählten Quellen.
Übernahme aus Reader, Inbox und Lumen-Ergebnissen; bestehende Erinnerungen erhalten.

## Aufbau und Reihenfolge

1. `wissen_data.py` (seit R10 nur noch die Anbindung; Notizbuch-Kern, Tags, Eigenschaften und Überschriften
   liegen in `lumen-service`, `native/service/src/notebook.rs`): Markdown ist die Quelle der Wahrheit. Private lokale
   UI-Einstellungen und ein abgeleiteter Suchkatalog dürfen SQLite verwenden.
   Gewählter Ordner wird nicht verschoben; bestehende Dateien bleiben unverändert.
   Atomare Schreibvorgänge, Hash-Konfliktprüfung, Wiederherstellungskopien und
   private lokale Entwürfe schützen vor paralleler Bearbeitung und Ausfällen.
2. `tools_wissen.py`: ToolWindow/Job/Theme wiederverwenden, Bibliothek links,
   Schreiben/Lesen in der Mitte, Verbindungen und Quellen rechts. Tastaturaktionen,
   sichtbarer Speicherstatus, Wiederherstellung von Entwürfen. Reine Qt-Widgets.
3. `wissen_views.py`: lokale, eingeschränkte Markdown-Vorschau und native Karte;
   ausgewählte Textauszüge mit Zitaten an bestehenden OpenCode-Backend senden.
   Keine automatische Modellanfrage, keine versteckten Dokumentuploads.
4. Store-Brücke und explizite Übernahmeaktionen; Starter, Installer, Paket,
   Bedienungsanleitung, Benutzerinstallation, privates Git und Systemreferenz.

## Datenvertrag

Notizen sind UTF-8 `.md`, mit sichtbarer Überschrift, gewöhnlichen Markdown-/
Wikilinks und `#tags`. Ein optionaler HTML-Kommentar enthält Lumen-ID und Herkunft;
alle Notizen bleiben auch ohne diesen Kommentar lesbar. Fremde Frontmatter bleibt
als Text erhalten. Bilder werden bewusst in einen relativen Anhängeordner kopiert.
Kein Zugriff durch Symlinks oder Pfade außerhalb des gewählten Ordners.

Einträge zeigen Datum und lokale Uhrzeit dezent unter dem Titel. Neue Notizen
speichern die Erstellungszeit als UTC-Unixzeit im vorhandenen Lumen-Kommentar;
Bearbeiten und Wiederherstellen erhalten sie. Die Änderungszeit stammt aus der
gelesenen Datei. Ohne belegte Erstellungszeit wird nur „Geändert“ angezeigt;
bestehende Dateien werden dafür nicht nachträglich umgeschrieben. Bekannte
Erstellungszeiten älterer Gedächtniseinträge bleiben als Anzeigequelle nutzbar.
Zeitstempel gehören nicht in den editierbaren Text und erscheinen auch bei
Profil-Einträgen. Speichern ohne Inhaltsänderung verändert den Zeitpunkt nicht.

Vorhandene SQLite-Erinnerungen werden idempotent kopiert, niemals aus ihrer
Ursprungsdatenbank entfernt. Nach Aktivierung arbeiten neue Store-Aufrufe auf den
Markdown-Dateien. Späte Änderungen aus noch laufenden alten Lumen-Fenstern werden
verlustfrei als aktualisierte Kopie oder zusätzliche Konfliktkopie übernommen.
Gelöschte Markdown-Notizen werden durch die Übernahme nicht wieder angelegt.

Bei externen Änderungen bleibt ein eigener ungespeicherter Entwurf erhalten.
Konflikte bieten Neu laden oder Als Kopie speichern, kein blindes Überschreiben.
Ein anderer Wissensordner wird ausdrücklich gewählt; vorhandene Notizen werden
nicht automatisch dorthin verschoben. Eine fehlende NAS-Verbindung darf keine
leere Ersatzbibliothek oder automatische Datenlöschung erzeugen.

## Grenzen und Abnahme

Standardbibliothek plus vorhandenes PySide6, keine neue Cloud oder Notiz-Engine.
Scanner begrenzt auf 5.000 Notizen/32 MiB Text/10.000 Verzeichniseinträge; native
Dateiarbeit in abbrechbaren Jobs/Unterprozessen. Vorschau lädt keine entfernten
Bilder, Skripte oder lokalen Dateien außerhalb des Notizordners. Graph zeigt einen
überschaubaren Ausschnitt mit klickbaren Verbindungen.

Prüfung: Migration/Wiederholung/späte Altversionen, externe Bearbeitung und
Konfliktkopien, Unicode/Links/Tags, Symlink-/Pfadgrenzen, Löschen/Wiederherstellen,
Entwürfe nach Neustart, Quellenübernahme und begrenzte KI-Kontexte. Native UI in
allen vorhandenen Themes, Kalt-/Warmstart, vollständige isolierte Python-Suite,
12 QML-Checks, Paket-/Installationsvergleich. Keine persönlichen Inhalte ins Git.

Befehle: `PYTHONPATH=files QT_QPA_PLATFORM=offscreen python3 -m unittest files/test_wissen.py -v`,
`python3 -m unittest discover -s files -v`,
`/usr/lib/qt6/bin/qmltestrunner -input plasmoid/tests -platform offscreen`,
`./packaging/arch/build-package.sh`, `./install.sh --no-timer --no-mcp`.
Code folgt den vorhandenen ToolWindow/Library/Job-Konventionen; keine Änderung
an aktiven Benutzersitzungen oder Cloud-Konten und keine persönlichen Beispieldaten.

## Angenommener Bedienentwurf 1: Direktes Notizbuch

Der Nutzer wählt „Direktes Notizbuch“: dauerhafte Navigation für persönliche
Notizen und Gedächtnis, daneben Notizliste, rechts eine ruhige Schreibfläche.
Keine große Einstiegsüberschrift, kein Bereichs-Dropdown und keine permanente
Werkzeug-/Metadatenwand. Titel direkt bearbeiten, neue Notiz ohne Titeldialog,
automatisch nach kurzer Schreibpause speichern. Vorhandene Ordner erscheinen
als Sammlungen; keine künstlichen Beispielordner. Quellen, Verknüpfungen,
Versionen, Gedächtnisoptionen, Vorschau, Karte und Fragen bleiben erreichbar.
Freigabe privat/geteilt unmittelbar an der Notiz sichtbar und änderbar.

Autosave verwendet die vorhandene atomare Hash-Prüfung und Entwurfssicherung.
Während des Schreibens bleiben weitere Eingaben möglich; Rückmeldungen dürfen
weder neueren Text noch Cursor/Undo ersetzen. Navigation und Schließen warten
auf den Schreibvorgang. Bei Konflikten bleibt der lokale Entwurf erhalten.
Markdown, Frontmatter, Herkunft und externe Verknüpfungen werden erhalten;
eine Titeländerung benennt die Datei nicht ungefragt um.

Abnahme: verzögerte Schreibvorgänge mit weiteren Eingaben, Wechsel/Schließen,
externe Konflikte, Titel und Frontmatter, Bereichstrennung und Freigaben sowie
native Darstellung in vier Themes bei 840/1180/1440 Pixeln. Bestehende Quellen-,
Karten-, Vorschau- und Startprüfungen bleiben gültig. Paket38, Benutzerbundle,
private Git-Quellen und Systemreferenz aktualisieren; keine persönlichen Daten.

## Bedienkorrektur: Sammlungen und Linktitel

„Neue Sammlung“ ist im persönlichen Bereich direkt unter Sammlungen sichtbar.
Anlegen erzeugt einen normalen Unterordner, auch leere Ordner bleiben nach
erneutem Scan/Start sichtbar. „Neu“ respektiert den ausgewählten Ordner, Tag
oder Gedächtnistyp. Beim Wechsel wird zuvor weiter automatisch gespeichert.
Die Verknüpfungsauswahl zeigt den bearbeiteten Titel sowie den eindeutigen Pfad.
Links verwenden relative, kodierte Ziele; ihre Vorschau zeigt den aktuellen
Titel, sofern kein eigener Anzeigename gesetzt ist. Keine automatische
Dateiumbenennung, neue Laufzeitabhängigkeit oder Änderung persönlicher Daten.
Prüfung: leere Sammlung, erste Notiz, Wechsel/Autosave, doppelte Titel,
ordnerübergreifende Links, ungültige Pfade und Symlinks sowie native Darstellung.
