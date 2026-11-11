# Desktop-Funktionen und Zuständigkeiten

Diese Zuordnung beschreibt die aktuelle Quellstruktur. Ein Startername allein sagt nicht, dass die betreffende App lokal arbeitet.

| Bereich | Verantwortung | Voraussetzung |
| --- | --- | --- |
| Lumen / Search | Gespräche, ausgewählte Dateien, Systemhilfe und genehmigte Aktionen | Lokale Engine; KI-Anbieter für Antworten |
| Files | Lokale Dateien, NAS, Online-Konten, optionale Drive-Ansicht | Qt/GIO; Netzwerkfunktionen bei Bedarf |
| Reader | Private Lesekopien, PDF/EPUB/Text/Office, Markierungen und Vorlesen | Eigener PDF-Kern und eigener Office-Leser; Stimme optional |
| Compose | Lokale Text-/PDF-Bearbeitung, Übersetzen/Korrigieren | KI-Anbieter für Verarbeitung |
| Haushalt | Lokale Geräte/Verträge, Fristen und Belege | Lokale Tools-Bibliothek |
| System / Sound / Sicherungen | Diagnose, Audio und lokale Backup-Pläne | Lokale Systemfunktionen; Restic/Ziel für Backups |
| Gedächtnis | Lokale Erinnerungen und begrenztes Lernen mit Freigaben | Eigene Einstellungen; Modell für Lernen |
| Notes, Projekte, Code, Inbox, Audio Studio, Vault | Gemeinsame Inhalte und Produktiv-Apps | Lumen Server, Konto und passende Gerätefreigaben |
| Nativer Vault-Broker | Bestätigte lokale Zugangsdatenoperationen | Separat eingerichtete native Vorabversion, keine allgemeine Freigabe |

Alte lokale Projekt- und Notes-Oberflächen sowie Inbox-/Audio-Runner sind aus der Auslieferung entfernt. Vorhandene Benutzerdaten bleiben erhalten; daraus folgt kein automatischer Import und kein Offline-Modus der Server-Apps.

[Bedienung](TOOLS.md) · [Desktop-Verantwortlichkeiten](docs/desktop-retirement.md) · [Reader und Sound](READER-SOUND.md) · [Notes und Gedächtnis](WISSEN.md)
