---
description: Systemgesundheit prüfen (Units, Logs, Disk, GPU, RAM)
---

Erstelle einen kompakten Systemgesundheits-Bericht für dieses System.

Nutze bevorzugt das MCP-Tool **`cachyos`** (Tools: `systemctl`, `journal`, `pacman`, `disk`, `gpu`, `memory`, `sensors`, `kwin`, `cmd`). Falle nur wenn nötig auf Bash zurück.

Prüfe:
1. **Fehlgeschlagene Units** – `systemctl` (system + user scope).
2. **Auffällige Logs** – `journal` mit Priorität `err`/`warning` der letzten Zeit.
3. **Speicherplatz** – `disk` für `/` und `/mnt/games`.
4. **GPU** – `gpu` (Auslastung, VRAM, Temperatur, Leistung).
5. **RAM/Swap + Load** – `memory`.
6. **Temperaturen** – `sensors`, falls verfügbar.

Gib das Ergebnis als knappe Markdown-Tabelle + kurze Befunde aus. Markiere Probleme mit ⚠ und nenne für jedes Problem einen konkreten nächsten Schritt. Wenn alles in Ordnung ist, sag das klar.

$ARGUMENTS
