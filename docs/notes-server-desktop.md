# Lumen Notes Desktop: Servergestaltung

Die normale Schreibansicht verwendet den unveränderten Server-Editor
(`note-editor.tsx`, `note-rich-document.ts`), DM Sans, Lucide und die originalen
Stylesheets `style.css`, `panorama.css` und `knowledge.css`. Die Desktop-Hülle
ordnet Sammlungen, Notizliste, Titel, Tags und Speicherzeile nach diesem Layout an.
Notes verwendet dabei die Server-Graphitfarben. Native Werkzeugdialoge und das
Fensterdekor bleiben Desktop-Elemente. Die bisherigen lokalen KI-Freigaben werden
beibehalten; es wird keine Server-Freigaberegel simuliert.

Alle Ressourcen werden lokal geladen. Es gibt keinen lokalen HTTP-Server,
keine Browseranmeldung und keinen neuen Serverzugriff. CSP und Request-Interceptor
beschränken die Seite auf ihre drei lokalen Laufzeitdateien, Qt WebChannel und
gebündelte Schriftdateien. Fremde Navigation, Downloads, Geräteberechtigungen,
Sitzungs-/Browserspeicher und programmatische Zwischenablagezugriffe sind gesperrt.
Unbekannte Markdown-Inhalte bleiben durch den Server-Codec geschützt erhalten.

`notes_web.py` verbindet die Seite mit dem bestehenden `Wissen`-Fenster. Notizordner,
Schreiben, automatische Speicherung, private Entwürfe, Konflikte, Versionen,
Freigaben, Synchronisation und Dateiprüfungen verbleiben in der nativen Logik.
Notiz-/Ordnerwechsel entwerten alte Editorantworten; Eingabefolgen verhindern,
dass eine ältere Rückmeldung neue Eingaben ersetzt. Vor Schließen wird die letzte
Browserfassung abgefragt und der normalen Speicherung übergeben. Die Notizliste
lädt zunächst 100 Einträge, weitere auf Anforderung. Unveränderte Zustände werden
nicht erneut serialisiert. Bei einem Rendererabbruch ist die native Ansicht mit
den bereits übergebenen Eingaben erreichbar.

Unter **Mehr** / **Einstellungen** bleiben die bisherigen Desktop-Werkzeuge
zugänglich, einschließlich Quellen, Projektwissen, Dateiverschieben und Abgleich.
**Lumen Notes** oberhalb der nativen Werkzeuge führt zur Server-Schreibansicht.
Ohne das bereits optionale Qt WebEngine bleibt der native Editor nutzbar.
`LUMEN_NOTES_NATIVE=1` ermöglicht dessen isolierte Regressionstests.

## Ressourcen bauen

Die kopierten Serverquellen liegen in `files/notes_web/src/`; ihre Hashes stehen
in `server-sources.json`. Aktualisierungen werden gezielt aus dem Serverrepo
übernommen und erneut geprüft. Der Build verwendet ausschließlich dessen bereits
installierte, gesperrte Bibliotheksstände und lädt nichts herunter:

```sh
node scripts/build-notes-web.mjs /pfad/zu/lumen-server/web
```

`notes.js`, `notes.css`, `index.html`, Lizenztexte und Abhängigkeitsmanifest werden
mitgeliefert; Node ist zur Nutzung nicht erforderlich. Installer und Archpaket
nehmen den Ressourcenbaum mit auf. Lizenzen: `files/notes_web/NOTICES.txt`.

## Prüfung

`test_notes_web.py` bedient echtes lokales Chromium und künstliche Notizbücher:
Formatierung/Tabellen, leere Spalten, Tags, Undo/Redo, Speichern/Wiederöffnen,
840–1440 Pixel, Notizwechsel mit verspäteter Eingabe, externer Konflikt, letzte
Eingabe vor Schließen, Navigationssperre und native Zusatzwerkzeuge. Vorhandene
Notes-Suiten werden zusätzlich gegen den nativen Pfad ausgeführt. Kein persönliches
Notizbuch oder persönliches Desktop-Fenster dient als Testprofil.
