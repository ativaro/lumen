# Lumen Notes Desktop: Servergestaltung

Die normale Schreibansicht verwendet den unveränderten Server-Editor
(`note-editor.tsx`, `note-rich-document.ts`), DM Sans, Lucide und die originalen
Stylesheets `style.css`, `panorama.css`, `knowledge.css` und `appearance.css`.
Seitentitel, Navigation, Notizliste und Schreibfläche verwenden deren originale
Panorama-Regeln. Die vier gemeinsamen Themes folgen weiterhin der Desktop-Auswahl.
Native Werkzeugdialoge und das
Fensterdekor bleiben Desktop-Elemente. Die bisherigen lokalen KI-Freigaben werden
beibehalten; es wird keine Server-Freigaberegel simuliert.

Seit dem 19.10.2026 ersetzt der vollständige Server-Snapshot die zuvor separat
nachgebildeten Desktop-Styles. Quelle ist der bereitgestellte Serverstand
`bb8a87a844ac257969d141e5aeac113d5bac6381`; die sieben übernommenen Komponenten/
Styles stimmen mit dessen Release-Manifest überein. Die DM-Sans-Schriften werden
aus demselben vorhandenen Fontsource-Paket lokal gebündelt. Eine ausdrücklich
gewählte andere Desktop-Schrift bleibt erhalten.

`src/desktop.css` enthält nur die lokale Anbindung und Bedienkorrekturen: native
Werkzeugmenüs, erreichbare lange Tags/Linkaktionen und den schmalen Fensteraufbau.
Unter 1200 Pixeln verhindert sie eine leere dritte Spalte aus einer späten
Server-CSS-Regel. Es gibt keine zusätzliche globale App-Leiste. Lokale KI-Freigaben,
Einstellungen und Dialoge bleiben bewusst Desktop-Bedienwege.

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
