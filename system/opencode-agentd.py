#!/usr/bin/env python3
"""
opencode-agentd — system-wide helper daemon for opencode Agent.

Exposes a small D-Bus service on the **system bus** so any local client can
query read-mostly system state without needing root itself:

    service:   org.opencode.Agent
    path:      /org/opencode/Agent
    interface: org.opencode.Agent

Methods:
    GetSummary() -> a{sv}   CPU load, RAM, root disk, GPU, failed units
    GetFindings() -> s      last watchdog findings (markdown) or ""
    RefreshWatch() -> b     trigger the watchdog now

This is a normal, visible, uninstallable system service. It performs only
read-only introspection; it does not hide itself or bypass authorisation.
"""

import os
import shutil
import subprocess
import sys

try:
    import dbus
    import dbus.service
    import dbus.mainloop.glib
    from gi.repository import GLib
except ImportError:
    sys.stderr.write("opencode-agentd: python-dbus / pygobject missing\n")
    sys.exit(1)

BUS_NAME = "org.opencode.Agent"
OBJ_PATH = "/org/opencode/Agent"
IFACE = "org.opencode.Agent"
FINDINGS = "/var/lib/opencode-agent/findings.md"
WATCH_BIN = "/usr/bin/opencode-agent-watch"


def sh(cmd, timeout=15):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.stdout.strip()
    except Exception:
        return ""


def summary():
    out = {}

    # CPU load (1 min) and number of cores
    try:
        load1 = float(open("/proc/loadavg").read().split()[0])
        cores = os.cpu_count() or 1
        out["cpu_load"] = load1
        out["cpu_percent"] = round(min(load1 / cores, 1.0) * 100, 1)
    except Exception:
        out["cpu_percent"] = -1.0

    # memory
    try:
        mem = {}
        for line in open("/proc/meminfo"):
            k, v = line.split(":", 1)
            mem[k] = int(v.strip().split()[0])
        total = mem.get("MemTotal", 0)
        avail = mem.get("MemAvailable", 0)
        out["mem_total_mb"] = round(total / 1024)
        out["mem_used_mb"] = round((total - avail) / 1024)
        out["mem_percent"] = round((total - avail) / total * 100, 1) if total else -1.0
    except Exception:
        out["mem_percent"] = -1.0

    # root disk
    try:
        du = shutil.disk_usage("/")
        out["disk_total_gb"] = round(du.total / 1e9)
        out["disk_free_gb"] = round(du.free / 1e9)
        out["disk_percent"] = round(du.used / du.total * 100, 1)
    except Exception:
        out["disk_percent"] = -1.0

    # GPU (nvidia)
    if shutil.which("nvidia-smi"):
        line = sh(["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu,memory.used",
                   "--format=csv,noheader,nounits"])
        if line:
            parts = [p.strip() for p in line.split(",")]
            try:
                out["gpu_percent"] = float(parts[0])
                out["gpu_temp"] = float(parts[1])
                out["gpu_mem_used_mb"] = float(parts[2])
            except Exception:
                pass

    # failed system units
    failed = sh(["systemctl", "--failed", "--no-legend", "--plain"]).splitlines()
    out["failed_units"] = len([l for l in failed if l.strip()])

    return out


class AgentService(dbus.service.Object):
    def __init__(self):
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SystemBus()
        name = dbus.service.BusName(BUS_NAME, bus)
        super().__init__(name, OBJ_PATH)

    @dbus.service.method(IFACE, out_signature="a{sv}")
    def GetSummary(self):
        return {k: v for k, v in summary().items()}

    @dbus.service.method(IFACE, out_signature="s")
    def GetFindings(self):
        try:
            with open(FINDINGS) as f:
                return f.read()
        except FileNotFoundError:
            return ""

    @dbus.service.method(IFACE, out_signature="b")
    def RefreshWatch(self):
        if os.path.exists(WATCH_BIN):
            subprocess.Popen([WATCH_BIN])
            return True
        return False


def main():
    AgentService()
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
