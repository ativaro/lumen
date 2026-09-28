#!/usr/bin/env python3
"""
cachyos-mcp — a stdlib-only MCP (Model Context Protocol) server exposing
read-mostly system introspection tools for CachyOS / KDE Plasma.

Transport: JSON-RPC 2.0 over stdio, newline-delimited (MCP stdio transport).
No third-party dependencies.

Run:  lumen_mcp.py
Wire into opencode via ~/.config/opencode/opencode.jsonc -> mcp.cachyos
"""

import json
import os
import shlex
import subprocess
import sys

SERVER_NAME = "cachyos-mcp"
SERVER_VERSION = "0.2.0"
PROTOCOL_VERSION = "2024-11-05"

# Writing actions (restart units, media control, notifications, …) are OFF by
# default. Enable explicitly with LUMEN_MCP_ACTIONS=1.
ACTIONS_ENABLED = os.environ.get("LUMEN_MCP_ACTIONS", "0") == "1"

# ---- helpers ---------------------------------------------------------------


def run(cmd, timeout=20):
    """Run a command (list form), return dict with rc/stdout/stderr."""
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {"rc": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}
    except FileNotFoundError:
        return {"rc": 127, "stdout": "", "stderr": f"command not found: {cmd[0]}"}
    except subprocess.TimeoutExpired:
        return {"rc": 124, "stdout": "", "stderr": f"timeout after {timeout}s: {cmd}"}


def ok(text):
    return [{"type": "text", "text": text}]


def fmt(res):
    out = res["stdout"]
    if res["stderr"]:
        out += f"\n[stderr]\n{res['stderr']}"
    if res["rc"] != 0:
        out += f"\n[exit {res['rc']}]"
    return out.strip() or "(keine Ausgabe)"


# ---- tool implementations --------------------------------------------------

ALLOWED_SYSTEMCTL_ACTIONS = {"status", "is-active", "is-enabled", "list-units", "list-unit-files"}
ALLOWED_PACMAN_ACTIONS = {"-Ss", "-Qs", "-Qi", "-Q", "-Si"}


def tool_systemctl(args):
    action = args.get("action", "status")
    unit = args.get("unit", "")
    scope = args.get("scope", "system")  # system | user
    if action not in ALLOWED_SYSTEMCTL_ACTIONS:
        return ok(f"Ungültige Aktion '{action}'. Erlaubt: {sorted(ALLOWED_SYSTEMCTL_ACTIONS)}")
    cmd = ["systemctl"]
    if scope == "user":
        cmd.append("--user")
    if action == "list-units":
        cmd += ["list-units", "--no-pager", "--type=service", "--state=failed"]
        if unit:
            cmd = ["systemctl", "--user" if scope == "user" else "--system", "list-units", unit, "--no-pager"]
    elif action == "list-unit-files":
        cmd += ["list-unit-files", "--no-pager"]
        if unit:
            cmd += [f"{unit}"]
    else:
        if unit:
            cmd += [action, unit]
        else:
            cmd += [action]
    return ok(fmt(run(cmd)))


def tool_journal(args):
    unit = args.get("unit", "")
    lines = int(args.get("lines", 50))
    lines = max(1, min(lines, 500))
    scope = args.get("scope", "system")
    priority = args.get("priority", "")  # e.g. "err" or "warning"
    cmd = ["journalctl", "--no-pager", "-n", str(lines), "-o", "short"]
    if scope == "user":
        cmd.append("--user")
    if unit:
        cmd += ["-u", unit]
    if priority:
        cmd += ["-p", priority]
    return ok(fmt(run(cmd)))


def tool_pacman(args):
    action = args.get("action", "-Ss")
    query = args.get("query", "")
    if action not in ALLOWED_PACMAN_ACTIONS:
        return ok(f"Ungültige Aktion '{action}'. Erlaubt: {sorted(ALLOWED_PACMAN_ACTIONS)}")
    cmd = ["pacman", action]
    if query:
        cmd.append(query)
    return ok(fmt(run(cmd)))


def tool_disk(args):
    path = args.get("path", "/")
    return ok(fmt(run(["df", "-h", path])))


def tool_gpu(args):
    res = run(
        [
            "nvidia-smi",
            "--query-gpu=name,utilization.gpu,memory.used,memory.total,power.draw,temperature.gpu",
            "--format=csv",
        ]
    )
    return ok(fmt(res))


def tool_memory(args):
    out = fmt(run(["free", "-h"]))
    out += "\n\n" + fmt(run(["uptime"]))
    return ok(out)


def tool_sensors(args):
    return ok(fmt(run(["sensors"])))


def tool_kwin(args):
    return ok(fmt(run(["qdbus6", "org.kde.KWin", "/KWin", "supportInformation"])))


