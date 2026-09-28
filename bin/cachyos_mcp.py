#!/usr/bin/env python3
"""
cachyos-mcp — a stdlib-only MCP (Model Context Protocol) server exposing
read-mostly system introspection tools for CachyOS / KDE Plasma.

Transport: JSON-RPC 2.0 over stdio, newline-delimited (MCP stdio transport).
No third-party dependencies.

Run:  cachyos_mcp.py
Wire into opencode via ~/.config/opencode/opencode.jsonc -> mcp.cachyos
"""

import json
import os
import shlex
import subprocess
import sys

SERVER_NAME = "cachyos-mcp"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"

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
