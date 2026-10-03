# Eigenständige Desktop-Werkzeuge

Auftrag: Meeting-Werkstatt (3), digitaler Haushalt (4), Projekt-Werkbank (6), persönliches Radio (7). Eigene Fenster/Starter, gemeinsame lokale Laufzeit und Themes. Pictus und Numen bleiben separate Projekte. Kreativstudio nur als Pictus-Roadmap.

| Modul | Verantwortung | Abhängigkeit |
|---|---|---|
| tools-common | Private Speicherung, Dateiimport, Jobs, Darstellung, Audio, KI-Vorschläge | vorhandene Qt-/Lumen-Laufzeit |
| meetings | Aufnahme importieren, lokal transkribieren, Zeitstellen, Entscheidungen/Aufgaben | tools-common, Whisper/ffmpeg |
| household | Geräte/Verträge mit Fristen und Belegen verwalten, suchen | tools-common |
| workbench | Projektdateien, Links, Notizen und offene Fragen zusammenführen | tools-common |
| radio | Gewählte Artikel/Dokumente zu hörbarer Ausgabe mit Quellen machen | tools-common, Piper |
| vault | Verschlüsselte USB-/NAS-Sicherung, Vorschau, Zeitplan, Verlauf und Wiederherstellung in neue Ordner | tools-common, Restic, Secret Service |
| inbox | IMAP/SMTP, Proton Bridge, CalDAV/ICS, lokale Entwürfe und Aufgaben | tools-common, Secret Service, optionales Kalender-Environment |

Reihenfolge: common → meetings → household → workbench → radio → Installation/Verifikation.

Vault und Inbox: Einrichtung und Grenzen stehen in [VAULT-INBOX.md](VAULT-INBOX.md).
