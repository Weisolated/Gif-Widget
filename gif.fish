# ============================================================================
# gif.fish - Floating GIF Widget Controller
# Speicherort: ~/.config/fish/functions/gif.fish
# ============================================================================
#
# QUICK USAGE:
#   gif <name> [-always]     Starten
#   gif edit                 GLOBAL TOGGLE: alle GIFs in Edit-Mode (oder zurück)
#   gif lock                 Alle sperren (game-ready)
#   gif unlock               Alle entsperren
#   gif kill-all             Alle beenden
#   gif list                 Was läuft
#
# Mit Name (für einzelne Widgets):
#   gif lock/unlock/toggle <name>
#   gif move <name> X Y / nudge <name> DX DY / scale <name> F
#   gif corner <name> tl|tr|bl|br|center
#   gif kill <name>
# ============================================================================

set -g GIF_SCRIPT_PATH "$HOME/Scripts/gif-script.py"
set -g GIF_DIR "$HOME/Scripts"

function gif --description "Floating GIF Widget steuern"
    if test (count $argv) -eq 0
        _gif_help
        return 0
    end

    set -l first $argv[1]

    switch $first
        case help -h --help
            _gif_help
            return 0

        case list ls
            _gif_run_cmd list
            return $status

        case kill-all
            _gif_kill_all
            return $status

        case kill stop
            if test -z "$argv[2]"
                echo "❌ Fehlt: Name. Oder nutze 'gif kill-all'"
                return 1
            end
            _gif_kill_one $argv[2]
            return $status

        # === GLOBALE Aktionen wenn ohne Name aufgerufen ===
        case edit
            _gif_edit_toggle
            return $status

        case toggle
            if test -z "$argv[2]"
                _gif_edit_toggle
            else
                _gif_simple_action toggle $argv[2]
            end
            return $status

        case lock
            if test -z "$argv[2]"
                _gif_lock_all
            else
                _gif_simple_action lock $argv[2]
            end
            return $status

        case unlock
            if test -z "$argv[2]"
                _gif_unlock_all
            else
                _gif_simple_action unlock $argv[2]
            end
            return $status

        case pause play status
            if test -z "$argv[2]"
                _gif_apply_to_all $first
            else
                _gif_simple_action $first $argv[2]
            end
            return $status

        case move
            _gif_move_abs $argv[2..]
            return $status

        case nudge
            _gif_move_rel $argv[2..]
            return $status

        case scale
            _gif_scale $argv[2..]
            return $status

        case corner
            _gif_corner $argv[2..]
            return $status

        case '*'
            # Default: 1. arg ist GIF-Name → starten
            _gif_start $argv
            return $status
    end
end

# ===========================================================================
# Helpers
# ===========================================================================

function _gif_help
    echo "gif - Floating GIF Widget Controller"
    echo ""
    echo "▸ Starten:"
    echo "    gif <name>                   Im Vordergrund"
    echo "    gif <name> -always           Im Hintergrund (überlebt Terminal)"
    echo ""
    echo "▸ Globale Steuerung (perfekt für Niri-Keybinds):"
    echo "    gif edit                     TOGGLE alle GIFs zwischen lock/unlock"
    echo "    gif lock                     Alle sperren (game-ready)"
    echo "    gif unlock                   Alle entsperren (verschiebbar)"
    echo "    gif kill-all                 Alle beenden"
    echo "    gif list                     Was läuft"
    echo ""
    echo "▸ Einzeln (mit Name):"
    echo "    gif toggle/lock/unlock <name>"
    echo "    gif move <name> X Y          Auf Position"
    echo "    gif nudge <name> DX DY       Relativ verschieben"
    echo "    gif scale <name> F           1.0 = original, 0.5 = halb"
    echo "    gif corner <name> POS        tl/tr/bl/br/center"
    echo "    gif pause/play <name>        Animation steuern"
    echo "    gif status <name>            State anzeigen"
    echo "    gif kill <name>              Beenden"
    echo ""
    echo "Im unlocked-State: Linksklick+Drag = verschieben, Rechtsklick = lock,"
    echo "Scrollen = skalieren. Pinker Rahmen zeigt unlocked an."