def tool_cmd(args):
    """Explicit, opt-in shell command execution (guarded by allowlist prefixes)."""
    command = args.get("command", "")
    if not command:
        return ok("Kein 'command' angegeben.")
    allow = (
        "systemctl ",
        "journalctl ",
        "df ",
        "free",
        "uptime",
        "sensors",
        "nvidia-smi ",
        "pacman -Q",
        "lsblk",
        "uname",
        "cat /etc/",
        "qdbus6 ",
        "kreadconfig6 ",
        "git ",
    )
    if not command.startswith(allow):
        return ok(
            "Befehl nicht erlaubt. Erlaubte Präfixe:\n" + "\n".join(f"- {a}" for a in allow)
        )
    res = run(["bash", "-lc", command], timeout=30)
    return ok(fmt(res))


def tool_notify(args):
    """Send a desktop notification (action tool)."""
    summary = args.get("summary", "opencode")
    body = args.get("body", "")
    urgency = args.get("urgency", "normal")
    if urgency not in ("low", "normal", "critical"):
        urgency = "normal"
    cmd = ["notify-send", "-a", "opencode", "-u", urgency, summary, body]
    return ok(fmt(run(cmd)))


def tool_restart_unit(args):
    """Restart a systemd unit (action tool). Only units that are safe/common
    are permitted; never dbus/systemd-logind/display-manager."""
    unit = args.get("unit", "")
    scope = args.get("scope", "user")
    if not unit:
        return ok("Kein 'unit' angegeben.")
    # allowlist by simple suffix/pattern; refuse core services
    forbidden = ("dbus", "dbus-broker", "systemd", "display-manager", "plasmalogin",
                 "sddm", "gdm", "lightdm", "graphical.target")
    low = unit.lower()
    if any(f in low for f in forbidden):
        return ok(f"Unit '{unit}' ist gesperrt (kritischer Dienst).")
    if not (low.endswith(".service") or low.endswith(".timer") or low.endswith(".socket") or low.endswith(".path")):
        return ok("Nur Unit-Namen mit Endung .service/.timer/.socket/.path erlaubt.")
    cmd = ["systemctl"]
    if scope == "user":
        cmd.append("--user")
    cmd += ["restart", unit]
    return ok(fmt(run(cmd)))


def tool_media(args):
    """Control media playback via the MPRIS D-Bus interface (action tool)."""
    action = args.get("action", "")
    players = {
        "playpause": "PlayPause",
        "next": "Next",
        "previous": "Previous",
        "stop": "Stop",
        "play": "Play",
        "pause": "Pause",
    }
    if action not in players:
        return ok(f"Ungültige Aktion. Erlaubt: {sorted(players)}")
    # talk to the first available player
    services = run(["bash", "-lc",
        "qdbus6 | grep -oE 'org\\.mpris\\.MediaPlayer\\.[A-Za-z0-9._]+' | head -1"]).get("stdout", "")
    if not services:
        return ok("Kein MPRIS-Player aktiv.")
    svc = services.splitlines()[0].strip()
    res = run(["qdbus6", svc, "/org/mpris/MediaPlayer2",
               "org.mpris.MediaPlayer2.Player." + players[action]])
    return ok(fmt(res))


def tool_wallpaper(args):
    """Set the Plasma wallpaper (action tool)."""
    path = args.get("path", "")
    if not path or not (path.startswith("/") or path.startswith("file://")):
        return ok("Bitte absoluten Pfad (oder file://-URL) angeben.")
    url = path if path.startswith("file://") else "file://" + path
    script = (
        "var ds = desktops();"
        "for (var i=0;i<ds.length;i++){"
        f"ds[i].wallpaperPlugin='org.kde.image';"
        f"ds[i].currentConfigGroup=['Wallpaper','org.kde.image','General'];"
        f"ds[i].writeConfig('Image','{url}');"
        "}"
    )
    res = run(["qdbus6", "org.kde.plasmashell", "/PlasmaShell",
               "org.kde.PlasmaShell.evaluateScript", script])
    return ok(fmt(res) or "Wallpaper gesetzt.")


def tool_screenshot(args):
    """Take a screenshot to a file (action tool)."""
    path = args.get("path", "/tmp/opencode-screenshot.png")
    if not path.startswith("/"):
        return ok("Bitte absoluten Zielpfad angeben.")
    res = run(["spectacle", "-b", "-n", "-o", path], timeout=30)
    if res["rc"] == 0:
        return ok(f"Screenshot gespeichert: {path}")
    return ok(fmt(res))


def tool_window(args):
    """List or activate windows via KWin (action tool)."""
    action = args.get("action", "list")
    if action == "list":
        return tool_kwin({"dummy": ""})  # not ideal; fall through below
    return ok("Nur action=list unterstützt.")


