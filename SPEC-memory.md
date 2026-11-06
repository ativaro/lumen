> **Historischer Entwurf oder Abnahmebeleg – keine aktuelle Installationsanleitung.** Die frühere gemeinsame Notes-/Gedächtnis-Oberfläche ist aufgeteilt. Den aktuellen lokalen Lernvertrag beschreibt docs/memory/LEARNING.md; normale Notes-Inhalte gehören zum Server. Aktuelle Zuordnung: [Desktop-Verantwortlichkeiten](docs/desktop-retirement.md).

# Mein Notizbuch und Lumen-Gedächtnis

Angenommener Nutzerentwurf: zwei erkennbare Bereiche in Wissen. Persönliche
Notizen bleiben unter Nutzerkontrolle; einzelne Notizen oder Ordner sind für
Kontext freigebbar. Lumen pflegt sein Gedächtnis selbstständig, mit Herkunft,
Zeitpunkt, Korrektur, Verlauf und Vergessen. Spätere Gespräche/Aufträge in Lumen,
Files und Suche verwenden das passende Gedächtnis. Explizite Aktionen heißen
„Für mich speichern“ und „Merk dir das“.

## Aufbau

1. `lumen_memory.py`: lokaler Markdown-Gedächtnisordner, privates Register für
   Art/Geltungsbereich/Herkunft/Version, Freigaben und Vergessen-Sperren. Vorhandenen
   Notebook-Speicher, History und Job-Unterprozesse verwenden. Keine neue Engine.
2. Wissen-Oberfläche: Bereiche, Freigaben, Herkunft/Zeitpunkt, Korrektur/Verlauf,
   Nutzung/Lernen umschaltbar. Persönliche Notizen unverändert behalten.
3. Gemeinsames OpenCode-Backend: vor normaler Anfrage begrenzte relevante,
   frisch gelesene Erinnerungen und freigegebene Notizauszüge laden. Keine
   Gedächtnisbeimischung in isolierte native JSON-Vorschlagsaufträge außer dem
   ausdrücklich integrierten Inbox-Entwurf (nur Kontext, kein Lernen). Extraktion
   nach Gespräch aus der ursprünglichen Nutzernachricht, ohne Werkzeuge, in
   getrenntem Auftrag. Kein Lernen aus Modellantworten oder Dateianhängen.
4. Native Gesprächsaktionen, Tests, Dokumentation, Paket37, Benutzerbundle/Git.

## Vertrag und Grenzen

Gedächtnis bleibt lokal unter dem Lumen-Zustandsordner, unabhängig vom wählbaren
Notiz-/NAS-Ordner. Vorhandene Notizen sind standardmäßig privat. Die globale
Nutzung und das automatische Lernen sind einstellbar; in dieser Installation
durch das angenommene Konzept aktiviert, in frischen Profilen zunächst aus.

Automatische Einträge: maximal drei kurze Aussagen pro Nachricht mit wörtlichem
Beleg aus dem Nutzertext; Typ Vorliebe/Fakt/Entscheidung, global oder an das aktuelle
Arbeitsverzeichnis gebunden. Keine Zugangsdaten, keine sensiblen persönlichen
Profile, keine aus Anhängen oder Lumen-Antworten abgeleiteten Behauptungen.
Aktualisieren nur mit passendem vorherigem Datei-Hash; manuell bearbeitete Notizen
werden nicht blind überschrieben. Deduplizierung und Fingerabdrücke gegen erneutes
automatisches Lernen identischer vergessener Einträge. Keine automatische Übernahme kompletter
Chats. Fehler des Gedächtnisses blockieren die eigentliche Anfrage nicht.

Freigaben sind an Ordneridentität und Pfad gebunden, revokabel und überschreibbar
durch eine private Einzelnotiz. Dateizugriff bleibt unter vorhandenen No-Symlink-
und Ressourcen-Grenzen. Revokation/Vergessen/Nutzungsänderung invalidiert Kontext;
der nächste Auftrag startet eine frische Engine-Unterhaltung, damit vorher
eingefügtes Gedächtnis dort nicht weiter verwendet wird. Frühere Chats werden nicht
rückwirkend verändert. Vergessen entfernt aktiven Eintrag und dessen lokale
Wiederherstellungskopien; inhaltsfreie Fingerabdrücke sperren bekannte identische
Titel, Texte und Belege. Semantisch ähnliche Umformulierungen sind damit nicht
vollständig erkennbar. Ein ausdrücklich neues Merken ist möglich.

Die Extraktionsanweisung schließt sensible Profile und zitierte Inhalte aus;
der Speicher prüft zusätzlich wörtlichen Beleg und typische Zugangsdatenmuster.
Dies verifiziert nicht die Bedeutung einer Modellinterpretation. Automatische
Einträge bleiben deshalb als solche erkennbar und korrigierbar.

Nur beim Nutzerauftrag werden passende Auszüge an den konfigurierten Anbieter
übermittelt; dieser kann Cloud sein. Automatisches Lernen verwendet denselben
Anbieter und nur bereits übermittelten Nutzertext. Native Einstellungen erklären
dies vor einer erstmaligen Aktivierung. Keine zusätzlichen Anbieter/Abhängigkeiten.

## Abnahme

`PYTHONPATH=files QT_QPA_PLATFORM=offscreen python3 -m unittest test_memory test_wissen -v`
prüft Bereichstrennung, explizite Freigabe/Entzug, Projektfilter, begrenzten Kontext,
Quellenbelege, Konflikte, Duplikate, Vergessen und Neustart. Gemeinsames Backend
gegen lokale Test-Engine prüfen, einschließlich Abbruch und späterem Gespräch.
`python3 -m unittest discover -s files -v`, zwölf QML-Checks, native Ansichten
in vier Themes und installiertes Bundle prüfen. Keine echten privaten Inhalte
an einen Modellanbieter senden; synthetische Antworten für die Integration.

Code bleibt im Stil der vorhandenen Notebook-/ToolWindow-/Job-Module. Keine
Umbauten an Files-Ansichten, Panels, Themes oder anderen Werkzeugen ohne Bedarf.
# Gekoppelter Gesprächszugriff · 27.10.2026

Bei bestehender Serverkopplung nutzt der normale Gesprächskontext den aktuellen
kontoweiten Serverbestand und dessen Suchdienst. ID, Revision, Bestätigung und
Kontofreigabe stammen vom Server; vor dem Absenden wird die Fassung erneut geprüft.
Eine Korrektur oder ein Entzug beginnt eine neue Engine-Sitzung statt alte
Kontextnachrichten weiterzureichen. Serverfehler führen nicht zu einem stillen
lokalen Ersatz. Der Servereditor öffnet dieselben Erinnerungen wie Web/Mobile.

Lokale Inhalte, bestehende Opt-outs und offene Replikationsquittungen bleiben
unverändert. Nach bewusstem Trennen bleibt lokaler Betrieb möglich. Lokale
Gedächtniswerkzeuge sind als lokale Ziele beschrieben; gewöhnliche gekoppelte
Speicheraufträge verwenden die vorhandenen Serverwerkzeuge samt Freigabe.
Der gekoppelte Leseweg startet keinen lokalen automatischen Lerner. Gemeinsames
automatisches Lernen und Persona folgen separat (A8), keine Bestandsübernahme.
