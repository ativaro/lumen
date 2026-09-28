# opencode — fish integration
#
# Source from config.fish:
#   source /usr/share/opencode-lumen/shell/opencode.fish
#
# Then:
#   why                 # explain the last failed command
#   why <command>       # explain an explicit command
#   vix                 # screenshot region -> opencode vision
#   sel explain|fix|translate|summarize   # act on the selection/clipboard

set -g LUMEN_OPENCODE_BIN (command -v opencode; or echo $HOME/.opencode/bin/opencode)
set -g LUMEN_TERM (command -v alacritty; or command -v konsole; or echo xterm)
set -g LUMEN_WORKDIR $HOME/Documents/work

function why --description "opencode: explain last failed command"
    set -l cmd_text (string join ' ' $argv)
    if test -z "$cmd_text"
        set cmd_text (history --max=1 | string replace -r '^\s*- cmd:\s*' '')
    end
    if test -z "$cmd_text"
        echo "Kein Befehl gefunden. Nutzung: why <Befehl>"
        return 1
    end
    set -lx LUMEN_PROMPT "Dieser Shell-Befehl hat einen Fehler verursacht. Erkläre knapp die wahrscheinliche Ursache und gib den konkreten Fix (Befehl(e)). Antworte auf Deutsch.\n\nBefehl:\n$cmd_text"
    $LUMEN_TERM --working-directory $LUMEN_WORKDIR -T "opencode: why" \
        -e bash -lc '"$LUMEN_OPENCODE_BIN" run "$LUMEN_PROMPT"; printf "\n--- Fertig. Enter zum Schließen. ---\n"; read -r _'
end

function vix --description "opencode: screenshot region -> vision"
    lumen-vision region
end

function sel --description "opencode: act on selection/clipboard"
    lumen-sel $argv
end
