# Lumen Notes: Platznutzung wie Lumen Projekte

Vom Nutzer am 19.10.2026 freigegeben und gezielt installiert.

Die Vorschau wird aus dem tatsächlichen Notes-Code in einem privaten, vollständig
isolierten Testprofil erzeugt. Es gibt keine separat nachgezeichnete Oberfläche.
Die Installation verwendet dieselben Komponenten und gebauten Ressourcen.

- Tatsächlicher `desktop_design.AppHeader` wie bei `ProjectHome`, mit dessen
  Außenmaßen und 26-Pixel-Titel. Keine zusätzliche globale App-Leiste.
- 24 Pixel seitlicher Außenrand, 224 Pixel Navigation, vorhandene Notizliste und
  die gesamte verfügbare Fensterhöhe. Keine 1700-Pixel-Inhaltsbegrenzung.
- Notizliste auf Nutzerwunsch 10 Pixel breiter: 260 Pixel in der Dreispaltenansicht,
  250 beziehungsweise 210 Pixel in den beiden schmalen Ansichten.
- Notiztext und Notizliste scrollen innerhalb ihres verfügbaren Bereichs.
  Die tatsächliche Formatleiste und Speichern bleiben erreichbar.
- Vorhandener Tag-Befehl über ein aufklappbares Eingabefeld im Notizkopf;
  vorhandene Tags bleiben sichtbar und entfernbar. Datum steht beim Speicherstatus.
- In schmalen Fenstern klappen die Sammlungen auf Anforderung auf. Schriftgrößen,
  Themefarben und Theme-Radien bleiben erhalten. Keine neue Mindestfenstergröße.

Schreiben, Autosave, Konflikte, Freigaben, Notizbücher und native Zusatzwerkzeuge
verwenden unverändert die bestehenden Notes-Befehle. Der gemeinsame Server-Editor
und sein Codec bleiben unverändert. Keine Serverbereitstellung oder Abhängigkeit.

`test_notes_web.py` prüft sechs tatsächliche WebEngine-/Notizbuchwege einschließlich
Native-Header, Fensteraufteilung, Tagformular, Tabellen, Undo/Redo, Speichern,
Konflikten, letzter Eingabe vor Schließen und nativer Zusatzansicht. Fenstergrößen
für die Sichtprüfung: 1920×1400, 1280×800, 960×640 und 840×640 bei Skalierung 1.

Die übernommenen Codecommits sind `f5d5320` und `a511660` (Originale `793fa27`
und `dc65e71`). Sechs Prüfungen gegen Quelle, aktuellen installierten Modulmischstand
und tatsächlich installierte Module bestanden. Neun echte installierte Aufnahmen
über vier Fenstergrößen und vier Themes stimmen in ihren Geometriemessungen mit
der freigegebenen Vorschau überein. Root-Quell-/Sichtprüfung und Nutzerfreigabe
liegen vor; keine separate unabhängige Gegenprüfung behauptet.

Nur `files/notes_web.py`, `files/notes_web/notes.css`, `files/notes_web/notes.js`
und `files/notes_web/server-sources.json` ersetzt. 645 weitere Codeassets und der
Vault-Broker blieben unverändert; die gleichzeitig installierte Code-Popup-Korrektur
bleibt erhalten. Persönliche Notizbücher wurden nicht getestet, persönliche Fenster
nicht beendet. Lumen Notes vollständig regulär schließen und neu öffnen.

Belege und Sicherung: `~/.local/state/lumen/notes-project-layout-20261019/` mit
`verification.json`, `image-manifest.json` und `installed/receipt.json`.
`install-desktop.py rollback` prüft den Rückweg, `rollback --apply` nimmt nur diese
vier unveränderten Notes-Dateien zurück. Vollständige Installation und Rücknahme
auf kleiner Wegwerfkopie bestanden. Vor älteren Notes-/Panorama-Rückwegen nutzen.
Andere Skalierungen, persönliche Geräte und eine vollständige Screenreader-/KWin-
Abnahme sind nicht geprüft. Server und Mobile wurden nicht verändert, kein Push.
