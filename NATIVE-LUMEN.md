# Native Lumen

Lumen ist die sichtbare Anwendung; OpenCode arbeitet ausschließlich als lokale Hintergrund-Engine. Keine Desktop-Aktion öffnet eine Terminaloberfläche.

## Umsetzung
- Gemeinsamer nativer Chat für Lumen und das Seitenpanel in Lumen Files, mit Kontext, lesbaren Antworten, Status und Abbrechen.
- Headless OpenCode über seine lokale HTTP-API; eigener Server mit zufälligem Passwort und ausschließlich Loopback. Vorhandene Provider-/Modellkonfiguration bleibt erhalten, bestehende Terminal-Sessions werden nicht übernommen.
- Berechtigungen und Rückfragen der Engine werden als native Bedienelemente angezeigt, niemals automatisch bestätigt.
- Gespräche sind einem Arbeitsordner zugeordnet und lassen sich fortsetzen oder neu beginnen. Dateien werden nur mit explizitem Dateikontext an eine Anfrage angehängt.
- Kontextmenüs, KRunner, Auswahl-/Zwischenablage- und Screenshot-Aktionen verwenden Lumen. Systemstatus und Berichte bleiben direkt lesbar.
- Vorhandenes PyQt5 wird für beide Oberflächen genutzt; die bisherige QML-Shell und Textdatei-Polling-Bridge werden durch denselben Chat ersetzt.

## Prüfung
Native UI-Prüfungen, lokaler HTTP-Testserver für Antwortfortschritt, Fehler, Stoppen, Berechtigungen und Rückfragen; realer OpenCode-Server für API-/Session-Lebenszyklus sowie einen kurzen Modellaufruf. Bestehende Files-Tests bleiben erhalten. Launcher-Tests prüfen Argumente und dass keine Terminalprogramme gestartet werden.

API-Grundlage: https://opencode.ai/docs/server/ und das OpenAPI-Schema der lokal installierten Version.

## Implementiert
Gemeinsames PyQt5-Panel und native Einzelanwendung; lokale authentifizierte API,
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
- Native Fenster von Lumen und Lumen Files offscreen gerendert und betrachtet.
- Bestehende Dateimanager-Prüfungen einschließlich lokaler WebDAV-Verbindung laufen mit.

Die UI fragt den Verlauf derzeit alle 450 ms während aktiver Vorgänge ab und
lädt die letzten 100 Nachrichten; bei sehr langen Gesprächen neues Gespräch
beginnen. Modell-/Providerwahl erfolgt weiter über die bestehende OpenCode-Konfiguration.
