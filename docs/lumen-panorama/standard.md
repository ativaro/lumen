# Lumen Panorama

Status: verbindlicher Designstandard seit 18.10.2026 für Lumen Desktop, Server und Mobile.

Nutzerentscheidung: „ok it is panorama ab jetzt für lumen desktop, server und mobile immer so umsetzzen“.

## Referenz und Zweck

[Freigegebene interaktive Referenz](reference.html): **Panorama** auswählen. Die drei anderen Entwürfe bleiben ausschließlich zum historischen Vergleich enthalten. Die vier Themes sind Glas, Graphit, Atelier und Mitternacht.

Die Referenz soll die bisherige Lücke zwischen Entwurf und implementierter Oberfläche schließen. Sie zeigt gemeinsame Proportionen, Navigation, Bausteine und Zustände anhand synthetischer Inhalte. Sie ist kein Nachweis implementierter Produktfunktionen. Native Plattformen verwenden ihre vorhandene Technik; sie teilen Gestaltung und Bedienprinzipien.

Diese Vorgabe gilt für neue und überarbeitete Oberflächen. Bestehende Ansichten werden im jeweiligen Änderungsschritt angeglichen. Eine vollständige Migration oder Veröffentlichung ist damit nicht automatisch erfolgt oder beauftragt. Historische Entwürfe und ältere Implementierungsberichte überschreiben diesen Standard nicht.

## Aufbau und Bedienung

- Auf breiten Ansichten: gut sichtbare App-Navigation oben, links die zum Inhalt passende Navigation, Hauptinhalt mit deutlichem visuellen Vorrang. Auf kleinen Ansichten wird die Navigation platzsparend und nativ zugänglich; keine verkleinerte Desktop-Dreispaltenansicht erzwingen.
- Gespräche sind der leicht erreichbare Hauptweg. Links zunächst die fünf neuesten Gespräche und „Mehr laden“. Eine finale Antwort erscheint einmal im Gespräch. Die schmale, schließbare Nebenansicht zeigt ausschließlich **Arbeitsschritte**. Werkzeugaufrufe werden kompakt zusammengefasst und bei Bedarf aufgeklappt.
- Technische Aufträge treten in den Hintergrund: „Alle Aufgaben“ beziehungsweise die vorhandene Diagnoseansicht dient Fortschrittskontrolle und Troubleshooting. Keine dominante zweite Aufgabenübersicht über dem eigentlichen Inhalt.
- Projekte fassen Vorhaben, Aufgaben, Materialien und Gespräche zusammen. Aufgaben können Recherche, Analyse oder Automation sein. Datei, Notes-Notiz und Weblink sind gleichwertig auffindbare Materialarten. Neue Elemente erhalten einen passenden dedizierten Seiteneditor; alte generische Untermenüs nicht darüberlegen.
- Es gibt keine globale Arbeitsraum-/Workspace-Auswahl. Projekte sind kein umbenannter globaler Arbeitsraum. Bei Migrationen bleiben Daten, Zuordnungen und Rechte erhalten; notwendige Kompatibilität ausdrücklich dokumentieren.
- Reader und Übersetzungs-/Textbearbeitung sind aus Gesprächen erreichbar. Audio-Funktionen folgen der gemeinsamen Bezeichnung **Audio Studio**. Vault und Sicherungen bleiben auffindbar; Sicherungen berücksichtigen insbesondere Drive und Photos.
- Drive berücksichtigt Auswahl, Alles auswählen, Verschieben und kompakte anpassbare Übertragungsanzeigen. Photos berücksichtigt Sammlungen, Entdecken mit Personen/Orten/Motiven und geschützte Fotos. Diese Referenzwege definieren ihre Darstellung; tatsächliche Verfügbarkeit und Schutz werden separat nachgewiesen.
- Funktionen dort anbieten, wo Inhalt und nächste Handlung zusammenpassen. Keine zusätzlichen allgegenwärtigen „Verbinden“- oder Verweisleisten. Klare Handlungsnamen erklären, was der Klick bewirkt.

## Gestaltung

