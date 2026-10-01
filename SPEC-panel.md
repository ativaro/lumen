# Lumen im Plasma-Panel

Freigegebene erste Ausbaustufe vom 2026-10-01: vorhandenen Lumen-Starter durch ein
echtes Plasma-Menü mit gemeinsamer Aufgabenanzeige ersetzen.

- Klick und Tastatur öffnen ein kompaktes Menü in KDE-Farben. Laufende Aufträge,
  wartende Rückfragen und letzte Ergebnisse stammen aus derselben privaten
  Datenbank wie Lumen und Files; keine zweite Auftragsverwaltung.
- Ergebnisse lassen sich direkt aufklappen. Native Schritte zeigen echten
  Fortschritt; KI-Aufträge einen laufenden Status ohne erfundene Prozentzahl.
- Direkte Einstiege zu Dateien, Systemstatus, Aufträgen und Einstellungen;
  ein gewählter Auftrag wird im vorhandenen Hauptfenster ausgewählt, ohne
  automatisch etwas auszuführen oder einen Gesprächsentwurf zu ersetzen.
- Statusabfrage ausschließlich lesend, begrenzt und mit kurzer Sperrwartezeit;
  leere Datenbank, Lesefehler und veralteter Ausführungsstatus sichtbar behandeln.
  Titel/Ergebnisse als Klartext, keine Shell-Interpolation ihrer Inhalte.
- Der bestehende KDE-Starter wird nach erfolgreichem Bau und Prüfung gezielt
  durch das Applet am gleichen Ort ersetzt; Panel-Konfiguration vorher sichern.
  Plasma/KWin und offene Lumen-/Files-Fenster bleiben aktiv.
- Prüfen: Auftragsänderungen aus getrennten Schreibern, Fehler/Leerdaten,
  Sonderzeichen und begrenzte Ergebnisse; native Qt-Quick-Tastaturbedienung,
  kleines Menü und Themes; Paket bauen, installieren und live aktivieren.

Die Hintergrund-Lebensdauer von KI-Aufträgen, eine gemeinsame Engine und neue
KRunner-Aktionen gehören zu den später vorgeschlagenen Ausbaustufen.
