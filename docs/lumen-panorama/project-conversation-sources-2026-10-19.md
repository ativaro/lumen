> **Historischer Entwurf oder Abnahmebeleg – keine aktuelle Installationsanleitung.** Diese datierte Abnahme gehört zum damaligen Kandidaten. Enthaltene lokale Notes-/Projekt-/Code-/Audio-Editoren sind inzwischen durch Server-Apps ersetzt; nur die Gestaltungsentscheidung bleibt als Referenz bestehen. Aktuelle Zuordnung: [Desktop-Verantwortlichkeiten](../desktop-retirement.md).

# Projektgespräche und lesbare Quellen

Desktop-Korrektur vom 19.10.2026. Keine neue globale Projektauswahl,
kein Arbeitsraum und keine neue Datenbanktabelle.

„Weiterdenken mit Lumen“ öffnet weiterhin nur einen Entwurf. Der Aufruf trägt
jetzt zusätzlich `--draft-project`. Nach tatsächlichem Senden und Anlegen der
Sitzung schreibt der native Assistent einen bestehenden Gesprächsverweis in
`records.data.references`. Die Projektliste aktualisiert sich über ihren
vorhandenen Poller. Titel ist die erste Zeile der Frage; unveränderte Originale,
andere Verweise und parallele Projektänderungen bleiben erhalten. Archivierte
und nur lesbare Projekte lehnen die Zuordnung ab. Neue Gespräche und andere
Kontexte übernehmen die Zuordnung nicht; ungesendete Wiederherstellungsentwürfe
behalten sie. Fehler werden im Gespräch angezeigt.

`lumen_project_search` liest zusätzlich direkt zugeordnete Dateien, DOCX/PPTX/XLSX
und deren Makrovarianten als Text sowie lokal gespeicherte Fragen/Antworten aus
ausdrücklich verknüpften Gesprächen. Ordner und Unterordner bleiben live verknüpft.
Die gemeinsame Dateisuche verwendet denselben Office-Leser. Keine neue Abhängigkeit.
Die Zelltexte werden anhand der [Shared String Table](https://learn.microsoft.com/en-us/office/open-xml/spreadsheet/working-with-the-shared-string-table)
aufgelöst; [Folientexte](https://learn.microsoft.com/en-us/office/open-xml/presentation/how-to-get-all-the-text-in-all-slides-in-a-presentation)
folgen der gespeicherten Reihenfolge. Belege behalten Datei/Zeile, Foliennummer,
Tabellenblatt/Zelle beziehungsweise Gespräch/Auftrag/Rolle.

Grenzen bleiben ausdrücklich: kein persistenter RAG-/Vektorindex, kein vollständiger
Office-Layout-/Diagramm-/Bildleser, keine automatische OCR oder Auswertung von
ISO/AppImage/ZIP-Inhalten. Formeln werden nicht ausgeführt; fehlende gespeicherte
Ergebnisse sind gekennzeichnet. Keine Makros, externen Links oder XML-Entitäten.
Office: maximal 64 MiB Archiv, 8 MiB pro XML-Teil, insgesamt 32 MiB XML und 1 MiB
Text; Überschreitungen/Fehler werden gemeldet. Sucharbeiter bleiben begrenzt und
abbrechbar; veränderte oder entfernte Quellen werden erneut geprüft.

Gesprächssuche liest ausschließlich passende lokale `tasks.directory/session`
mit höchstens 100 gespeicherten Aufträgen und 20.000/40.000 Zeichen pro Frage/
Antwort. Nicht verknüpfte Gespräche werden nicht als Quellen ausgewählt. Fehlende
ältere oder serverseitige Verläufe werden als nicht verfügbar ausgewiesen.
KI-Antworten sind bisherige Analysen; sie ersetzen keine Originalbelege und können
veraltet sein. Das Wiederverwenden erteilt keine Ausführungsberechtigung.

Technischer Altverweis: `agent-app/main.py --page workplace` führt über
`lumen_detail_routes.py` zu Lumen Projekte. `StudioWorkspaces` zeigt den technischen
Gesprächsordner und den Projekte-Einstieg; keine globale Arbeitsraumauswahl.
Diese Namenskompatibilität wird in dieser Datenwegkorrektur nicht umgebaut.

Abnahmebelege, Sourcepins, isolierte Testprofile, tatsächliche Vorher-/Nachherbilder,
Installationsmanifest und selektiver Rückweg liegen unter
`~/.local/state/lumen/project-conversation-sources-20261019/`.
