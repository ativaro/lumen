> **Historischer Entwurf oder Abnahmebeleg – keine aktuelle Installationsanleitung.** Diese datierte Abnahme gehört zum damaligen Kandidaten. Enthaltene lokale Notes-/Projekt-/Code-/Audio-Editoren sind inzwischen durch Server-Apps ersetzt; nur die Gestaltungsentscheidung bleibt als Referenz bestehen. Aktuelle Zuordnung: [Desktop-Verantwortlichkeiten](../desktop-retirement.md).

# Audio Studio · Panorama, 18.10.2026

Audio Studio verwendete unter dem gemeinsamen Kopfbereich noch zwei verschachtelte Reiterleisten, eine dicht gedrängte Aktionszeile und eine leere Transkripttabelle. Die bestehenden nativen Ansichten sind jetzt direkt überarbeitet; es gibt keine zusätzliche globale App-Leiste.

## Bedienung und Darstellung

- Aufnahmen / Hörskripte als kompakte Bereichsauswahl im bestehenden Kopfbereich; beide Bibliotheken und ihre Änderungen bleiben beim Wechsel erhalten.
- Bibliothek mit Suche, verständlichem Einstieg, Titel und Dauer/Textstellen bzw. Quellen/Minuten. Archiv und Wiederherstellen bleiben erreichbar.
- Aufnahmen: großer bearbeitbarer Titel, Metadaten, vorhandener Player, geordnete Aktionen. Das Transkript liest sich als Text mit anklickbaren Zeitstellen; lange Absätze umbrechen auch beim Verkleinern. Ergebnisse und Agenda bleiben bearbeitbar.
- Hörskripte: dieselbe Struktur für Quellen, Sprechtext und Wiedergabe. Quellenauswahl und Textprüfung stehen nebeneinander; leere Quellen zeigen einen Einstieg. Vertonen, Export, Quellenbelege und Original öffnen bleiben erhalten.
- Leere Player und nicht vorhandene Quellenbelege werden ausgeblendet. Die Herkunft von KI-Ergebnisvorschlägen und die lokale Verarbeitung bleiben sichtbar erklärt.

Die Gestaltung verwendet die gemeinsamen Panorama-Schriften, Palette und Kopfzeile für Graphit, Glas, Atelier und Mitternacht. Native Textbearbeitung, Fokus und Tastaturbedienung bleiben bestehen. Keine neuen Modelle, Datenmigrationen oder automatischen KI-/Audioaufrufe; keine erfundene Wellenform.

## Änderungspunkte

`files/audio_design.py` enthält die tatsächlich von beiden Bereichen genutzte Bibliotheks-/Leeransicht und Transkriptgestaltung. `tools_meetings.py` und `tools_radio.py` bauen ihre vorhandenen Inhalte damit auf. `tools_meeting_radio.py` ersetzt die alte äußere Reiterleiste durch die Bereichsauswahl. Alte äußere Reiterstile und die bisherigen überbreiten Aktionsreihen sind entfernt. Speicherformat, Import-, Export-, Transkriptions-, Synthese-, Quellen- und Schließlogik bleiben erhalten.

## Abnahme

23 Prüfungen in fünf Suiten: acht Audio-Studio-Prüfungen einschließlich echter isolierter Starter/IPC für beide Einstiege, drei Radio-Audioprüfungen, drei Routingprüfungen, acht weitere Audio-Interop-Prüfungen sowie der gemeinsame reale Notes-/Projekte-/Code-/Audio-Kopfzeilentest in allen vier Themes. Die neuen Fälle prüfen leere Einstiege, Sperren während einer Arbeit, Archiv/Wiederherstellen, bearbeitete Transkripte und Quellen, Zeitstellen, Export und erhaltene Aufgaben-Metadaten sowie den Umbruch langer Absätze beim Verkleinern.

Echte Qt-Aufnahmen mit synthetischen Daten: Transkript, Ergebnisse, Quellen und Hörskript in allen vier Themes bei 1280 × 900; zusätzlich leere Bibliotheken und schmale Fenster bei 960 × 760. Gegen die freigegebene Audio-Referenz geprüft: ruhige Hierarchie, lesbare Zeitstellen, gemeinsame Navigation und Inhalte im Vordergrund. Die bestehende importbasierte Aufnahmefunktion erhält keine vorgetäuschte Live-Aufnahme oder Wellenform.

Belege und kontrollierter Installationsrückweg: `~/.local/state/lumen/audio-panorama-20261018/`. Jede Qt-Prüfung verwendet getrennte Lumen-/Tools-/XDG-Daten und einen privaten D-Bus. Persönliche Bibliotheken und geöffnete Apps sowie Server/Mobile und der belegte iPhone-Simulator sind keine Testziele. Hardware-Audioausgabe, echte Modelltranskription und kostenpflichtige KI-Anfragen sind nicht Teil dieser UI-Abnahme.

## Installierter Stand

Quellstand `08fc03ba27d1c691aba7b2f6929d6c523975dbd5`: vier Audio-Module nach Prüfung der vorherigen Dateihashes atomar installiert. 630 andere Codeassets und der Vault-Broker blieben unverändert; keine persönliche App wurde neu gestartet. Alle 23 Prüfungen bestehen auch gegen die installierten Produktionsmodule. Die 20 installierten Qt-Aufnahmen stimmen bytegleich mit den Aufnahmen des geprüften Quellstands überein. Manifest, Vorher-Sicherung, Prüfprotokolle und `verification.json` liegen im genannten Belegverzeichnis.

Rückweg: `python ~/.local/state/lumen/audio-panorama-20261018/install-desktop.py rollback` prüft zunächst; `rollback --apply` nimmt ausschließlich diese vier Dateien zurück und entfernt das neu hinzugekommene Modul. Der Rückweg wurde auf Hash-/Driftkonsistenz geprüft, nicht auf der persönlichen Installation ausgeführt. Diesen neuesten Audio-Stand vor älteren Desktop-Rückwegen zurücknehmen. Bereits geöffnete Audio-Studio-Fenster laden die Änderung erst nach normalem Schließen und erneutem Öffnen.
