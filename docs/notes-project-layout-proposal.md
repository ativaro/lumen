> **Historischer Entwurf oder Abnahmebeleg – keine aktuelle Installationsanleitung.** Die beschriebenen nativen Notes-/Projekteditoren sind nicht mehr die ausgelieferte App. Für die gemeinsame Oberfläche gilt der Server-Host und Panorama. Aktuelle Zuordnung: [Desktop-Verantwortlichkeiten](desktop-retirement.md).

> Historischer Stand des entfernten nativen Notes-Editors. Aktuell: [Desktop-Verantwortlichkeiten](desktop-retirement.md).

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


## Korrektur: Scrollbar am Spaltenrand (19.10.2026)

Der zusätzliche rechte Innenrand von16px neben der Notizlisten-Scrollbar wurde
entfernt. Suche und Listenaktionen behalten ihren Abstand; Notiztext erhält16px
mehr Breite, die Spalte bleibt260px. Regression reproduziert16px, danach0px.
Code0667a2f (Original17117bc): sechs Fälle gegen aktuellen RuntimeMix und sechs
gegen installierte Module bestanden; sieben echte Aufnahmen über vier Größen und
vier Themes, Editor-Geometrie unverändert. Zwei Runtime-Dateien ersetzt,647 andere
Codeassets und Vault-Broker unverändert. Belege/Sicherung: ~/.local/state/lumen/
notes-scrollbar-gutter-20261019/verification.json. install-desktop.py rollback
[--apply] geprüft; vor dem vorherigen Notes-Layout-Rückweg verwenden. Persönliche
Fenster und Notizbücher nicht getestet/verändert; kein Push.


## Korrektur: einmalige Kopfaktionen und sicheres Beenden (19.10.2026)

Zwei benachbarte Kopfaktionen verwendeten denselben React-Schlüssel. Nach vier
Notizwechseln blieben fünf Tag-Schaltflächen stehen. Die statischen Kopfaktionen
benötigen keine Schlüssel; der neue echte WebEngine-Test prüft acht Wechsel mit
geöffnetem Tagformular und Mehr-Menü. Mehr verwendet ein fenstereigenes natives
Menü mit den bisherigen drei Aktionen; frühere Fassungen bleiben in der
Schreibansicht. Native Zusatzmenüs gehören dem Fenster, damit Hintergrundaufträge
sie beim Deaktivieren der versteckten alten Ansicht nicht ungültig schalten.

Die vorhandene globale Fensterbereinigung löschte außerdem das parentlose
QCompleter-Popup vor dessen Besitzer. Die Bereinigung überlässt Qt-Popups und
Tooltips ihrem Besitzer. Eine unabhängige Gegenprüfung bestätigt Ursache und
private A/B-Reproduktion; Starttests prüfen die tatsächliche Freigabe von Notes,
Editor und QCompleter nach dem Ereigniszyklus. Keine ToolbarStyle-Änderung nötig.

Sieben Notes-Prüfungen und beide echten Starttests bestanden im privaten Profil;
zusätzlicher vollständiger Anwendungsschluss mit dem aktuellen Runtime-Mischstand
endet mit Status0. Sieben echte Aufnahmen über vier Größen und vier Themes zeigen
je eine Kopfaktion, ohne zusätzlichen Scrollbar-Abstand. Server und Mobile bleiben
unverändert. Belege und begrenzter Installer/Rückweg:
`~/.local/state/lumen/notes-header-controls-20261019/`.
Die Runtime-Fassung von app.py enthält ausschließlich den Bereinigungsfix auf der
aktuellen installierten Basis; noch nicht installierte Files-Quelländerungen werden
nicht mit übernommen. Persönliche Fenster und Notizbücher sind keine Testprofile.

Installationsabnahme: Code `f4c7df3` (Original `57779a0`). Fünf Runtime-Dateien
mit Sicherung ersetzt, 649 andere Codeassets und Vault-Broker unverändert.
Sieben installierte Notes-Fälle, sieben echte installierte Aufnahmen und echter
Anwendungsschluss mit Freigabe aller drei Besitzerobjekte bestanden. Rücknahme
auf Wegwerfkopie und installierter Rückweg als Trockenlauf geprüft. Normal neu
öffnen; persönliche Fenster wurden nicht beendet. Abnahme:
`~/.local/state/lumen/notes-header-controls-20261019/verification.json`.
