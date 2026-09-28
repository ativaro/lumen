#!/usr/bin/env bash
# opencode-why — explain the last failed shell command (or a given one) and
# suggest a fix. Intended to be sourced:
#
#   source /usr/share/opencode-agent/shell/opencode.bash
#   why                     # explain the previous command + its error
#   why <command>           # explain an explicit command
#
# Env: OPENCODE_BIN, OPENCODE_TERM, OPENCODE_WORKDIR

OPENCODE_BIN="${OPENCODE_BIN:-$(command -v opencode || echo "$HOME/.opencode/bin/opencode")}"
OPENCODE_TERM="${OPENCODE_TERM:-$(command -v alacritty || command -v konsole || command -v xterm)}"
OPENCODE_WORKDIR="${OPENCODE_WORKDIR:-$HOME/Documents/work}"
TERM_BIN="$(command -v "$OPENCODE_TERM" 2>/dev/null || echo "$OPENCODE_TERM")"

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

    export OPENCODE_PROMPT="$prompt"
    case "$(basename "$TERM_BIN")" in
        alacritty) "$TERM_BIN" --working-directory "$OPENCODE_WORKDIR" -T "opencode: why" \
            -e bash -lc '"$OPENCODE_BIN" run "$OPENCODE_PROMPT"; printf "\n--- Fertig. Enter zum Schließen. ---\n"; read -r _' ;;
        konsole)   "$TERM_BIN" --workdir "$OPENCODE_WORKDIR" -p tabtitle="opencode: why" \
            -e bash -lc '"$OPENCODE_BIN" run "$OPENCODE_PROMPT"; printf "\n--- Fertig. Enter zum Schließen. ---\n"; read -r _' ;;
        *)         "$TERM_BIN" -e bash -lc 'cd "'"$OPENCODE_WORKDIR"'"; "$OPENCODE_BIN" run "$OPENCODE_PROMPT"' ;;
    esac
}

# `??` is not a valid command name; use the `why` function instead.
# For fish, see shell/opencode.fish.
