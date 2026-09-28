---
description: Diagnose und Fix eines Systemproblems (Dienste, Logs, Disk, GPU)
---

Hilf beim Diagnostizieren und Beheben eines Systemproblems.

Vorgehen:
1. **Verstehen**: Formuliere zuerst in einem Satz, welches Symptom zu beheben ist (aus `$ARGUMENTS` und Kontext).
2. **Diagnose**: Sammle gezielt Belege — nutze das MCP-Tool **`cachyos`** (`systemctl`, `journal`, `pacman`, `disk`, `gpu`, `memory`, `kwin`, `cmd`) und bei Bedarf Systemwerkzeuge (`journalctl`, das systemeigene D-Bus-CLI, Paketmanager).
3. **Hypothese**: Nenne die wahrscheinlichste Ursache und was dagegen spricht.
4. **Fix**: Schlage die kleinste, reversible Änderung vor. Nenne exakte Befehle/Pfade. Bei Systemänderungen: Backup anlegen.
5. **Verifizieren**: Wie prüfen wir, dass es behoben ist?

Konsultiere vorhandene Referenzdateien (z. B. `system.md`/`sync.md` im aktuellen
oder übergeordneten Verzeichnis), bevor du Annahmen triffst.

Sicherheit: Keine destruktiven Befehle ohne Rückfrage. Bei Paket-Eingriffen und
Systemdateien immer erst Backup + kurze Bestätigung. Niemals den D-Bus neustarten.

$ARGUMENTS
