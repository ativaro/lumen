#!/usr/bin/env bash
# opencode-why — explain the last failed shell command (or a given one) and
# suggest a fix. Intended to be sourced:
#
#   source /usr/share/lumen/shell/lumen.bash
#   why                     # explain the previous command + its error
#   why <command>           # explain an explicit command
#

LUMEN_WORKDIR="${LUMEN_WORKDIR:-$HOME/Documents/work}"

opencode_why() {
    local cmd_text="$*"
    if [ -z "$cmd_text" ]; then
        # last history entry (excluding this call)
        cmd_text="$(HISTTIMEFORMAT= builtin history 2>/dev/null | tail -2 | head -1 | sed 's/^ *[0-9]* *//')"
    fi
    [ -z "$cmd_text" ] && { echo "Kein Befehl gefunden. Nutzung: why <Befehl>"; return 1; }

    local prompt="Dieser Shell-Befehl hat einen Fehler verursacht. Erkläre knapp die wahrscheinliche Ursache und gib den konkreten Fix (Befehl(e)). Antworte auf Deutsch.

Befehl:
$cmd_text"

    lumen-agent-app --directory="$LUMEN_WORKDIR" --prompt="$prompt"

}

# `??` is not a valid command name; use the `why` function instead.
# For fish, see shell/lumen.fish.
