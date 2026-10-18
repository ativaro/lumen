# Lumen Code: lesbare Aktionen und kleine Fenster

Kandidat, nicht installiert oder veröffentlicht. Basis ist
`29d08e3b1c438952be706ddac5e71d28640a4236`.
Soll ist [Panorama](standard.md), insbesondere die spätere native Präzisierung:
24 Einheiten Außenrand, Bedienung 14, eigene Bearbeitungsansichten ohne eine
zweite Sammlungsnavigation. Die bestehenden gewählten Inhaltswege bleiben
Werkzeug Ein-/Ausgabe, Code Projektquelle und App Auftrag neben Vorschau.

## Konkrete Befunde und Korrekturen

- Die App-Bearbeitung zeigte noch die alte Sammlungsnavigation. Deren Einträge
  schlossen lediglich den Dialog; „Vorhandene kleine Apps“ wurde abgeschnitten.
  Die App verwendet nun den vorhandenen Editoraufbau und „Zur Sammlung“.
  Breite Fenster behalten Auftrag und echte Vorschau nebeneinander; schmale
  Fenster erlauben das Scrollen zur Vorschau. Prüfbeispiele, Datenübernahme,
  Quellcode, Entwürfe und frühere Fassungen bleiben erreichbar.
- Die Beispielbuttons hatten eine eigene 11-Pixel-Schrift und kleine native
  Einstellknöpfe. Sie verwenden nun die vorhandene Code-Aktionsgestaltung;
  Modus-/Versionswahl übernimmt die normale Bedienungsschrift.
- `codeLink` hatte keinen horizontalen Innenraum; beim Fokus nahm der breitere
  Rahmen zusätzlich Platz weg. Acht Einheiten Innenraum und ein gleich breiter
  sichtbarer Fokusrahmen erhalten den Text.
- Verborgene Erstellungs-/Detailseiten und der Leerzustand erzwangen unnötige
  Mindesthöhen. Die betreffenden Inhalte scrollen nun im bestehenden Seitenraum;
  die Erstellung reserviert einen verkleinerbaren Formularbereich. Prüfung und
  Rückweg bleiben am unteren Rand erreichbar. Die Projektquellwahl kann bei
  langen Beschriftungen vertikal stehen.
- App-Daten und Prüfbeispiele verwenden denselben Editorrahmen, 24 Einheiten
  Außenrand und scrollbar bleibende Felder mit stets erreichbarem Schließen.

Keine Änderung an Ausführungsrechten, Backend, Datenformat, persönlichen Daten,
Startern oder Startschutz. Keine Änderungen an Generals geteilten Dateien.
Der eigene App-HTML-Inhalt wird weiterhin unverändert angezeigt; sein internes
Design wird nicht durch eine ungefragte Theme-Injektion überschrieben.

## Prüfung und Übergabe

111 bestehende/gezielt ergänzte Code-Prüfungen bestanden. Die neuen Fälle
prüfen kleine Erstellung mit sichtbarer Validierung/Prüfaktion, eine kleine
leere Sammlung und die App-Bearbeitung ohne tote Navigation sowie mit lesbaren
Beispielaktionen. Bestehende App-Fälle prüfen echte WebEngine-Eingaben,
Prüfbeispiele, Speichern/Verwerfen, Wiederöffnen und Konfliktschutz weiter.

Echte unveränderte Qt-Aufnahmen: normale Fenster 1280×800 in vier Themes;
zusätzlich Graphit DE/EN mit 960×640, große App-Bearbeitung 1600×1000,
App-Daten/Prüfbeispiele 660×640; gezielte 125-Prozent-Atelier/EN- und
150-Prozent-Glas/DE-Aufnahmen. Formularfehler und Scrollende sind enthalten.
Keine vollständige Kombination aller Ansichten/Themes/Sprachen/Skalierungen.
Alle Datenpfade und HOME/XDG sind temporär; privater D-Bus sowie getrennte
PID-/Netz-Namensräume. Kein persönliches Fenster wurde getestet oder beendet.

Belege, genaue Bildliste, Hashes und Prüfprotokolle:
`~/.local/state/lumen/code-ui-fit-20261019/`.
Root muss die echten Bilder abnehmen; General integriert erst danach.
Kein Installations- oder Push-Schritt in diesem Kandidaten.

Offen außerhalb dieses Bereichs: Die eingebettete Gesprächsansicht übernimmt
weiter ihre geteilten `studio.qss`-Aktionen (u.a. 10/11-Pixel-Metadatenaktionen).
Eine appübergreifende Anpassung gehört zu General, nicht in diesen Code-Patch.
Kein neuer Modell-/Dienstaufruf, kein physischer Compositor-/Screenreader-Test
und keine neue Sicherheitsabnahme werden behauptet.
