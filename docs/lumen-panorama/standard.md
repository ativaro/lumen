# Lumen Panorama

Status: verbindlicher Designstandard seit 18.10.2026 für Lumen Desktop, Server und Mobile.

Nutzerentscheidung: „ok it is panorama ab jetzt für lumen desktop, server und mobile immer so umsetzzen“.

## Referenz und Zweck

[Freigegebene interaktive Referenz](reference.html): **Panorama** auswählen. Die drei anderen Entwürfe bleiben ausschließlich zum historischen Vergleich enthalten. Die vier Themes sind Glas, Graphit, Atelier und Mitternacht.

Die Referenz soll die bisherige Lücke zwischen Entwurf und implementierter Oberfläche schließen. Sie zeigt gemeinsame Proportionen, Navigation, Bausteine und Zustände anhand synthetischer Inhalte. Sie ist kein Nachweis implementierter Produktfunktionen. Native Plattformen verwenden ihre vorhandene Technik; sie teilen Gestaltung und Bedienprinzipien.

Diese Vorgabe gilt für neue und überarbeitete Oberflächen. Bestehende Ansichten werden im jeweiligen Änderungsschritt angeglichen. Eine vollständige Migration oder Veröffentlichung ist damit nicht automatisch erfolgt oder beauftragt. Historische Entwürfe und ältere Implementierungsberichte überschreiben diesen Standard nicht.

## Aufbau und Bedienung

- Desktop: keine zusätzliche globale App-Leiste. Vorhandene Kopfzeilen, Inhaltsnavigation, Aktionen und Menüs gemeinsam gestalten. Auf Server-Breitansichten bleibt die App-Navigation oben; Mobile behält native Navigation. Auf kleinen Ansichten keine verkleinerte Desktop-Dreispaltenansicht erzwingen. Der Hauptinhalt hat visuellen Vorrang.
- Gespräche sind der leicht erreichbare Hauptweg. Links zunächst die fünf neuesten Gespräche und „Mehr laden“. Eine finale Antwort erscheint einmal im Gespräch. Die schmale, schließbare Nebenansicht zeigt ausschließlich **Arbeitsschritte**. Werkzeugaufrufe werden kompakt zusammengefasst und bei Bedarf aufgeklappt.
- Technische Aufträge treten in den Hintergrund: „Alle Aufgaben“ beziehungsweise die vorhandene Diagnoseansicht dient Fortschrittskontrolle und Troubleshooting. Keine dominante zweite Aufgabenübersicht über dem eigentlichen Inhalt.
- Projekte fassen Vorhaben, Aufgaben, Materialien und Gespräche zusammen. Aufgaben können Recherche, Analyse oder Automation sein. Datei, Notes-Notiz und Weblink sind gleichwertig auffindbare Materialarten. Neue Elemente erhalten einen passenden dedizierten Seiteneditor; alte generische Untermenüs nicht darüberlegen.
- Es gibt keine globale Arbeitsraum-/Workspace-Auswahl. Projekte sind kein umbenannter globaler Arbeitsraum. Bei Migrationen bleiben Daten, Zuordnungen und Rechte erhalten; notwendige Kompatibilität ausdrücklich dokumentieren.
- Reader und Übersetzungs-/Textbearbeitung sind aus Gesprächen erreichbar. Audio-Funktionen folgen der gemeinsamen Bezeichnung **Audio Studio**. Vault und Sicherungen bleiben auffindbar; Sicherungen berücksichtigen insbesondere Drive und Photos.
- Drive berücksichtigt Auswahl, Alles auswählen, Verschieben und kompakte anpassbare Übertragungsanzeigen. Photos berücksichtigt Sammlungen, Entdecken mit Personen/Orten/Motiven und geschützte Fotos. Diese Referenzwege definieren ihre Darstellung; tatsächliche Verfügbarkeit und Schutz werden separat nachgewiesen.
- Funktionen dort anbieten, wo Inhalt und nächste Handlung zusammenpassen. Keine zusätzlichen allgegenwärtigen „Verbinden“- oder Verweisleisten. Klare Handlungsnamen erklären, was der Klick bewirkt.

