# Lumen Code Desktop: eigene Erstellungswege

Nutzerentscheidung vom 18.10.2026: Werkzeuge, Zeitpläne & Routinen,
Automation und Code erhalten eigene Einstiege. Kleine Apps werden vorerst
nicht neu angeboten; vorhandene Apps samt Entwürfen bleiben nutzbar.

## Bedienung

- **Werkzeug:** Eingabe, Ergebnisform, Auftrag und feste Regeln beschreiben.
  Beispieleingabe mit der eingerichteten KI prüfen; tatsächliches Ergebnis sehen.
  Datei oder Projektnotiz ausdrücklich auswählen, lesen, prüfen und in die
  Eingabe übernehmen. Anschließend mit neuen Eingaben wiederverwenden.
- **Zeitpläne & Routinen:** Bis zu fünf feste Schritte erstellen, ordnen oder
  gespeicherte Werkzeuge als eingefrorene Version hinzufügen. Manueller Start,
  einmaliger Termin, täglicher, wöchentlicher oder monatlicher Zeitplan in
  Europe/Zurich; Ergebnis melden oder als neue Notes-Notiz ablegen. Anlegen
  aktiviert noch nichts. Die anschließende vorhandene Routineprüfung erteilt
  Quellen- und Ausführungsfreigaben.
- **Automation:** Wenn / Und wenn / Dann mit aufklappbaren Bausteinen. Quelle
  ist Text, ausdrücklich ausgewählte Datei, Name und Notiz eines Lumen-Projekts,
  eingefügte Nachricht oder eingefügte Termindaten. Verfügbare Vergleichsfelder
  richten sich nach Quelle und vorherigen Schritten. UND, ODER und NICHT sowie
  Zahlen-, Text- und Ja/Nein-Vergleiche; keine ausführbaren Formelausdrücke.
  Bis zu zwölf Wege je Entscheidung, drei verschachtelte Steuerungsebenen und
  sechzig Bausteine insgesamt. Der erste passende Weg läuft, anschließend der
  gemeinsame Hauptablauf. Textzeilen filtern, KI-Verarbeitung, KI-Inhaltsprüfung,
  Schleifen über maximal zwanzig Zeilen, Warten, Bestätigung sowie Schreiben
  von Dateien, Notes-Notizen, Inbox-Aufgaben, Projektnotizen und Meldungen.
  Maximal tausend ausgeführte Bausteinschritte je Durchlauf.
- **Code:** Ordner öffnen, HTTPS-/SSH-Repository klonen oder in einem neuen
  Ordner beginnen; optional ersten Auftrag eingeben. Prüfung zeigt Ziel und
  Aktion. Erst die abschließende Bestätigung legt den Ordner an oder klont das
  Repository. Vorhandene Ziele werden nicht überschrieben. Danach öffnet sich
  das vorhandene Projektgespräch mit Dateien und Änderungen.

Bedingungen und ganze Abläufe lassen sich zusätzlich in Worten beschreiben.
Die KI liefert ausschließlich einen validierten Vorschlag. Er ist sichtbar,
bearbeitbar und erst nach ausdrücklicher Übernahme Teil des Entwurfs.
Änderungen an Quelle, Beschreibung oder Ablauf machen alte Vorschläge ungültig.
Keine Schlüsselwort-Klassifikation und keine automatische Ausführung aus Text.

## Daten, Freigaben und Kompatibilität

Die bestehende Sammlung bleibt unverändert: Routinen sind Automation-Einträge
mit bestehendem v1-Zeitplan, neue Bausteinabläufe verwenden Version 3 und
`code_block_runs`. Version-2-Abläufe bleiben im bisherigen Editor lauffähig und
werden nicht automatisch umgeschrieben. Kein neues globales Arbeitsraum-Modell.
Der technische Altschlüssel `files/spaces/room/` in `file_spaces.py` bleibt als
Speicher von Lumen-Projekten erhalten. Zuordnungen und bisherige Daten werden
nicht migriert oder gelöscht. Das Anhängen an eine Projektnotiz und sein
Checkpoint teilen dieselbe SQLite-Schreibtransaktion.

Baustein-Testläufe lesen tatsächlich gewählte Quellen und rufen gegebenenfalls
das konfigurierte Modell auf. Schreibaktionen landen ausschließlich im privaten
Testordner. Reale Läufe zeigen zuvor Quellen, Modellübermittlung und konkrete
Aktionen zur Freigabe. Checkpoints, Versuchskennungen und eigene Effektkennungen
pro Schleifeniteration schützen Fortsetzen und erneute Zustellung. Bei einer
geänderten Definition darf ein alter Lauf nicht fortgesetzt werden.

