# opencode — fish integration
#
# Source from config.fish:
#   source /usr/share/opencode-lumen/shell/lumen.fish
#
# Then:
#   why                 # explain the last failed command
#   why <command>       # explain an explicit command
#   vix                 # screenshot region -> opencode vision
#   sel explain|fix|translate|summarize   # act on the selection/clipboard

set -g LUMEN_WORKDIR $HOME/Documents/work

function why --description "Lumen: explain last failed command"
    set -l cmd_text (string join ' ' $argv)
    if test -z "$cmd_text"
        set cmd_text (history --max=1 | string replace -r '^\s*- cmd:\s*' '')
    end
    if test -z "$cmd_text"
        echo "Kein Befehl gefunden. Nutzung: why <Befehl>"
        return 1
    end
    set -lx LUMEN_PROMPT "Dieser Shell-Befehl hat einen Fehler verursacht. Erkläre knapp die wahrscheinliche Ursache und gib den konkreten Fix (Befehl(e)). Antworte auf Deutsch.\n\nBefehl:\n$cmd_text"
    lumen-agent-app --directory="$LUMEN_WORKDIR" --prompt="$LUMEN_PROMPT"
end

function vix --description "Lumen: screenshot region -> vision"
    lumen-vision region
end

function sel --description "Lumen: act on selection/clipboard"
    lumen-sel $argv
end