end

function _gif_run_cmd
    if not test -f $GIF_SCRIPT_PATH
        echo "❌ Script nicht gefunden: $GIF_SCRIPT_PATH"
        return 1
    end
    python3 $GIF_SCRIPT_PATH $argv
end

function _gif_running_ids
    if test -f $GIF_SCRIPT_PATH
        python3 $GIF_SCRIPT_PATH list 2>/dev/null
    end
end

function _gif_available_gifs
    for f in $GIF_DIR/*.gif
        if test -e $f
            echo (basename $f .gif)
        end
    end
end

function _gif_is_unlocked
    set -l id $argv[1]
    set -l result (python3 $GIF_SCRIPT_PATH ipc $id status 2>/dev/null)
    # Status-JSON enthält "locked": true|false
    if string match -q '*"locked": false*' -- $result
        return 0  # ist unlocked
    end
    return 1  # ist locked oder Fehler
end

# ===========================================================================
# Globale Aktionen (alle Widgets)
# ===========================================================================

function _gif_edit_toggle
    set -l ids (_gif_running_ids)
    if test (count $ids) -eq 0
        echo "ℹ️  Keine laufenden Widgets."
        return 1
    end

    # Wenn IRGENDEIN Widget unlocked ist → alle locken (zurück in game-mode)
    # Sonst → alle entsperren (edit-mode)
    set -l any_unlocked 0
    for id in $ids
        if _gif_is_unlocked $id
            set any_unlocked 1
            break
        end
    end

    if test $any_unlocked -eq 1
        for id in $ids
            python3 $GIF_SCRIPT_PATH ipc $id lock >/dev/null 2>&1
        end
        echo "🔒 Alle gesperrt – game-ready ($ids)"
    else
        for id in $ids
            python3 $GIF_SCRIPT_PATH ipc $id unlock >/dev/null 2>&1
        end
        echo "🔓 Edit-Mode AN – jetzt mit Maus verschieben ($ids)"
    end
end

function _gif_lock_all
    set -l ids (_gif_running_ids)
    if test (count $ids) -eq 0
        echo "ℹ️  Keine laufenden Widgets."
        return 1
    end
    for id in $ids
        python3 $GIF_SCRIPT_PATH ipc $id lock >/dev/null 2>&1
    end
    echo "🔒 Alle gesperrt: $ids"
end

function _gif_unlock_all
    set -l ids (_gif_running_ids)
    if test (count $ids) -eq 0
        echo "ℹ️  Keine laufenden Widgets."
        return 1
    end
    for id in $ids
        python3 $GIF_SCRIPT_PATH ipc $id unlock >/dev/null 2>&1
    end
    echo "🔓 Alle entsperrt: $ids"
end

function _gif_apply_to_all
    set -l action $argv[1]
    set -l ids (_gif_running_ids)
    if test (count $ids) -eq 0
        echo "ℹ️  Keine laufenden Widgets."
        return 1
    end
    for id in $ids
        python3 $GIF_SCRIPT_PATH ipc $id $action
    end
end

function _gif_kill_all
    set -l ids (_gif_running_ids)
    if test (count $ids) -eq 0
        echo "ℹ️  Keine laufenden Widgets."
        return 0
    end
    for id in $ids
        echo "🛑 Beende '$id'..."
        python3 $GIF_SCRIPT_PATH ipc $id quit >/dev/null 2>&1
    end
end

# ===========================================================================
# Einzelne Aktionen
# ===========================================================================

function _gif_start
    set -l name $argv[1]
    set -l flag $argv[2]
    set -l gif_path "$GIF_DIR/$name.gif"

    if not test -f $GIF_SCRIPT_PATH
        echo "❌ Script nicht gefunden: $GIF_SCRIPT_PATH"
        return 1
    end
    if not test -f $gif_path
        echo "❌ GIF nicht gefunden: $gif_path"
        echo "   Verfügbar:"
        for g in (_gif_available_gifs)
            echo "     $g"
        end
        return 1
    end

    if test "$flag" = "-always"
        echo "🚀 Starte '$name' (Hintergrund)..."
        nohup python3 $GIF_SCRIPT_PATH run $gif_path >/dev/null 2>&1 &
        disown
    else
        echo "🚀 Starte '$name'... ('gif edit' zum Verschieben)"
        python3 $GIF_SCRIPT_PATH run $gif_path &
    end
end

function _gif_kill_one
    set -l name $argv[1]
    python3 $GIF_SCRIPT_PATH ipc $name quit >/dev/null 2>&1
    if test $status -eq 0
        echo "✅ '$name' beendet."
    else
        echo "⚠️  '$name' nicht erreichbar – versuche pkill..."
        pkill -f "gif-script.py.*$name.gif" 2>/dev/null
    end
end

function _gif_simple_action
    set -l action $argv[1]
    set -l name $argv[2]
    if test -z "$name"
        echo "❌ Fehlt: Widget-Name"
        return 1
    end
    python3 $GIF_SCRIPT_PATH ipc $name $action
end

function _gif_move_abs
    if test (count $argv) -lt 3
        echo "Usage: gif move <name> <x> <y>"
        return 1
    end
    python3 $GIF_SCRIPT_PATH ipc $argv[1] move $argv[2] $argv[3]
end

function _gif_move_rel
    if test (count $argv) -lt 3
        echo "Usage: gif nudge <name> <dx> <dy>"
        return 1
    end
    python3 $GIF_SCRIPT_PATH ipc $argv[1] move-by $argv[2] $argv[3]
end

function _gif_scale
    if test (count $argv) -lt 2
        echo "Usage: gif scale <name> <factor>"
        return 1
    end
    python3 $GIF_SCRIPT_PATH ipc $argv[1] scale $argv[2]
end

function _gif_corner
    if test (count $argv) -lt 2
        echo "Usage: gif corner <name> <tl|tr|bl|br|center>"
        return 1
    end
    python3 $GIF_SCRIPT_PATH ipc $argv[1] corner $argv[2]
end

# ===========================================================================
# Tab-Completion
# ===========================================================================

complete -c gif -e

function _gif_first_arg_completions
    echo -e "edit\tGLOBAL: alle togglen (lock⇄unlock)"
    echo -e "lock\tAlle sperren (oder einzeln mit Name)"
    echo -e "unlock\tAlle entsperren (oder einzeln)"
    echo -e "toggle\tAlle togglen (oder einzeln mit Name)"
    echo -e "list\tLaufende Widgets auflisten"
    echo -e "kill\tEinzelnes Widget beenden"
    echo -e "kill-all\tAlle Widgets beenden"
    echo -e "move\tAuf Position setzen"
    echo -e "nudge\tRelativ verschieben"
    echo -e "scale\tSkalierung setzen"
    echo -e "corner\tIn Bildschirmecke"
    echo -e "pause\tAnimation pausieren"
    echo -e "play\tAnimation fortsetzen"
    echo -e "status\tStatus anzeigen"
    echo -e "help\tHilfe"
    for g in (_gif_available_gifs)
        echo -e "$g\tGIF starten"
    end
end

complete -c gif \
    -n "test (count (commandline -opc)) -eq 1" \
    -a "(_gif_first_arg_completions)" \
    -f

# 2. arg nach Subcommand → laufende IDs
complete -c gif \
    -n "test (count (commandline -opc)) -eq 2; and contains (commandline -opc)[2] kill stop lock unlock toggle pause play status move nudge scale corner" \
    -a "(_gif_running_ids)" \
    -f

# 3. arg nach corner → Positionen
complete -c gif \
    -n "test (count (commandline -opc)) -eq 3; and test (commandline -opc)[2] = corner" \
    -a "tl tr bl br center" \
    -f

# 2. arg falls 1. arg ein GIF-Name war → -always
complete -c gif \
    -n "test (count (commandline -opc)) -eq 2; and not contains (commandline -opc)[2] edit list kill kill-all stop lock unlock toggle pause play status move nudge scale corner help" \
    -a "-always" \
    -f
