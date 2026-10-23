> **Historischer Entwurf oder Abnahmebeleg – keine aktuelle Installationsanleitung.** Diese datierte Abnahme gehört zum damaligen Kandidaten. Enthaltene lokale Notes-/Projekt-/Code-/Audio-Editoren sind inzwischen durch Server-Apps ersetzt; nur die Gestaltungsentscheidung bleibt als Referenz bestehen. Aktuelle Zuordnung: [Desktop-Verantwortlichkeiten](../desktop-retirement.md).

# Lumen Notes: mehr Platz in der Notizliste

Die aktive Desktop-Liste war höchstens 260 Einheiten breit und zeigte Titel,
Vorschau, Tags und Ablage auf eng aufeinanderfolgenden Zeilen. Sie ist jetzt
bis 320 Einheiten breit; bei schmalen Fenstern bis 280. Einträge haben 16
Einheiten Innenabstand und 8 Abstand zueinander. Titel und Vorschau dürfen
jeweils zwei Zeilen einnehmen. Tags beziehungsweise Ablage stehen gemeinsam
auf einer abschließenden Metadatenzeile. Auswahl, Fokus und Hover bleiben sichtbar.

Die Vorschau wiederholte zusätzlich die gespeicherte Titelüberschrift. Die
bestehende native `document_parts`-Funktion entfernt diese nun nur aus dem
Vorschaudokument. Der Aufwand bleibt auf die bisherigen ersten 2000 Zeichen
begrenzt; ausgewählte Dokumente, Dateien, Suche und Speicherformat bleiben
unverändert. Der vorab fehlschlagende Regressionstest reproduziert die Dopplung
und prüft anschließend auch das Öffnen der vollständigen Notiz.

Die native Ersatzansicht ohne Qt WebEngine erhält dieselbe breitere Spalte,
112 statt 88 Einheiten hohe Einträge, größere Vorschau-/Metadatenschrift und
mehr Innenabstand. Ihre Titel bleiben plattformbedingt einzeilig gekürzt.
Keine neue Einstellung oder Abhängigkeit, kein Server-/Mobile-Umbau.

## Prüfung und Gestaltung

Panorama-Standard und gerenderte Notes-Referenz im Glas-Theme verglichen:
ruhige gemeinsame Flächen, lesbare Hierarchie und getrennte Navigation/Liste/
Schreibfläche. Die breitere Liste ist eine gezielte Anpassung an lange Titel.
Keine zusätzliche globale App-Leiste und kein neuer Arbeitsraum.

Fünf Prüfungen für den echten offline WebEngine-Editor und Themes sowie eine
native Prüfung bestehen gegen Quellmodule; dieselben sechs gegen installierte
Module. Enthalten sind Tabellen/Tags, Speichern, veraltete Eingaben, Konflikte,
Schließen mit aktuellen Browserdaten, Theme-Wechsel und schmale Fenster.
Zusätzliche echte Aufnahmen beider Ansichten in vier Themes bei 1440 × 1000,
1180 × 900 und 960 × 800. Browserauswahl und Filter wurden mit synthetischen
Notizen ausgeführt; alle fünf Originaldateien blieben jeweils hashgleich.

Erste Bildprüfungen hatten zwei Fehler im Prüfstarter: Return wurde an das
falsche Qt-WebEngine-Ziel geschickt; das Suchwort „Heizung“ passte auf zwei
Testnotizen. Ein Mock hatte außerdem den beim Schließen benötigten Sync-Timer
entfernt. Die endgültigen Prüfungen nutzen echte DOM-Auswahl, einen eindeutigen
Filter und die normale Initialisierung im vollständig isolierten Profil.
Fehlerlogs bleiben erhalten; kein entsprechender Produktfix behauptet.

## Installation und Rückweg

Sechs Runtime-Dateien gezielt aktualisiert; 633 andere Code-/Asset-Dateien und
Broker unverändert. Eine anschließende begrenzte Änderung an `notes_web.py`
sichert die bisherige Vorschau-Lesegrenze; mit eigenem Hash-/Rückwegbeleg.
Vorherige Dateien gesichert, Hauptinstallation und Rollback an einer kleinen
Wegwerfkopie geprüft. Keine persönlichen Profile oder Prozesse als Testgeräte
verwendet. Bereits offene Notes-Fenster laden den Stand beim normalen Wiederöffnen.

Belege: `~/.local/state/lumen/notes-list-panorama-20261019/`.
Rückweg zuerst `preview-limit/install-desktop.py rollback --apply`, danach
`install-desktop.py rollback --apply`. Beide verweigern das Überschreiben
zwischenzeitlich veränderter Dateien. Keine echte Server-/Provider-Verbindung
oder vollständige Screenreader-Abnahme durchgeführt; es bleibt ein begrenzter
Desktop-UI-Schritt.