## Gestaltung

Desktop-Präzisierung vom 18.10.2026: Panorama wird in den ursprünglichen Ansichten umgesetzt. Parallele App-Stile ersetzen und ungenutzten Gestaltungs-/Navigationscode entfernen; kein zusätzlicher Überzug. Native Kopfzeilen nutzen `files/desktop_design.py`, die gemeinsamen Server-Apps werden im gerätegebundenen Host angezeigt; ihre Oberfläche wird auf dem Server gepflegt. Gemeinsame Maße: Titel26px/500, Untertitel12px, Bedienung14px, Rand24px, Abschnitt16px, Navigation224px. Systemschrift/Zoom und Leseschrift-Einstellungen bleiben erhalten. Unterschiedliche Inhaltsaufteilungen folgen der jeweiligen Aufgabe; Menüverhalten, Titelhierarchie und Aktionsgestaltung bleiben konsistent.

- Ruhige zusammenhängende Flächen, klare Hierarchie, sparsame Umrandungen; keine Mischung aus alten Karten-, Menü- und Icon-Stilen. Bestehende freigegebene Lumen-Halo-Assets konsistent verwenden. Referenz-Platzhaltersymbole ersetzen diese Assets nicht.
- Gemeinsame Abstände: 4, 8, 12, 16, 24 und 32 logische Einheiten. Web-Basistext 14 px mit etwa 22 px Zeilenhöhe, Metadaten 12 px, Haupttitel etwa 26 px. Native Schriftgrößen, Zoom und Dynamic Type haben Vorrang vor starren Pixeln.
- Lesbare Beschriftungen, sichtbarer Tastaturfokus, ausreichender Kontrast und plattformgerechte Berührungsflächen. Lade-, Leer-, Fehler-, Auswahl- und deaktivierte Zustände mitgestalten. Status und Fehler nicht ausschließlich durch Farbe vermitteln.
- Fenster bleiben bei kleinen Größen bedienbar. Seiteneditoren und Arbeitsschritte werden bei Bedarf umgeordnet oder eingeklappt. Kein seitliches Abschneiden wesentlicher Aktionen.
- Neue Gesprächsinhalte folgen ruhig dem Lesefluss. Beim Lesen älterer Inhalte nicht ungefragt ans Ende springen; keine springenden Doppelansichten.

Die folgenden Ausgangswerte stammen aus der Desktop-Palette und der freigegebenen Referenz. Gemeinsame semantische Theme-Tokens verwenden; keine zusätzlichen individuellen App-Paletten einführen. Kompatibilitäts-Themes wie Clear/System nicht ohne gesonderte Migration entfernen.

| Theme | Fenster | Inhalt | Text | Gedämpft | Linie | Akzent | Auf Akzent | Radius |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Glas | `#202c34` | `#19242b` | `#f0f6f8` | `#b1c5cf` | `#526d79` | `#9be5d8` | `#123a38` | 16 |
| Graphit | `#222529` | `#1a1c1f` | `#eff1f3` | `#aab1ba` | `#393e45` | `#d7dce2` | `#1a1c1f` | 10 |
| Atelier | `#f2efe8` | `#fcfaf5` | `#302e29` | `#645e54` | `#c4bfb2` | `#52634f` | `#ffffff` | 8 |
| Mitternacht | `#10151f` | `#141c29` | `#eef1fa` | `#a9b7ce` | `#3d4c65` | `#a7b6ff` | `#18203d` | 6 |

Glas-Präzisierung vom 05.11.2026: Fensterflächen verwenden denselben dunklen
Rauchblau-/Graphitton wie die Topbar-Referenz des Nutzers. Die gemeinsame
Fensterfläche ist `#202c34`, die vertiefte Inhaltsfläche `#19242b`; Text, Akzente
und Bediengeometrie bleiben den vorhandenen semantischen Rollen zugeordnet.

## Verbindlicher Abgleich bei UI-Änderungen

