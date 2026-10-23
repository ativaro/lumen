> **Historischer Entwurf oder Abnahmebeleg – keine aktuelle Installationsanleitung.** Die frühere Richtungsentscheidung ist historisch. Für neue und geänderte Oberflächen gilt Panorama; vorhandene Panelrollen bleiben plattformgerechte Einstiege. Aktuelle Zuordnung: [Desktop-Verantwortlichkeiten](docs/desktop-retirement.md).

# Lumen-Inseln

Freigegeben am 2026-10-01: Entwurf 2 mit dem gemeinsamen Systemmenü aus Entwurf 3.

- Drei schwebende Plasma-Leisten pro vorhandenem oberen Bildschirmrand:
  Lumen/Dateien/Anwendungen links, KRunner-Suche mittig, Aufgaben/Systemablage/Uhr rechts.
- Gemeinsames Menü: echte gemeinsame Aufgaben, Netzwerk-Einstieg, Lautstärke und
  Stummschaltung, Bildschirmhelligkeit, Nicht stören, Einstellungen und Sperren.
  Bestehende KDE-/PipeWire-Dienste verwenden; keine simulierten Statuswerte.
- Vorhandene Systemablage, Uhr und Anwendungsstarter samt Super-Taste erhalten.
  Unteres Dock, offene Anwendungen und bestehende Aufgaben erhalten. Kein Neustart
  von Plasma/KWin. Layout und Widgetkonfiguration vor dem Umbau sichern.
- Gleiches vorhandenes Lumen-Applet in verschiedenen Rollen; kompatibler Standard
  bleibt das bisherige Aufgabenmenü. Suche öffnet den vorhandenen KRunner inklusive
  Lumen-Runner. Netzwerkdetails verwenden die nativen KDE-Einstellungen.
- Fehler und nicht verfügbare Regler sichtbar; Tastatur, Klartext, kompakte Breite
  und Statusaktualisierung prüfen. Tests ausschließlich in temporärem Zustand.
- Erst isoliert prüfen und installieren, danach beide vorhandenen oberen Leisten
  live umbauen und auf doppelte Widgets, Überlappungen und Fehler kontrollieren.

Technische Grundlage: [KDE Panel-Scripting](https://develop.kde.org/docs/plasma/scripting/api/)
und die auf diesem System installierten QML-Typinformationen.

## Gestalterische Korrektur nach Nutzerfeedback

Die erste Umsetzung war zu kleinteilig und funktional. Die verbindliche Vorlage
besteht aus drei runden Inseln mit einem gemeinsamen Systemmenü.
56 px hohe, sichtbar gefüllte runde Glasinseln; größere Schrift, konsistente helle
Linienicons, türkisfarbene Akzente, großzügige Abstände und flache Menüaktionen.
Der alte Plasma-Stil hatte im north-Präfix vollständig transparente Flächen.
`plasmoid/install-island-style.py` erzeugt deshalb einen ableitenden Benutzerstil
LumenIslands, erhält LumenDark und das Dock-Artwork. Keine globale Schriftänderung.


## Unteres Dock: freigegebene Variante 2 (2026-10-01)

Zwei getrennte Inseln für Anwendungen und virtuelle Arbeitsflächen.
Bestehender nativer Icons-only Task Manager bleibt im Dock, rechts daneben eine
kleine separate Insel mit nummerierten virtuellen Arbeitsflächen. Graphitflächen,
runde Ecken, türkise Aktivitätsmarkierungen. Bestehende Launcher, Rechtsklick,
Fenstervorschauen und Ausblendverhalten erhalten. Keine zweite Uhr oder Suche.
Native Plasma-Panels und Pager nutzen; keine eigene Taskmanager-Implementierung.
Das Paar bleibt auf dem bisherigen Dock-Bildschirm. Positionen müssen ohne
Überlappung auch bei wechselnder Appzahl funktionieren. Desktopkonfiguration und
Stil vor Änderungen sichern; gezielten Rückweg bereitstellen. Native Darstellung,
Arbeitsflächenwechsel sowie Rückkehr zur ursprünglichen Arbeitsfläche prüfen;
keine Benutzeranwendungen oder Plasma/KWin neu starten.
