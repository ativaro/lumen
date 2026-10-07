# Native Lumen

Lumen ist die sichtbare Anwendung; OpenCode arbeitet ausschließlich als lokale Hintergrund-Engine. Keine Desktop-Aktion öffnet eine Terminaloberfläche.

## Umsetzung
- Gemeinsamer nativer Chat für Lumen und das Seitenpanel in Lumen — Dateien, mit Kontext, lesbaren Antworten, Status und Abbrechen.
- Headless OpenCode über seine lokale HTTP-API; eigener Server mit zufälligem Passwort und ausschließlich Loopback. Vorhandene Provider-/Modellkonfiguration bleibt erhalten, bestehende Terminal-Sessions werden nicht übernommen.
- Werkzeugfreigaben werden standardmäßig einzeln bestätigt oder abgelehnt. Der sichtbare Schalter „Nicht mehr nachfragen“ erlaubt sie optional automatisch; inhaltliche Rückfragen bleiben native Formulare.
- Gespräche sind einem Arbeitsordner zugeordnet und lassen sich fortsetzen oder neu beginnen. Dateien werden nur mit explizitem Dateikontext an eine Anfrage angehängt.
- Kontextmenüs, KRunner, Auswahl-/Zwischenablage- und Screenshot-Aktionen verwenden Lumen. Systemstatus und Berichte bleiben direkt lesbar.
- Vorhandenes PySide6 wird für beide Oberflächen genutzt; die bisherige QML-Shell und Textdatei-Polling-Bridge werden durch denselben Chat ersetzt.

## Prüfung
Native UI-Prüfungen, lokaler HTTP-Testserver für Antwortfortschritt, Fehler, Stoppen, Berechtigungen und Rückfragen; realer OpenCode-Server für API-/Session-Lebenszyklus sowie einen kurzen Modellaufruf. Bestehende Files-Tests bleiben erhalten. Launcher-Tests prüfen Argumente und dass keine Terminalprogramme gestartet werden.

API-Grundlage: https://opencode.ai/docs/server/ und das OpenAPI-Schema der lokal installierten Version.

## Gemeinsame Einstellungen (2026-09-29)
Native Einstellungsansicht, erreichbar in beiden Anwendungen und mit Strg+Komma.
Die Ansicht liest beim Öffnen; jede Änderung braucht einen sichtbaren Übernehmen-
oder Dienstschalter. Keine Modellaufträge, Terminals oder Desktop-Neustarts.

- Lumen: Startordner, Standard-Arbeitsweise, Werkzeugfreigaben, Übersetzungssprache
  und Modellauswahl aus den eingerichteten Providern; bestehende Zugangsdaten bleiben erhalten.
- Files: Startordner/letzter Ordner, versteckte Dateien, Vorschauleiste, Suchverzögerung
  und Trefferlimit; gespeicherte Orte/Server sowie vorhandene native Dateiwerkzeuge.
- Vier globale Lumen-Tastenkürzel mit Konfliktprüfung; lokale Files-/Galerie-Kürzel
  nachschlagbar. Weitere globale Kürzel im KDE-Editor.
- Erscheinungsbild: aktiven Zustand anzeigen; KDE-Editoren für globale Themes,
  Farben, Icons, Mauszeiger, Schriften, Fenster, Effekte, Kvantum und Bildschirme.
  Lumen selbst kann seine dunkle Gestaltung oder den Systemstil verwenden.
- Leisten: tatsächlich vorhandene Panels nach Bildschirm/ID auswählen, Position,
  Größe, Schweben und Ausblendverhalten ändern; native Widget-/Tray-Konfiguration.
- Dienste: reale Zustände von Wächter, Benachrichtigungen, Tages-/Nachtberichten;
  gezieltes Ein-/Ausschalten. Benutzerberichte mit Uhrzeit und optionaler Analyse.
- Integrationen: KRunner, Autostart, Dateizuordnungen, Netzwerk und Systemanpassungen
  über passende native Einstiege und die bestehende Referenz zugänglich.

Prüfung: isolierte Einstellungen und gemockte Systemaufrufe für Schreibpfade,
Konflikte, Fehler, unbekannte IDs und Werte; vorhandene Tests; echte read-only
KDE-/Dienstabfragen und native Ansicht. Keine Änderung der persönlichen
Desktop-Konfiguration allein zum Testen. Komplexe KDE-Einstellungen bleiben
im nativen KDE-Editor, statt in Lumen dupliziert zu werden.