Desktop-Topbar (05.11.2026): Die Standardleiste folgt dem freigegebenen Entwurf
`lumen-topbar-alltag.html`: ein zusammenhängendes Panorama-Band mit dauerhafter
Lumen-Eingabe und Diktat-Einstieg. Links vor dem Lumen-Kreis steht ein eigener
Programmknopf: Er öffnet die Startansicht mit direkter App-Suche. Der
Lumen-Kreis öffnet die Lumen-Apps. Beide verwenden dasselbe vorhandene Startmenü.
Fensterübersicht und letzte Inhalte haben je
einen kleinen Schnellzugriff. Eine gemeinsame Statusfläche priorisiert Freigaben,
Aufnahmen, Fokuszeit, Übertragungen, Medien und Updates; sie rotiert nicht automatisch.
Nicht stören bleibt in der Mitteilungsanzeige erkennbar. Bei wenig Platz rückt die
Eingabe in eine eigene Zeile. Keine Dateiauswahl in der Topbar; Dateien bleiben in
den zuständigen Apps verwendbar. Bestehende Notes-Übergaben bleiben ausdrücklich.
Fokuszeit, Nicht stören, Medien und Updates sind über dieselbe Statusfläche erreichbar.
Freigaben und Aktualisierungen öffnen ihre bestehenden Prüf-/Bestätigungsdialoge.
Letzte Inhalte nutzen die vorhandenen Dateiverläufe und gespeicherten Gespräche;
offene Notes-/App-Inhalte sind über die laufenden Fenster erreichbar. Verläufe
anderer Serverbindungen werden nicht angeboten. Es werden keine Inhalte kopiert.
Aktive Systemtray-Apps bleiben bei ausreichend Platz direkt sichtbar; nur bei
Platzmangel sowie für passive Apps dient das Menü „Hintergrund-Apps“.
Startmenü-Präzisierung vom 05.11.2026: Das vollständige Startmenü zeigt „Dein Start“
nach der freigegebenen Referenz `lumen-start-next.html`: Suche, angeheftete Apps,
zwei letzte Inhalte unter „Gleich weiter“ und eine ruhige Fußzeile mit Benutzer,
Einstellungen, Sperren und Sitzungsaktionen. „Alle Apps“ öffnet den nativen,
durchsuchbaren Anwendungskatalog mit dessen tatsächlichen Kategorien; Lumen-Apps
bleiben dort und über den Lumen-Kreis erreichbar. Favoriten lassen sich anheften
und über „Anpassen“ entfernen. App-Kontextaktionen stammen vom nativen Katalog.
Sitzungsaktionen beachten die verfügbaren Plattformfähigkeiten und die nativen
Bestätigungen. Fehlende Apps oder Verläufe werden als solche angezeigt; keine
Beispieldaten in der ausgelieferten Oberfläche. Die Fußzeile und Popups verwenden
die vertiefte Theme-Fläche; normale Beschriftungen bleiben 14px.

Gesprächs-Präzisierung vom 05.11.2026: Nach einer Frage wächst die Topbar nach
unten zu einer durchgehenden Gesprächsfläche nach `lumen-topbar-gespraech-ablosen.html`.
Leiste und Gespräch teilen Fläche und Außenkante. Der Knopf unmittelbar rechts
neben der Eingabe klappt das Gespräch auf und zu. Senden erscheint bei vorhandenem
Text als eigene Aktion. Herausziehen und „Als Fenster öffnen“ lösen denselben
Verlauf mit Entwurf und Arbeitsschritten; „In Leiste anheften“ führt ihn zurück.
Die Eingabe bleibt erreichbar, während Antworten, Freigaben, Rückfragen und
aufgeklappte Arbeitsschritte im Inhalt scrollen. Bestehende native Gesprächslogik
und Antwortbausteine werden wiederverwendet. Der Darstellungswechsel sendet keine
Nachricht und startet keinen weiteren Auftrag. Das abgelöste normale Fenster nutzt
Lumens vorhandene Fensterknöpfe für Minimieren, Maximieren/Wiederherstellen und
Schließen; Verschieben und Größenänderungen bleiben native Fensteraktionen.

