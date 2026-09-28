# opencode — fish integration
#
# Source from config.fish:
#   source /usr/share/opencode-agent/shell/opencode.fish
#
# Then:
#   why                 # explain the last failed command
#   why <command>       # explain an explicit command
#   vix                 # screenshot region -> opencode vision
#   sel explain|fix|translate|summarize   # act on the selection/clipboard

set -g OPENCODE_BIN (command -v opencode; or echo $HOME/.opencode/bin/opencode)
set -g OPENCODE_TERM (command -v alacritty; or command -v konsole; or echo xterm)
set -g OPENCODE_WORKDIR $HOME/Documents/work

function why --description "opencode: explain last failed command"
    set -l cmd_text (string join ' ' $argv)
    if test -z "$cmd_text"
        set cmd_text (history --max=1 | string replace -r '^\s*- cmd:\s*' '')
    end
    if test -z "$cmd_text"
        echo "Kein Befehl gefunden. Nutzung: why <Befehl>"
        return 1
    end
    set -lx OPENCODE_PROMPT "Dieser Shell-Befehl hat einen Fehler verursacht. Erkläre knapp die wahrscheinliche Ursache und gib den konkreten Fix (Befehl(e)). Antworte auf Deutsch.\n\nBefehl:\n$cmd_text"
    $OPENCODE_TERM --working-directory $OPENCODE_WORKDIR -T "opencode: why" \
        -e bash -lc '"$OPENCODE_BIN" run "$OPENCODE_PROMPT"; printf "\n--- Fertig. Enter zum Schließen. ---\n"; read -r _'
end

function vix --description "opencode: screenshot region -> vision"
    opencode-vision region
end

function sel --description "opencode: act on selection/clipboard"
    opencode-sel $argv
end
