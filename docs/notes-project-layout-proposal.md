# Lumen Notes: Platznutzung wie Lumen Projekte

Vorbereiteter Vorschlag vom 19.10.2026, noch nicht installiert.

Die Vorschau wird aus dem tatsächlichen Notes-Code in einem privaten, vollständig
isolierten Testprofil erzeugt. Es gibt keine separat nachgezeichnete Oberfläche.
Bei einer Übernahme werden dieselben Komponenten und gebauten Ressourcen genutzt.

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
