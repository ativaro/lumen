#!/usr/bin/env python3
# Lumen native desktop KRunner entry point.

import os
import subprocess

import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

DBusGMainLoop(set_as_default=True)

OBJPATH = "/runner"
IFACE = "org.kde.krunner1"
BUSNAME = "org.lumen.runner"

WORKDIR = os.environ.get("LUMEN_WORKDIR", os.path.expanduser("~/Documents/work"))

TRIGGERS = ("lumen ", "ai ", "oc ", "opencode ", "? ")


def build_command(prompt):
    app = os.path.join(os.path.dirname(os.path.realpath(__file__)), "lumen-agent-app")
    return [app, "--directory=" + WORKDIR, "--prompt=" + prompt]


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
                "lumen",
                100,  # QueryType (custom/free)
                1.0,  # relevance
                {"subtext": "Mit Lumen besprechen", "category": "Lumen"},
            )
        ]

    @dbus.service.method(IFACE, out_signature="a(sss)")
    def Actions(self):
        return []

    @dbus.service.method(IFACE, in_signature="ss")
    def Run(self, matchId, actionId):
        subprocess.Popen(build_command(matchId))


if __name__ == '__main__':
    runner = Runner()
    GLib.MainLoop().run()