Der technische Einstellungswert `classic` heißt in der Oberfläche nun Panorama;
die ausdrücklich angebotenen alternativen Layouts bleiben wählbar.

Desktop-Topbar, Eingabe (11.11.2026): Mikrofon, „Gespräch aufklappen“ und Senden
sitzen im Eingabefeld. Senden erscheint erst mit Text. Fokus zeigt ein 2 px starker
Akzentrahmen; ein Fehler zeigt Warnsymbol, Rahmen in Textfarbe und „Erneut senden“.
Bedienelemente verwenden den Innenradius des Themes (`innerRadius`, 65 % des
Theme-Radius), Flächen und Menüs den Theme-Radius. Keine festen Radien im Topbar-Code.
Das Feld ist höchstens 720 px breit und sitzt in der Bildschirmmitte. Im angedockten
Gespräch ist dessen mehrzeiliges Feld die Eingabe; das Feld der Leiste nennt dann nur das
Gespräch und behält Diktat und Einklappen. Eingeklappt bietet es „Abbrechen“, solange
Lumen arbeitet. Ab 1100 px stehen die Arbeitsschritte als schließbare Nebenansicht rechts,
darunter als aufklappbare Zeile. Das gelöste Gesprächsfenster behält seine eigene Eingabe.
Nachrichten im Topbar-Gespräch stehen in runden Sprechblasen (Radius 18, die Ecke zur
sprechenden Seite 6): eigene Nachrichten rechts, Antworten von Lumen links. Nutzerentscheidung
vom 11.11.2026; die Blasen folgen bewusst nicht dem Theme-Radius.

Desktop-Topbar, Kurzansichten (06.11.2026): Glocke, Netzwerk und Audio öffnen jeweils eine angedockte, höchstens 390 Pixel breite Ansicht.
Die Statusmenüs schließen rechts an die Leiste an. Der Lumen-Kreis öffnet links
direkt den vollständigen Katalog „Lumen Apps“. Seine Suche beginnt leer und hat den Tastaturfokus.
Auf schmalen Bildschirmen bleibt ein seitlicher Abstand. Ein Eintrag öffnet das
vollständige Menü mit der gewählten Meldung oder dem Gerätebereich. Programmknopf und Super öffnen direkt das vollständige, links angedockte
Startmenü „Dein Start“. Die Suche erhält den Tastaturfokus. Angeheftete Apps und
„Gleich weiter“ sind sofort sichtbar. „Alle Apps“ öffnet den Katalog. Der Reglerknopf rechts und das Zahnrad in „Dein Start“
öffnen direkt die angedockte Systemsteuerung. Dort sind Netzwerk, Audio und Lumen-Einstellungen erreichbar. Ein zweiter Klick auf denselben
Menüknopf klappt die Ansicht zu. Beim Wechsel zwischen Menüknöpfen ist nur die
gewählte Ansicht geöffnet. Eigene App-Fenster behalten ihre Fenstersteuerung.
Plasma führt den gemeinsamen Mitteilungsverlauf und alle Aktionen. Der erste
Klick zeigt bis zu drei aktuelle Meldungen. Desktop-Popups erscheinen oben rechts
auf dem von Plasma priorisierten Monitor. Zugangsdaten, Verbindungswechsel und
Geräteeinstellungen werden erst im dafür zuständigen vollständigen Menü behandelt.