Für die neue Oberfläche werden die vorhandene native Shell, Panorama-Palette,
Lumen-Icons und Tastatursteuerung verwendet. Breite Routinen zeigen Schritte
und Zeitplan nebeneinander, schmale Fenster ordnen sie untereinander. Die
Erstellung bleibt ein eigenes natives Fenster; eine zusätzliche globale
App-Leiste wird dort nicht eingeführt. Details werden bei Bedarf aufgeklappt,
die abschließenden Aktionen bleiben erreichbar.

## Abnahme und Grenzen

82 Code-Regressionstests, native A/B-Simulatorprofile mit Graphit, Atelier,
Glas und Mitternacht, Deutsch/Englisch sowie 840/1120 Pixel breite Fenster.
Die native Ansicht wurde mit der Panorama-Referenz und den gewählten
Erstellungsentwürfen verglichen. Echte Ollama-Cloud-Aufrufe mit
`ollama/deepseek-v4.1-flash` prüfen Werkzeugtest, Bedingungsvorschlag,
Ablaufvorschlag sowie eine KI-Verzweigung mit Bestätigung, Fortsetzen und
ausschließlich isoliertem Ergebnis. Neuer Ordner und echtes Git-Klonen gegen
eine isolierte HTTPS-Quelle geprüft; keine externen Repository-Zugangsdaten.

Neue Baustein-Automationen starten auf Desktop vorerst **manuell**; Lumen bleibt
während der Ausführung geöffnet. Zeitgesteuerte Hintergrundausführung nutzt den
vorhandenen Routinenweg. Eingefügte Nachrichten/Termine sind Daten, keine neuen
automatischen Mail-/Kalenderauslöser. Keine beliebigen externen APIs oder
Shell-/Python-Bausteine. Dateilesen nutzt die vorhandenen begrenzten Decoder;
Dateitypauswahl bedeutet keine Unterstützung beliebiger Binärformate.
Projektquelle umfasst Name/Notiz, nicht automatisch alle Projektmaterialien.
Keine vollständige Screenreader-Abnahme oder Prüfung privater SSH-Authentifizierung.
Server und Mobile wurden in diesem Schritt nicht geändert.

Installation erfolgt nur für die betroffenen Laufzeitdateien nach Prüfung gegen
den Ausgangsstand. Hashmanifest, vorherige Dateien und begrenzter Rückweg liegen
unter `~/.local/state/lumen/code-create-20261018/`. Rückweg verändert keine
Sammlungsdaten oder Lauf-Checkpoints: Neue v3-Abläufe benötigen zum erneuten Öffnen
weiterhin eine v3-fähige Laufzeit. Persönliche Sitzungen werden nicht als
Testumgebung benutzt und nicht automatisch beendet.

## Fenster-Icon, 18.10.2026

Der Starter war bereits `lumen-code` zugeordnet. Anwendung und Sammlung setzen
nun zusätzlich ausdrücklich das vorhandene `lumen-code`-Fenster-Icon, damit
weder der Desktop-Fallback noch ein geerbtes Projects-Icon angezeigt werden.
Kinddialoge erben das Code-Icon. Native A/B-Prüfungen über den echten Einstieg
vergleichen die gerenderten Pixel mit dem freigegebenen Code-Asset und prüfen
den Unterschied zum Projects-Asset. Zwei Regressionstests sichern Prozess- und
Fensterzuordnung. Bestehende persönliche Fenster werden nicht beendet; für die
neue Zuordnung Lumen Code schließen und neu öffnen. KWin/Plasma selbst wurde
nicht in einer persönlichen Sitzung automatisiert geprüft.

## KDE-Cache nach Icon-Installation

Die Prüfung des gemeldeten Leistenbilds bestätigte ein Projects-Motiv. Am vom
Nutzer geöffneten Code-Fenster lieferte KDEs Wayland-TasksModel bereits
`lumen-code`, `applications:lumen-code.desktop` und exakt die Code-Icon-Pixel.
Der vorhandene `hicolor/icon-theme.cache` war älter als das neue Code-Asset und
enthielt nur `lumen-workbench`, noch kein `lumen-code`. Der Cache wurde mit
Sicherung neu aufgebaut, die KDE-Anwendungsdatenbank aktualisiert und der
Panel-Iconloader über seine vorhandene Änderungsmitteilung neu geladen.
Der Benutzerinstaller aktualisiert künftig nach dem Kopieren der Icons auch
den Hicolor-Cache, falls das vorhandene Systemwerkzeug verfügbar ist.
Es wurde keine persönliche Anwendung geschlossen oder neu gestartet.
Eine sichtbare Bestätigung der laufenden Plasma-Leiste durch den Nutzer
steht noch aus; die Cachekorrektur ist technisch nachgewiesen.