- Ruhige zusammenhängende Flächen, klare Hierarchie, sparsame Umrandungen; keine Mischung aus alten Karten-, Menü- und Icon-Stilen. Bestehende freigegebene Lumen-Halo-Assets konsistent verwenden. Referenz-Platzhaltersymbole ersetzen diese Assets nicht.
- Gemeinsame Abstände: 4, 8, 12, 16, 24 und 32 logische Einheiten. Web-Basistext 14 px mit etwa 22 px Zeilenhöhe, Metadaten 12 px, Haupttitel etwa 26 px. Native Schriftgrößen, Zoom und Dynamic Type haben Vorrang vor starren Pixeln.
- Lesbare Beschriftungen, sichtbarer Tastaturfokus, ausreichender Kontrast und plattformgerechte Berührungsflächen. Lade-, Leer-, Fehler-, Auswahl- und deaktivierte Zustände mitgestalten. Status und Fehler nicht ausschließlich durch Farbe vermitteln.
- Fenster bleiben bei kleinen Größen bedienbar. Seiteneditoren und Arbeitsschritte werden bei Bedarf umgeordnet oder eingeklappt. Kein seitliches Abschneiden wesentlicher Aktionen.
- Neue Gesprächsinhalte folgen ruhig dem Lesefluss. Beim Lesen älterer Inhalte nicht ungefragt ans Ende springen; keine springenden Doppelansichten.

Die folgenden Ausgangswerte stammen aus der Desktop-Palette und der freigegebenen Referenz. Gemeinsame semantische Theme-Tokens verwenden; keine zusätzlichen individuellen App-Paletten einführen. Kompatibilitäts-Themes wie Clear/System nicht ohne gesonderte Migration entfernen.

| Theme | Fenster | Inhalt | Text | Gedämpft | Linie | Akzent | Auf Akzent | Radius |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Glas | `#20343f` | `#182b35` | `#f0f6f8` | `#b1c5cf` | `#526d79` | `#9be5d8` | `#123a38` | 16 |
| Graphit | `#222529` | `#1a1c1f` | `#eff1f3` | `#aab1ba` | `#393e45` | `#d7dce2` | `#1a1c1f` | 10 |
| Atelier | `#f2efe8` | `#fcfaf5` | `#302e29` | `#645e54` | `#c4bfb2` | `#52634f` | `#ffffff` | 8 |
| Mitternacht | `#10151f` | `#141c29` | `#eef1fa` | `#a9b7ce` | `#3d4c65` | `#a7b6ff` | `#18203d` | 6 |

## Verbindlicher Abgleich bei UI-Änderungen

1. Betroffene Panorama-Ansicht, Theme und Bedienweg vor der Umsetzung festlegen. Fehlende Details aus vorhandenen Bausteinen ableiten; grundlegende Abweichungen mit dem Nutzer klären.
2. Einen vollständigen Bedienweg in der tatsächlichen Plattform umsetzen, einschließlich seiner relevanten Zustände und Rechte. Gemeinsam verwendete Komponenten statt weiterer paralleler Stile bevorzugen.
3. Tatsächliche Screenshots bei gleichem Theme, vergleichbarem Inhalt und vergleichbarer Fenstergröße mit der Referenz vergleichen: Navigation, Flächenaufteilung, Typografie, Abstände, Icons und Zustände.
4. Betroffene Themes, schmale Ansicht, Tastatur-/Touchbedienung und funktionale Datenwege angemessen prüfen. Auf freigegebenen Staging-Simulatoren oder isolierten Testprofilen testen; persönliche Produktionsgeräte sind keine Agent-Testgeräte.
5. Sichtbare Abweichungen korrigieren oder ausdrücklich als verbleibende Grenze melden. Keine funktionierende Ansicht allein wegen bestandener Logiktests als visuell fertig bezeichnen. Testergebnis, Installationsstand und noch offene Migration getrennt berichten.

## Herkunft und Grenzen

Der unveränderte Referenz-Snapshot stammt aus `lumen-designreferenz-vier-themes.html`, Chat `01a10367-8a1d-7b13-b4eb-b7b59c0e59f0`. Seine SHA-256 steht in [reference.sha256](reference.sha256). Die HTML-Datei ist ein interaktives Visualisierungsfragment; die ursprüngliche Codex-Vorschau ergänzt den Rahmen für den Entwurfswechsel.

Der Entwurf wurde mit synthetischen Inhalten in vier Themes und zwölf Ansichten geprüft, darunter schmale Ansichten und gemeinsame Zustände. Das ersetzt keine Abnahme einer zukünftigen nativen Implementierung.

Historischer Hinweis: `docs/branding.md` im Server enthält im Abschnitt zur Icon-Familie vom 11.10.2026 noch „Arbeitsräume verwenden das Projektmotiv“. Das ist ein älterer Dokumentationsrest und keine Freigabe für ein Arbeitsraum-Produktmodell; die Passage belegt keine aktuelle Laufzeitfunktion.