Die vollständigen Netzwerk- und Audio-Menüs schließen an derselben Kante direkt an die Topbar an wie ihre Kurzansichten.
Netzwerk gliedert sich in Übersicht, WLAN,
Kabel/Adapter, VPN/Proxy, Hotspot und Details/Diagnose; Audio in Übersicht,
Ausgabe, Mikrofon, Apps, Bluetooth und Klang/Technik. Auf schmalen Bildschirmen
werden diese Bereiche oberhalb des Inhalts angeordnet. Darstellung und Regler
nutzen dieselben Themes, 14px-Bedienung, Hover und Namenshinweise wie die Leiste.
WLAN-/VPN-Verbindungen, Audiogeräte und App-Routing zeigen den tatsächlichen
Systemzustand. Profil-, Sicherheits-, Hotspot-, Proxy-, Firewall- und komplexe
Audioeinstellungen führen gezielt in die bestehenden nativen Einstellungsseiten.
Keine erfundenen Messwerte oder funktionslosen Klang-/Mikrofonregler anzeigen.
Passwörter/Zertifikate bleiben bei der Systemanmeldung. Mikrofone werden für die
Anzeige nicht geöffnet. Die allgemeine Systemsteuerung enthält Helligkeit,
Einstellungen und Sperren; sie ist kein zweiter gemeinsamer Audio-/Netzwerkmischer.

1. Betroffene Panorama-Ansicht, Theme und Bedienweg vor der Umsetzung festlegen. Fehlende Details aus vorhandenen Bausteinen ableiten; grundlegende Abweichungen mit dem Nutzer klären.
2. Einen vollständigen Bedienweg in der tatsächlichen Plattform umsetzen, einschließlich seiner relevanten Zustände und Rechte. Gemeinsam verwendete Komponenten statt weiterer paralleler Stile bevorzugen.
3. Echte Vorher-/Nachherbilder desselben Bedienwegs mit Sourcepin, Theme, Inhalt, Fenstergröße, Sprache und Skalierung festhalten und mit der freigegebenen Referenz vergleichen: Navigation, proportionale Inhaltsfläche, Typografie, 24px-Außenränder, vollständige Aktionsbeschriftungen, Icons und Zustände. Keine gesonderten Screenshot-Stile verwenden.
4. Betroffene Themes, kleine Fenster mit langen Inhalten, Tastatur-/Touchbedienung und funktionale Datenwege angemessen prüfen. Überlauf durch Umordnen, Umbrechen oder erreichbare Scrollwege lösen; Mindestgröße erhöhen oder Schrift verkleinern darf Fehler nicht kaschieren. Gemeinsame Komponenten und semantische Paletten verwenden. Auf freigegebenen Staging-Simulatoren oder isolierten Testprofilen testen; persönliche Produktionsgeräte sind keine Agent-Testgeräte.
5. Sichtbare Abweichungen korrigieren oder ausdrücklich als verbleibende Grenze melden. Grüne Logiktests allein bedeuten nicht „fertig“: vor gezielter Promotion müssen Root beziehungsweise der zuständige Reviewer die echten Bilder visuell abnehmen. Nur den geprüften Dateiumfang mit Sicherung, Rückweg und Erhalt unabhängiger installierter Änderungen übernehmen; installierte Hashes und den betroffenen Bedienweg nachprüfen. Testergebnis, Sichtabnahme, Integrations- und Installationsstand getrennt berichten. Die Desktop-Präzisierung ohne zusätzliche globale App-Leiste bleibt maßgeblich.

## Herkunft und Grenzen

Der unveränderte Referenz-Snapshot stammt aus `lumen-designreferenz-vier-themes.html`, Chat `01a10367-8a1d-7b13-b4eb-b7b59c0e59f0`. Seine SHA-256 steht in [reference.sha256](reference.sha256). Die HTML-Datei ist ein interaktives Visualisierungsfragment; die ursprüngliche Codex-Vorschau ergänzt den Rahmen für den Entwurfswechsel.

Der Entwurf wurde mit synthetischen Inhalten in vier Themes und zwölf Ansichten geprüft, darunter schmale Ansichten und gemeinsame Zustände. Das ersetzt keine Abnahme einer zukünftigen nativen Implementierung.

Historischer Hinweis: `docs/branding.md` im Server enthält im Abschnitt zur Icon-Familie vom 11.10.2026 noch „Arbeitsräume verwenden das Projektmotiv“. Das ist ein älterer Dokumentationsrest und keine Freigabe für ein Arbeitsraum-Produktmodell; die Passage belegt keine aktuelle Laufzeitfunktion.
