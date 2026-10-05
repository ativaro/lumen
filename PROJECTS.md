# Lumen Projekte

Links stehen Projekte mit ihren Vorhaben, in der Mitte die Aufgaben, rechts der
ausgewählte Inhalt. Ein Projekt kann mehrere Vorhaben enthalten, jedes Vorhaben
mehrere Aufgaben. Notizen und Material lassen sich auf jeder Ebene anheften.
Dateiverknüpfungen lassen die Originaldatei an ihrem Ort.

| Aufgabenart | Verhalten |
| --- | --- |
| Manuell | Selbst bearbeiten und als erledigt markieren; bei Bedarf wieder öffnen. |
| Recherche | Webquellen mit dem eingerichteten KI-Provider recherchieren. Deep Research ergänzt Gegenprüfung und abschließende Zusammenfassung. |
| Analyse | Angeheftete Inhalte auswerten und das gewünschte Ergebnis erstellen. |
| Automation | Recherche oder Analyse alle 60 Minuten, 24 Stunden oder 7 Tage wiederholen. |

Aufgaben verwenden auch Notizen und Material ihres Projekts und Vorhabens.
Unterlagen werden für den Lauf eingelesen; Textstände, Dateiprüfsummen,
Arbeitsschritte und Ergebnisse bleiben im Ausführungsverlauf erhalten.
Unterstützte Analysequellen: PDF, TXT, Markdown, CSV, Bilder mit OCR, HTML, EPUB
und verknüpfte Lumen-Wissen-Notizen. Andere Dateien können angeheftet und geöffnet
werden; für die Analyse ist ein unterstützter Auszug erforderlich. Pro Datei
gelten 32 MB, insgesamt 120.000 Textzeichen.

Recherche und Analyse brauchen einen eingerichteten KI-Provider. Recherche
verwendet die OpenCode-Websuche und Webabruf; andere Aktionswerkzeuge bleiben
gesperrt. Angeheftete Quellen werden als Kontext an diesen Provider übergeben.
Das allgemeine Lumen-Gedächtnis wird für Projektläufe nicht zusätzlich eingelesen.
Die Webwerkzeuge und ihre Freigaberegeln entsprechen der
[OpenCode-Dokumentation](https://opencode.ai/docs/tools/).

Im Lumen-Chat lassen sich gespeicherte Projekte, Vorhaben, Aufgaben und Ergebnisse
abfragen, etwa „Wie steht mein Projekt?“ oder „Was hat die Recherche ergeben?“.
Lumen kann dafür die aktuellen Projektdaten gezielt nachschlagen. Material wird
als Verknüpfung angezeigt; das Nachschlagen allein liest keine Dokumentdateien
ein und startet keine Aufgabe. Notizen des Projekts und Vorhabens können über die
jeweilige übergeordnete Ebene gelesen werden. Archivierte Einträge werden auf
Anfrage einbezogen. Nach Installation dieser Anbindung Lumen einmal vollständig
schließen und neu öffnen, damit die Chat-Engine die neuen Werkzeuge lädt.

Unter „Ergebnisse“ lässt sich jeder Lauf auswählen. „Auftrag, Quellen und
Arbeitsschritte ansehen“ zeigt den damaligen Kontext. Ergebnisse können als Notiz
in Lumen Wissen gespeichert werden. Ein Rechtsklick auf ein Dokument bietet
Lumen Reader an; Lumen Vault übernimmt die Projektbibliothek einschließlich
Aufgaben und Verlauf sowie die angehefteten lokalen Dateien in einen geprüften
Sicherungsplan. Eingehendes Material lässt sich direkt einem Projekt, Vorhaben
oder einer Aufgabe zuordnen.

Automationen beginnen erst nach Aktivierung. Der erste Lauf erfolgt nach dem
gewählten Intervall; Intervalländerungen setzen diesen Zeitpunkt neu. Ein
Benutzer-Timer prüft ungefähr jede Minute, auch bei geschlossenem Projektfenster.
Der Benutzer muss angemeldet sein, die Bibliothek erreichbar und der Provider
eingerichtet. Während der Hardware-Schonung werden Läufe verschoben. Verpasste
Intervalle werden einmal nachgeholt. Abhängigkeiten müssen erledigt sein;
gleichzeitige Doppelausführungen werden verhindert. Ein Abbruch, Fehler oder
unterbrochener Lauf pausiert die Automation bis zur erneuten Aktivierung.
Benachrichtigungen erscheinen nur bei verändertem Ergebnis oder Fehler.

Archivierte Vorhaben bleiben im Archiv ihres Projekts auffindbar. Bei
archivierten Eltern zuerst das Projekt bzw. Vorhaben wiederherstellen.
Automationen bleiben nach dem Archivieren ausgeschaltet.

Der bisherige Starter `lumen-workbench`, seine Desktop-Kennung und der lokale
Speicher `lumen-tools/workbench` bleiben für bestehende Verweise erhalten.
Die Anwendung heißt jetzt Lumen Projekte. Alte Notizen und Dateien bleiben
erhalten; Fragen werden einmalig als manuelle Aufgaben übernommen. Angefangene
Fragen bleiben als Entwurf im Projekt sichtbar. Es werden keine Beispielprojekte
oder ungefragten KI-Aufträge in der persönlichen Bibliothek angelegt.
