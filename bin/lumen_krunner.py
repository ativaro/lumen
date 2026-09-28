#!/usr/bin/env python3
# opencode KRunner DBus runner.
# Type "ai <question>" or "oc <question>" in KRunner to open a terminal
# running opencode with that prompt.
#
# Overridable via environment: LUMEN_OPENCODE_BIN, LUMEN_TERM, LUMEN_WORKDIR

import os
import shutil
import subprocess

import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

DBusGMainLoop(set_as_default=True)

OBJPATH = "/runner"
IFACE = "org.kde.krunner1"
BUSNAME = "org.lumen.runner"

LUMEN_OPENCODE_BIN = os.environ.get(
    "LUMEN_OPENCODE_BIN", shutil.which("opencode") or os.path.expanduser("~/.opencode/bin/opencode")
)
TERM = os.environ.get(
    "LUMEN_TERM", shutil.which("alacritty") or shutil.which("konsole") or "alacritty"
)
WORKDIR = os.environ.get("LUMEN_WORKDIR", os.path.expanduser("~/Documents/work"))

TRIGGERS = ("ai ", "oc ", "opencode ", "? ")


def build_command(prompt):
    shellcmd = (
        f'"$LUMEN_OPENCODE_BIN" run --continue "$LUMEN_PROMPT"; '
        'printf "\\n--- Fertig. Enter zum Schließen. ---\\n"; read -r _'
    )
    base = os.path.basename(TERM)
    if base == "alacritty":
        return [TERM, "--working-directory", WORKDIR, "-T", "Lumen: krunner", "-e", "bash", "-lc", shellcmd]
    if base == "konsole":
        return [TERM, "--workdir", WORKDIR, "-p", "tabtitle=Lumen: krunner", "-e", "bash", "-lc", shellcmd]
    return [TERM, "-e", "bash", "-lc", f"cd '{WORKDIR}' && {shellcmd}"]


class Runner(dbus.service.Object):
    def __init__(self):
        dbus.service.Object.__init__(
            self, dbus.service.BusName(BUSNAME, dbus.SessionBus()), OBJPATH
        )

    @dbus.service.method(IFACE, in_signature="s", out_signature="a(sssida{sv})")
    def Match(self, query):
        q = query.strip()
        low = q.lower()
        prefix = next((p for p in TRIGGERS if low.startswith(p)), None)
        if prefix is None:
            return []
        prompt = q[len(prefix):].strip()
        if not prompt:
            return []
        return [
            (
                prompt,
                f"Lumen: {prompt}",
                "opencode",
                100,  # QueryType (custom/free)
                1.0,  # relevance
                {"subtext": "Ask opencode in a terminal", "category": "opencode"},
            )
        ]

    @dbus.service.method(IFACE, out_signature="a(sss)")
    def Actions(self):
        return []

    @dbus.service.method(IFACE, in_signature="ss")
    def Run(self, matchId, actionId):
        env = dict(os.environ)
        env["LUMEN_PROMPT"] = matchId
        env["LUMEN_OPENCODE_BIN"] = LUMEN_OPENCODE_BIN
        subprocess.Popen(build_command(matchId), env=env)


runner = Runner()
GLib.MainLoop().run()
