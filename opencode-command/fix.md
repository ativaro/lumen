---
description: Diagnose und Fix eines Systemproblems (Dienste, GPU, Disk, KDE)
---

Hilf beim Diagnostizieren und Beheben eines Systemproblems auf diesem CachyOS/KDE-Rechner.

Vorgehen:
1. **Verstehen**: Formuliere zuerst in einem Satz, welches Symptom zu beheben ist (aus `$ARGUMENTS` und Kontext).
2. **Diagnose**: Sammle gezielt Belege — nutze das MCP-Tool **`cachyos`** (`systemctl`, `journal`, `pacman`, `disk`, `gpu`, `memory`, `kwin`, `cmd`) und bei Bedarf KDE-/KWin-Werkzeuge (`qdbus6`, `kreadconfig6`, `journalctl --user`).
3. **Hypothese**: Nenne die wahrscheinlichste Ursache und was dagegen spricht.
4. **Fix**: Schlage die kleinste, reversible Änderung vor. Nenne exakte Befehle/Pfade. Bei Systemänderungen: Backup anlegen.
5. **Verifizieren**: Wie prüfen wir, dass es behoben ist?

Wichtige Systemfakten stehen in `/home/example/Documents/work/system.md` und `sync.md` — konsultiere sie, bevor du Annahmen triffst.

Sicherheit: Keine destruktiven Befehle ohne Rückfrage. Bei `pacman`-Eingriffen und Systemdateien immer erst Backup + kurze Bestätigung.

$ARGUMENTS