## Nicht mehr nachfragen
- Gemeinsamer Schalter im Chat und in nativen Dateiaktionen, in Lumen und Files. Standard aus; die Auswahl wird in `Lumen/Assistant.conf` für neu geöffnete Fenster/Panel gespeichert. Bereits offene Fenster behalten ihre sichtbare Einstellung.
- Einschalten beantwortet auch bereits wartende Werkzeugfreigaben. Nur das aktuelle Gespräch und nachgewiesene Unteraufgaben; niemals andere Sitzungen. Jede Freigabe wird einzeln mit `once` beantwortet, ohne dauerhafte OpenCode-Regeln zu ändern. Ausschalten fragt ab der nächsten noch nicht erteilten Freigabe wieder nach.
- Der Tooltip nennt automatische Freigaben einschließlich Befehlen und Dateiänderungen. Rückfragen zur Aufgabe bleiben sichtbar; explizite Engine-Verbote, Lesen-/Prüfen-Modus und gesperrte Werkzeuge der Vorschlagsdialoge bleiben wirksam.
- Doppelte/überlappende Abfragen dürfen keine mehrfachen Antworten auslösen. Fehler bleiben sichtbar, alte Antworten nach Gesprächswechsel/Abbruch werden verworfen. Tests mit lokalem HTTP-Server für Ein/Aus, wartende Anfragen, Unteraufgaben/fremde Sitzungen, Fragen und Fehler; echte Engine und native Ansicht prüfen.

## Implementiert
Gemeinsames PySide6-Panel und native Einzelanwendung; lokale authentifizierte API,
getrennte Gespräche je Ordner, Markdown ohne automatische Ressourcenabrufe,
Freigaben/Rückfragen/Abbruch sowie Auswahl- und Bildkontext. Desktop- und
Dateimanager-Einstiege öffnen diese Oberfläche. Vorhandene OpenCode-Anweisungen
und Zugangsdaten werden weiter von OpenCode geladen, nicht von Lumen verändert.

## Nachweise
- Native UI/API-Test mit echtem lokalem HTTP-Testserver: Antwortverlauf,
  fremde Freigabe-IDs ignorieren, echte Unteraufgaben anhand ihrer Eltern zuordnen,
  Ablehnen, Frage beantworten, Abbrechen, Start-/HTTP-Fehler und ausbleibende Antworten.
- Launcher-Test: Leerzeichen, Shell-Sonderzeichen und führende Bindestriche bleiben Daten;
  Ordnerwechsel leert die alte Gesprächsauswahl sofort.
- Echte installierte Engine: privater Server, Gespräch mit Metadaten anlegen/löschen;
  vollständiger Modellaufruf lieferte „Lumen bereit.“ ohne Fehler oder Werkzeuge.
- Native Fenster von Lumen und Lumen — Dateien offscreen gerendert und betrachtet.
- Bestehende Dateimanager-Prüfungen einschließlich lokaler WebDAV-Verbindung laufen mit.

Die UI fragt den Verlauf derzeit alle 450 ms während aktiver Vorgänge ab und
lädt die letzten 100 Nachrichten; bei sehr langen Gesprächen neues Gespräch
beginnen. Die neue Einstellungsansicht kann das Modell für Lumen auswählen;
Provider und Zugangsdaten kommen weiter aus der bestehenden OpenCode-Konfiguration.

### Lebensdauer der Qt-Objekte
Antworten werden zentral über `QNetworkAccessManager.finished` verarbeitet;
Callback-Closures halten keine kurzlebigen Reply-/Timer-Objekte mehr. Nach
Abbruch verhindert die Gesprächsgeneration weitere Poll-Schritte. Prozesssignale
werden vor dem Aufräumen getrennt. Wiederholte separate Testprozesse prüfen das
Schließen während des Engine-Starts (keine Modellaufrufe). Fehlerhafte Antworten
lassen den ursprünglichen Entwurf für einen erneuten Versuch stehen.

## Dateiaktionen als Produktfunktionen (2026-09-29)
„Erklären“, „Fehler beheben“ und „Änderungen prüfen“ starten eigene Vorgänge mit
passendem Titel, sichtbarer Auswahl und Fortschritt. Sie zeigen nur Ergebnisse,
keine generierten Aufträge, Chatrollen, Moduswahl oder Gesprächsauswahl. Erklären
bietet „Mehr Details“, Beheben/Prüfen bieten „Ergebnis prüfen“ (Plan-Agent), außerdem
Abbrechen, erneuter Versuch nach Fehler, Kopieren und Schließen. Freigaben und
Rückfragen bleiben sichtbar. Dateiaktionen beginnen jeweils ein eigenes Gespräch;
der freie Chat bleibt über den bestehenden Lumen-Einstieg erreichbar.

Im Dateimanager bleibt die Aktion im Seitenpanel; externe Kontextmenüs öffnen
kompakte Ergebnisfenster ohne Navigationsleiste. Die Größen solcher Aktionsfenster
überschreiben nicht die gespeicherte Größe der normalen Lumen-App.

Geprüft: 22 Tests einschließlich Ergebnisansicht, verborgenem Auftragstext,
Lesen-/Bearbeiten-Zuordnung, Fehler/erneutem Versuch und echtem Qt-Ereignisablauf
beim Schließen. Zusätzlich eine temporäre Textdatei mit der echten Engine erklärt.