TOOLS = {
    "systemctl": {
        "fn": tool_systemctl,
        "desc": "systemctl: status/is-active/list von Units (system oder user scope).",
        "schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": sorted(ALLOWED_SYSTEMCTL_ACTIONS)},
                "unit": {"type": "string"},
                "scope": {"type": "string", "enum": ["system", "user"]},
            },
        },
    },
    "journal": {
        "fn": tool_journal,
        "desc": "journalctl: letzte Logzeilen, optional pro Unit / Priorität.",
        "schema": {
            "type": "object",
            "properties": {
                "unit": {"type": "string"},
                "lines": {"type": "integer", "minimum": 1, "maximum": 500},
                "scope": {"type": "string", "enum": ["system", "user"]},
                "priority": {"type": "string", "description": "z.B. err, warning, info"},
            },
        },
    },
    "pacman": {
        "fn": tool_pacman,
        "desc": "pacman: Suche/Info/installierte Pakete (read-only Aktionen).",
        "schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": sorted(ALLOWED_PACMAN_ACTIONS)},
                "query": {"type": "string"},
            },
        },
    },
    "disk": {
        "fn": tool_disk,
        "desc": "df -h für einen Pfad (Standard /).",
        "schema": {"type": "object", "properties": {"path": {"type": "string"}}},
    },
    "gpu": {
        "fn": tool_gpu,
        "desc": "nvidia-smi: GPU-Auslastung, VRAM, Leistung, Temperatur.",
        "schema": {"type": "object", "properties": {}},
    },
    "memory": {
        "fn": tool_memory,
        "desc": "RAM/swap (free) + uptime/load.",
        "schema": {"type": "object", "properties": {}},
    },
    "sensors": {
        "fn": tool_sensors,
        "desc": "lm_sensors Temperaturen/Lüfter.",
        "schema": {"type": "object", "properties": {}},
    },
    "kwin": {
        "fn": tool_kwin,
        "desc": "KWin Compositor-Info (Backend, Effekte, Screens).",
        "schema": {"type": "object", "properties": {}},
    },
    "cmd": {
        "fn": tool_cmd,
        "desc": "Eingeschränkter Shell-Befehl mit Präfix-Allowlist (read-only Fokus).",
        "schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
}

# ---- action tools (opt-in) -------------------------------------------------
# Registered only when LUMEN_MCP_ACTIONS=1. These perform state changes.
ACTION_TOOLS = {
    "notify": {
        "fn": tool_notify,
        "desc": "Desktop-Benachrichtigung senden (Aktion).",
        "schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "body": {"type": "string"},
                "urgency": {"type": "string", "enum": ["low", "normal", "critical"]},
            },
            "required": ["summary"],
        },
    },
    "restart_unit": {
        "fn": tool_restart_unit,
        "desc": "systemd-Unit neu starten (Aktion; kritische Dienste gesperrt).",
        "schema": {
            "type": "object",
            "properties": {
                "unit": {"type": "string"},
                "scope": {"type": "string", "enum": ["system", "user"]},
            },
            "required": ["unit"],
        },
    },
    "media": {
        "fn": tool_media,
        "desc": "Medienwiedergabe steuern (playpause/next/previous/stop/play/pause).",
        "schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["playpause", "next", "previous", "stop", "play", "pause"]}
            },
            "required": ["action"],
        },
    },
    "wallpaper": {
        "fn": tool_wallpaper,
        "desc": "Plasma-Hintergrundbild setzen (Aktion).",
        "schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    "screenshot": {
        "fn": tool_screenshot,
        "desc": "Screenshot in eine Datei speichern (Aktion).",
        "schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
        },
    },
}

if ACTIONS_ENABLED:
    TOOLS.update(ACTION_TOOLS)


# ---- JSON-RPC / MCP plumbing ----------------------------------------------


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def result(req_id, res):
    send({"jsonrpc": "2.0", "id": req_id, "result": res})


def error(req_id, code, message):
    send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def handle(req):
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        result(
            rid,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
    elif method == "notifications/initialized":
        pass  # notification, no reply
    elif method == "ping":
        result(rid, {})
    elif method == "tools/list":
        result(
            rid,
            {
                "tools": [
                    {
                        "name": name,
                        "description": t["desc"],
                        "inputSchema": t["schema"],
                    }
                    for name, t in TOOLS.items()
                ]
            },
        )
    elif method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        tool = TOOLS.get(name)
        if not tool:
            error(rid, -32602, f"Unbekanntes Tool: {name}")
            return
        try:
            content = tool["fn"](args)
            result(rid, {"content": content, "isError": False})
        except Exception as exc:  # noqa: BLE001
            result(rid, {"content": ok(f"Fehler: {exc}"), "isError": True})
    elif method in ("resources/list", "prompts/list"):
        result(rid, {"resources": [], "prompts": []} if method.startswith("resources") else {"prompts": []})
    else:
        if rid is not None:
            error(rid, -32601, f"Methode nicht unterstützt: {method}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        handle(req)


if __name__ == "__main__":
    main()
