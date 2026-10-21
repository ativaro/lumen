#!/usr/bin/env python3
"""Lumen's outbound-only desktop connector. Uses stdlib; restic is needed only for backups."""

from contextlib import closing
import argparse
import fcntl
import getpass
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import sqlite3
import socket
import signal
from ipaddress import IPv4Address, IPv4Interface
import ssl
import subprocess
import sys
import time
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, urlencode
from uuid import UUID

ROOT = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "lumen-server"
CONFIG = ROOT / "connection.json"


def save_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    with os.fdopen(fd, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def read_config():
    config = json.loads(CONFIG.read_text())
    url = urlsplit(config["server"])
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.path
        or url.query
        or url.fragment
    ):
        raise ValueError("Nur eine reine HTTPS-Serveradresse ist zulässig.")
    return config


def disconnect(config):
    """Keep the old backup coordinates; detach locally only after the server confirms."""
    with (ROOT / "pairing.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if CONFIG.exists() and read_config() != config:
            raise ValueError("Die Serververbindung wurde geändert. Bitte erneut öffnen.")
        result = request(config, "/bridge/disconnect", {})
        if result.get("ok") is not True or result.get("device_id") != config["device_id"]:
            raise ValueError("Der Server hat die Trennung nicht bestätigt.")
        save_private(ROOT / ("disconnected-" + str(UUID(config["device_id"])) + ".json"), json.dumps(config))
        if CONFIG.exists():
            if read_config() != config:
                raise ValueError("Die Serververbindung wurde geändert. Bitte erneut öffnen.")
            CONFIG.unlink()
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def tls_context(config):
    context = ssl.create_default_context(cafile=config.get("ca_file"))
    # Reuse only Lumen CAs the user explicitly trusted, including on this same host.
    if not config.get("ca_file") and shutil.which("certutil"):
        legacy = Path.home() / ".pki/nssdb"
        database = legacy if legacy.exists() else Path.home() / ".local/share/pki/nssdb"
        if (database / "cert9.db").exists():
            command = ["certutil", "-d", "sql:" + str(database), "-L"]
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            for name in re.findall(r"^(Lumen Server Local CA [0-9a-f]{12})\s+C,,\s*$", result.stdout, re.M):
                cert = subprocess.run(command + ["-n", name, "-a"], capture_output=True, text=True, timeout=5)
                if cert.returncode == 0:
                    context.load_verify_locations(cadata=cert.stdout)
    return context


def request(config, path, body=None, *, timeout=15):
    headers = {"Authorization": "Bearer " + config["token"]} if config.get("token") else {}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        config["server"] + path, headers=headers, data=json.dumps(body).encode() if body is not None else None
    )
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=tls_context(config)), NoRedirect()
    )
    with opener.open(req, timeout=timeout) as r:
        data = r.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            raise ValueError("Serverantwort ist zu groß.")
        return json.loads(data)


def parse_pairing_uri(uri):
    if len(uri) > 2048:
        raise ValueError("Ungültige Verbindungsanfrage.")
    link = urlsplit(uri)
    params = parse_qs(link.query, strict_parsing=True)
    if (
        link.scheme != "lumen-server"
        or link.netloc != "pair"
        or link.path
        or link.fragment
        or set(params) != {"server", "id", "code"}
        or any(len(v) != 1 for v in params.values())
    ):
        raise ValueError("Ungültige Verbindungsanfrage.")
    server = params["server"][0]
    origin = urlsplit(server)
    if (
        origin.scheme != "https"
        or not origin.hostname
        or origin.username
        or origin.password
        or origin.path
        or origin.query
        or origin.fragment
        or any(c.isspace() for c in server)
    ):
        raise ValueError("Die Serveradresse muss eine reine HTTPS-Adresse sein.")
    origin.port  # Validate the port before opening any network connection.
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", params["code"][0]):
        raise ValueError("Ungültiger Anfrageschlüssel.")
    return {"server": server}, {"id": str(UUID(params["id"][0])), "code": params["code"][0]}


def pairing_request(uri, action, capabilities=None):
    if action not in ("preview", "approve", "decline"):
        raise ValueError("Ungültige Aktion.")
    config, body = parse_pairing_uri(uri)
    if action == "approve" and capabilities is not None:
        body["capabilities"] = capabilities
    result = request(config, "/bridge/pairings/" + action, body)
    if not isinstance(result, dict):
        raise ValueError("Ungültige Serverantwort.")
    if action != "decline":
        if result.get("protocol", 1) != 1:
            raise ValueError("Diese Serverversion benötigt ein neueres Lumen Desktop.")
        if result.get("server") != config["server"]:
            raise ValueError("Die Serveradresse der Antwort stimmt nicht mit der Anfrage überein.")
        fields = ("account", "email", "name") + (
            ("device_id", "token", "backup_token") if action == "approve" else ()
        )
        if not all(isinstance(result.get(k), str) and 0 < len(result[k]) <= 1000 for k in fields):
            raise ValueError("Unvollständige Serverantwort.")
    return result


def device_inventory():
    """Report fixed, non-secret platform facts; never run downloaded commands."""
    root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "lumen"
    revision = "unknown"
    for path in (root / "install.json", Path("/usr/share/lumen/install.json")):
        try:
            candidate = json.loads(path.read_text()).get("revision", "")
            if re.fullmatch(r"[0-9a-f]{7,40}", candidate):
                revision = candidate
                break
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    try:
        system = platform.freedesktop_os_release().get("PRETTY_NAME", platform.system())
    except OSError:
        system = platform.system()
    return dict(
        connector="1.5.1",
        os=system[:120],
        architecture=platform.machine()[:40],
        lumen=revision,
        supported=["system_snapshot", "wake", "services", "update"],
    )


def system_access_allowed(config):
    # The local decision is bound to this connection, not merely to a server flag.
    try:
        local = read_config()
    except (OSError, ValueError, KeyError):
        return False
    if not all(local.get(key) == config.get(key) for key in ("server", "device_id", "token")):
        return False
    scope = dict(server=config.get("server"), device_id=config.get("device_id"))
    return local.get("system_access") in (
        {**scope, "version": 1},
        {**scope, "version": 2, "enabled": True},
    )


def initialize_system_access(config):
    """Upgrade legacy connections once; never overwrite a saved opt-out."""
    with (CONFIG.parent / "system-access.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        local = read_config()
        if not all(local.get(key) == config.get(key) for key in ("server", "device_id", "token")):
            raise ValueError("Die Serververbindung wurde geändert.")
        if "system_access" in local:
            return
        # In 1.3, disabling a granted pairing removed this marker. Preserve that choice.
        enabled = "system_read" not in local.get("capabilities", [])
        if enabled:
            rights = request(local, "/bridge/me").get("capabilities", [])
            if "desktop" not in rights:
                return
            if "system_read" not in rights:
                request(local, "/bridge/system-access", {"enabled": True})
        local["system_access"] = dict(
            server=local["server"], device_id=local["device_id"], version=2, enabled=enabled
        )
        save_private(CONFIG, json.dumps(local))


def set_system_access(enabled):
    with (CONFIG.parent / "system-access.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        config = read_config()
        if enabled:
            request(config, "/bridge/system-access", {"enabled": True})
        # Explicit opt-out remains effective locally even when the server is unreachable.
        config["system_access"] = dict(
            server=config["server"], device_id=config["device_id"], version=2, enabled=enabled
        )
        save_private(CONFIG, json.dumps(config))
        if not enabled:
            request(config, "/bridge/system-access", {"enabled": False})
    report_inventory(config)


def system_snapshot():
    from datetime import datetime, timezone

    files = Path(os.environ.get("LUMEN_DESKTOP_FILES", Path.home() / ".local/share/lumen/files"))
    if Path(__file__).with_name("system_data.py").is_file():
        files = Path(__file__).parent
    sys.path.insert(0, str(files))
    from system_data import Sampler

    sampler = Sampler()
    sampler.sample()
    time.sleep(0.25)
    value = sampler.sample()
    memory, disk, network = value.get("memory") or {}, value.get("disk") or {}, value.get("network") or {}
    return dict(
        measured=datetime.fromtimestamp(value["measured"], timezone.utc).isoformat(),
        cpu=value["cpu"],
        cores=value["cores"],
        memory_total=memory.get("total"),
        memory_used=memory.get("used"),
        disk_total=disk.get("total"),
        disk_used=disk.get("used"),
        receive=network.get("receive"),
        send=network.get("send"),
    )


def snapshot_request(config, identity):
    if not system_access_allowed(config):
        raise ValueError("Systemabfragen sind in der Serververbindung deaktiviert.")
    me = request(config, "/bridge/me")
    if not {"desktop", "system_read"} <= set(me.get("capabilities", [])):
        raise ValueError("Systemabfragen sind nicht freigegeben.")
    action = request(config, "/bridge/actions/" + identity)
    if action.get("app") != "system_snapshot" or action.get("state") != "pending":
        raise ValueError("Ungültige Systemabfrage.")
    claimed = request(
        config, "/bridge/actions/" + identity, dict(state="claimed", revision=action["revision"])
    )
    if claimed.get("replayed"):
        return
    result = system_snapshot()
    # Recheck both local and remote consent immediately before disclosure.
    if not system_access_allowed(config):
        raise ValueError("Systemfreigabe wurde widerrufen.")
    me = request(config, "/bridge/me")
    if not {"desktop", "system_read"} <= set(me.get("capabilities", [])):
        raise ValueError("Systemfreigabe wurde widerrufen.")
    request(
        config,
        "/bridge/actions/" + identity,
        dict(state="completed", revision=claimed["revision"], result=result),
    )


def report_inventory(config):
    initialize_system_access(config)
    try:
        request(
            config,
            "/bridge/inventory",
            {**device_inventory(), "status_access": system_access_allowed(config)},
        )
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise


def connection_scope(config):
    """Bind private mirrors to credentials as well as origin; never persist the token."""
    if not isinstance(config.get("token"), str) or not config["token"]:
        raise ValueError("Geräteschlüssel fehlt.")
    return hashlib.sha256(json.dumps(
        [config["server"], config.get("device_id", ""), config["token"]]
    ).encode()).hexdigest()


def synchronize(config):
    scope = connection_scope(config)
    if connection_scope(read_config()) != scope:
        raise ValueError("Die Serververbindung wurde geändert.")
    try:
        data = request(config, "/bridge/sync")
        cursor = data.get("memory_cursor")
        version = data.get("memory_version")
        while cursor:
            params = {"after": cursor}
            if version is not None:
                params["memory_version"] = version
            page = request(config, "/bridge/sync?" + urlencode(params))
            if page.get("memory_version") != version:
                raise ValueError("Gedächtnis während des Abgleichs geändert.")
            data["memories"].extend(page["memories"])
            cursor = page.get("memory_cursor")
    except urllib.error.HTTPError as error:
        if error.code in (401, 403) and CONFIG.exists() and connection_scope(read_config()) == scope:
            if (ROOT / "memory.sqlite3").exists():
                with closing(sqlite3.connect(ROOT / "memory.sqlite3")) as db, db:
                    db.execute("BEGIN IMMEDIATE")
                    owner = db.execute("SELECT 1 FROM sqlite_master WHERE name='memory_owner'").fetchone()
                    if not owner or db.execute("SELECT scope FROM memory_owner").fetchone() == (scope,):
                        for table in ("memories", "handoffs"):
                            if db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
                                db.execute("DELETE FROM " + table)
            if CONFIG.exists() and json.loads(CONFIG.read_text()).get("token") == config.get("token"):
                # Preserve the old backup coordinates/key; a revoked connection can be paired again in the UI.
                save_private(
                    ROOT / ("disconnected-" + str(UUID(config["device_id"])) + ".json"), json.dumps(config)
                )
                CONFIG.unlink()
        raise
    unified_notifications = False
    if ROOT == Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "lumen-server":
        candidates = [Path(__file__).parent, Path(os.environ.get('LUMEN_DESKTOP_FILES',Path.home()/'.local/share/lumen/files')), Path('/usr/share/lumen/files')]
        files = next((folder for folder in candidates if (folder/'notification_sync.py').is_file()), None)
        if files is not None:
            if str(files) not in sys.path: sys.path.insert(0,str(files))
            from notification_sync import synchronize as synchronize_notifications
            unified_notifications = synchronize_notifications(config,data,request)
    notify = False
    with closing(sqlite3.connect(ROOT / "memory.sqlite3")) as db, db:
        db.execute("BEGIN IMMEDIATE")
        if connection_scope(read_config()) != scope:
            raise ValueError("Die Serververbindung wurde während des Abgleichs geändert.")
        db.execute("CREATE TABLE IF NOT EXISTS memory_owner(scope TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS sync_state(source TEXT PRIMARY KEY,version TEXT)")
        previous_owner = db.execute("SELECT scope FROM memory_owner").fetchone()
        if previous_owner != (scope,):
            db.execute("DELETE FROM sync_state")
            # A new account must not inherit acknowledgement IDs from the old one.
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='notifications'").fetchone():
                db.execute("DELETE FROM notifications")
        db.execute("DELETE FROM memory_owner")
        db.execute("INSERT INTO memory_owner VALUES (?)", (scope,))
        if version:
            incoming = tuple(int(x) for x in version.split(":"))
            if len(incoming) != 2:
                raise ValueError("Ungültige Abgleich-Version.")
            previous = db.execute(
                "SELECT version FROM sync_state WHERE source=?", (scope,)
            ).fetchone()
            if previous and any(a < b for a, b in zip(incoming, map(int, previous[0].split(":")))):
                raise ValueError("Veralteter Abgleich wurde verworfen.")
            db.execute("INSERT OR REPLACE INTO sync_state VALUES (?,?)", (scope, version))
        db.execute(
            "CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,title TEXT,body TEXT,revision INT,source TEXT)"
        )
        db.execute("CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY,title TEXT,task_id TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS handoffs(id TEXT PRIMARY KEY,payload TEXT)")
        db.execute("DELETE FROM memories")
        db.executemany(
            "INSERT INTO memories VALUES (?,?,?,?,?)",
            [(m["id"], m["title"], m["body"], m["revision"], config["server"]) for m in data["memories"]],
        )
        db.execute("DELETE FROM handoffs")
        db.executemany("INSERT INTO handoffs VALUES (?,?)", [(t["id"], json.dumps(t)) for t in data["tasks"]])
        for n in data["notifications"]:
            inserted = db.execute(
                "INSERT OR IGNORE INTO notifications VALUES (?,?,?)", (n["id"], n["title"], n["task_id"])
            ).rowcount
            notify = notify or bool(inserted)
    if notify and not unified_notifications and shutil.which("notify-send"):
        # The inbox is committed before the best-effort OS notification and server acknowledgement.
        try:
            subprocess.run(
                ["notify-send", "Lumen Server", "Ein neuer Bericht ist bereit."],
                check=False,
                timeout=3,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    (ROOT / "memory.sqlite3").chmod(0o600)
    if data["notifications"]:
        request(config, "/bridge/ack", {"notification_id": max(n["id"] for n in data["notifications"])})
    if version and "memory" in data.get("capabilities", []):
        request(config, "/bridge/sync-complete", {"version": version})
    desktop_requests(config, data["tasks"])
    return {"memories": len(data["memories"]), "pending_desktop_tasks": len(data["tasks"])}


def shared_memories():
    """Read the confirmed server mirror without copying it into the personal notebook."""
    try:
        config = read_config()
        scope = connection_scope(config)
        path = ROOT / "memory.sqlite3"
        if not path.is_file():
            return []
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("BEGIN")
            if db.execute("SELECT scope FROM memory_owner").fetchone() != (scope,):
                return []
            db.row_factory = sqlite3.Row
            rows = [
                dict(row)
                for row in db.execute(
                    "SELECT id,title,body,revision,source FROM memories WHERE source=? ORDER BY id LIMIT 500",
                    (config["server"],),
                )
            ]
        return rows if connection_scope(read_config()) == scope else []
    except (OSError, ValueError, KeyError, sqlite3.Error):
        return []


def memory_stamp():
    rows = shared_memories()
    try:scope=connection_scope(read_config())
    except (OSError,ValueError,KeyError):scope=''
    return hashlib.sha256(json.dumps([scope,rows], sort_keys=True).encode()).hexdigest() if scope or rows else ""


def receive_artifact(config, action, *, job=None):
    """Claim once and download one authenticated immutable object into a private cache."""
    import hashlib

    def check():
        if job is not None:
            job.check()

    extensions = {
        "text/plain": ".txt",
        "text/markdown": ".md",
        "application/pdf": ".pdf",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    if action.get("mime") not in extensions or not 0 <= action.get("size", -1) <= 64 * 1024**2:
        raise ValueError("Dateityp oder Größe ist nicht freigegeben.")
    identity = str(UUID(action["id"]))
    file_id = str(UUID(action["file_id"]))
    action_revision = action["revision"]
    temporary = None
    fresh_claim = False
    try:
        check()
        claimed = request(
            config, "/bridge/actions/" + identity, dict(state="claimed", revision=action_revision)
        )
        replayed = claimed.get("replayed")
        if not replayed:
            revision = claimed["revision"]
            if type(revision) is not int or type(action_revision) is not int or revision != action_revision + 1:
                raise ValueError("Die Übernahme wurde nicht bestätigt.")
            fresh_claim = True
        check()
        if replayed:
            raise ValueError("Diese Anfrage wurde bereits übernommen. Bitte neu senden.")
        folder = ROOT / "received"
        folder.mkdir(mode=0o700, exist_ok=True)
        target = folder / (file_id + extensions[action["mime"]])
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=tls_context(config)), NoRedirect()
        )
        req = urllib.request.Request(
            config["server"] + "/bridge/artifacts/" + file_id,
            headers={"Authorization": "Bearer " + config["token"]},
        )
        digest = hashlib.sha256()
        count = 0
        check()
        fd, temporary = tempfile.mkstemp(dir=folder, prefix=".receive-")
        with os.fdopen(fd, "wb") as out:
            check()
            with opener.open(req, timeout=20) as response:
                check()
                while True:
                    check()
                    chunk = response.read(128 * 1024)
                    check()
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > action["size"]:
                        raise ValueError("Die Datei wurde verändert.")
                    digest.update(chunk)
                    check()
                    out.write(chunk)
                check()
                out.flush()
                check()
                os.fsync(out.fileno())
        check()
        if count != action["size"] or digest.hexdigest() != action["sha256"]:
            raise ValueError("Die Datei wurde verändert.")
        check()
        latest = request(config, "/bridge/actions/" + identity)
        check()
        if latest.get("state") != "claimed" or latest.get("revision") != revision:
            raise ValueError("Die Freigabe ist nicht mehr aktuell.")
        check()
        os.replace(temporary, target)
        temporary = None
        check()
        return dict(path=str(target), revision=revision, id=identity)
    except Exception:
        if fresh_claim:
            try:
                request(config, "/bridge/actions/" + identity, dict(state="failed", revision=revision))
            except (OSError, ValueError):
                pass
        raise
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def send_wake_packet(profile):
    """Fixed 102-byte packet, only to a verified directly attached LAN broadcast."""
    if (
        not isinstance(profile, dict)
        or not isinstance(profile.get("mac"), str)
        or not isinstance(profile.get("broadcast"), str)
    ):
        raise ValueError("Invalid wake profile")
    mac = profile["mac"]
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac):
        raise ValueError("Invalid wake MAC")
    raw = bytes.fromhex(mac.replace(":", ""))
    if not any(raw) or raw[0] & 1:
        raise ValueError("Invalid wake MAC")
    destination = IPv4Address(profile["broadcast"])
    interfaces = json.loads(
        subprocess.run(
            ["ip", "-j", "-4", "addr", "show", "up"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    )
    sources = set()
    for interface in interfaces:
        if "LOOPBACK" in interface.get("flags", []):
            continue
        for address in interface.get("addr_info", []):
            if address.get("family") != "inet" or address.get("broadcast") != str(destination):
                continue
            local = IPv4Interface(str(address["local"]) + "/" + str(address["prefixlen"]))
            if local.network.broadcast_address == destination and not local.ip.is_loopback:
                sources.add(str(local.ip))
    if len(sources) != 1:
        raise ValueError("Wake network is not uniquely attached to this relay")
    packet = b"\xff" * 6 + raw * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        sender.settimeout(3)
        sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sender.bind((sources.pop(), 0))
        if sender.sendto(packet, (str(destination), 9)) != len(packet):
            raise OSError("Incomplete wake packet")


def wake_request(config, identity):
    action = request(config, "/bridge/actions/" + identity)
    if action.get("app") != "wake" or action.get("state") != "pending":
        raise ValueError("Invalid wake request")
    claimed = request(
        config, "/bridge/actions/" + identity, dict(state="claimed", revision=action["revision"])
    )
    try:
        # Recheck current rights/config immediately before the irreversible send.
        latest = request(config, "/bridge/actions/" + identity)
        if latest.get("state") != "claimed" or latest.get("revision") != claimed["revision"]:
            raise ValueError("Wake request changed")
        send_wake_packet(latest["wake_profile"])
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        request(config, "/bridge/actions/" + identity, dict(state="failed", revision=claimed["revision"]))
        raise
    # A lost completion receipt must never replay the packet or claim success.
    request(config, "/bridge/actions/" + identity, dict(state="completed", revision=claimed["revision"]))


def check_services(report=None):
    services = ("lumen-server-connector.service", "lumen-watch.service", "lumen-jobs.service")
    checks = {}
    if report:
        report(checks, services[0])
    for index, service in enumerate(services):
        check = dict(state="unknown", load="unknown", expected="unknown")
        try:
            reply = subprocess.run(
                [
                    "systemctl",
                    "--user",
                    "show",
                    "--property=LoadState,ActiveState,UnitFileState,Type,Result",
                    service,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            values = dict(line.split("=", 1) for line in reply.stdout.splitlines() if "=" in line)
            if reply.returncode == 0 or values.get("LoadState") == "not-found":
                state, load = values.get("ActiveState"), values.get("LoadState")
                oneshot = values.get("Type") == "oneshot"
                if oneshot and values.get("Result") not in (None, "", "success"):
                    state = "failed"
                check = dict(
                    state=state
                    if state in ("active", "inactive", "failed", "activating", "deactivating")
                    else "unknown",
                    load=load if load in ("loaded", "not-found", "error") else "unknown",
                    expected="on-demand"
                    if oneshot and values.get("Result") == "success" and load == "loaded"
                    else "running"
                    if service == services[0] or values.get("UnitFileState") in ("enabled", "enabled-runtime")
                    else "optional"
                    if values.get("UnitFileState") in ("disabled", "masked", "masked-runtime")
                    else "unknown",
                )
        except (OSError, subprocess.SubprocessError):
            pass  # A failed read is reported as unknown, never as a healthy service.
        checks[service] = check
        if report:
            report(checks, services[index + 1] if index + 1 < len(services) else None)
    return dict(operation="services", services={name: value["state"] for name, value in checks.items()})


def management_result(data):
    operation = data.get("operation")
    if operation not in ("services", "restart-watch", "restart-jobs", "update-check", "update-apply"):
        raise ValueError("Unknown management operation")
    if operation == "services":
        return check_services()
    services = ("lumen-watch.service", "lumen-jobs.service", "lumen-server-connector.service")
    if operation.startswith("restart-"):
        service = {"restart-watch": services[0], "restart-jobs": services[1]}[operation]
        subprocess.run(
            ["systemctl", "--user", "restart", service], capture_output=True, timeout=30, check=True
        )
    if operation in ("services", "restart-watch", "restart-jobs"):
        states = {}
        for service in services:
            value = subprocess.run(
                ["systemctl", "--user", "show", "--property=ActiveState", "--value", service],
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
            states[service] = (
                value
                if value in ("active", "inactive", "failed", "activating", "deactivating")
                else "unknown"
            )
        return dict(operation=operation, services=states)
    data_root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    helper = Path(__file__).with_name("updater_data.py")
    if not helper.exists():
        helper = data_root / "lumen/files/updater_data.py"
    if not helper.is_file():
        raise ValueError("Updater unavailable")
    command = [sys.executable, str(helper), "check" if operation == "update-check" else "apply"]
    if operation == "update-apply":
        revision = data.get("revision")
        if not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise ValueError("Missing checked revision")
        command += ["--revision", revision, "--components", "lumen"]
    # Reuse the updater's lock, revision check and installation paths. No OS updates.
    with tempfile.TemporaryFile() as output:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            code = proc.wait(timeout=1200)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise
        if code:
            raise ValueError("Update operation did not complete")
        output.seek(0)
        raw = output.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("Update result too large")
    version = data.get("revision")
    if operation == "update-check":
        for line in raw.splitlines():
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict) and isinstance(value.get("plan"), dict):
                version = value["plan"].get("revision")
    if not isinstance(version, str) or not re.fullmatch(r"[a-f0-9]{40}", version):
        raise ValueError("Missing update receipt")
    return dict(operation=operation, version=version)


def management_access(config, action):
    rights = set(request(config, "/bridge/me").get("capabilities", []))
    if "manage" not in rights and not (
        {"desktop", "system_read"} <= rights
        and system_access_allowed(config)
        and action.get("management", {}).get("operation") in ("services", "update-check")
    ):
        raise ValueError("Verwaltungsaktion nicht freigegeben.")


def management_request(config, identity):
    action = request(config, "/bridge/actions/" + identity)
    if action.get("app") != "management" or action.get("state") != "pending":
        raise ValueError("Invalid management request")
    claimed = request(
        config, "/bridge/actions/" + identity, dict(state="claimed", revision=action["revision"])
    )
    try:
        latest = request(config, "/bridge/actions/" + identity)
        if latest.get("state") != "claimed" or latest.get("revision") != claimed["revision"]:
            raise ValueError("Management request changed")
        management_access(config, latest)
        if latest["management"]["operation"] == "services":

            def report(checks, current):
                management_access(config, latest)
                request(
                    config,
                    "/bridge/actions/" + identity + "/progress",
                    dict(revision=claimed["revision"], checks=checks, current=current),
                )

            result = check_services(report)
        else:
            result = management_result(latest["management"])
        management_access(config, latest)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        request(config, "/bridge/actions/" + identity, dict(state="failed", revision=claimed["revision"]))
        raise
    request(
        config,
        "/bridge/actions/" + identity,
        dict(state="completed", revision=claimed["revision"], result=result),
    )


def desktop_requests(config, tasks=()):
    try:
        requests = request(config, "/bridge/actions")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return
        raise
    with closing(sqlite3.connect(ROOT / "memory.sqlite3")) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS desktop_requests(id TEXT PRIMARY KEY)")
        pending = []
        for action in requests:
            identity = str(UUID(action["id"]))
            if db.execute("INSERT OR IGNORE INTO desktop_requests VALUES (?)", (identity,)).rowcount:
                pending.append(
                    (
                        "--management"
                        if action.get("app") == "management"
                        else "--wake"
                        if action.get("app") == "wake"
                        else "--snapshot"
                        if action.get("app") == "system_snapshot"
                        else "--launch"
                        if action.get("app")
                        else "--artifact",
                        identity,
                    )
                )
        for task in tasks:
            identity = str(UUID(task["id"]))
            key = identity + ":" + str(int(task["generation"]))
            if (
                task["kind"] == "assistant"
                and db.execute("INSERT OR IGNORE INTO desktop_requests VALUES (?)", (key,)).rowcount
            ):
                pending.append(("--handoff", identity))
    for option, identity in pending:
        if option == "--snapshot":
            # No GUI fallback: legacy connections require one explicit consent upgrade.
            try:
                snapshot_request(config, identity)
            except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                print("Systemabfrage nicht abgeschlossen; Freigabe und Verbindung prüfen.", file=sys.stderr)
            continue
        if option == "--management":
            subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--config-dir",
                    str(ROOT),
                    "manage-action",
                    identity,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            continue
        if option == "--wake":
            try:
                wake_request(config, identity)
            except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                print(
                    "Wake-on-LAN konnte nicht bestätigt werden; kein automatischer Wiederholungsversuch.",
                    file=sys.stderr,
                )
            continue
        # Record delivery before launching: a crash never silently repeats an opening.
        subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("lumen_connect_gui.py")), option, identity],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def restic(config, args):
    if not shutil.which("restic"):
        raise RuntimeError("Bitte restic installieren, um Sicherungen zu nutzen.")
    env = os.environ.copy()
    env.update(
        RESTIC_REPOSITORY="rest:" + config["server"] + "/backup/" + config["device_id"] + "/",
        RESTIC_PASSWORD_FILE=str(ROOT / "backup.key"),
        RESTIC_REST_USERNAME=config["device_id"],
        RESTIC_REST_PASSWORD=config["backup_token"],
    )
    command = ["restic"]
    if config.get("ca_file"):
        command += ["--cacert", config["ca_file"]]
    subprocess.run(command + args, env=env, check=True)


_DATA_PROCESS = None
_DATA_NEXT = 0


def sync_data():
    """One bounded pass and one status per area; retries run without open windows."""
    global _DATA_PROCESS, _DATA_NEXT
    if _DATA_PROCESS and _DATA_PROCESS.poll() is None: return
    if time.monotonic() < _DATA_NEXT: return
    _DATA_NEXT = time.monotonic() + 60
    helper = Path(__file__).with_name("sync_settings.py")
    if not helper.exists():
        helper = Path.home()/".local/share/lumen/files/sync_settings.py"
    if not helper.exists():
        sync_memory(); sync_drive(); sync_vault()
        return
    _DATA_PROCESS = subprocess.Popen([sys.executable, str(helper)], stdin=subprocess.PIPE,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _DATA_PROCESS.stdin.write(b'{"action":"sync"}')
        _DATA_PROCESS.stdin.close()
    except (BrokenPipeError, OSError): pass


def sync_vault():
    """Ciphertext-only, independently of Vault windows and unlock state."""
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    root = data / "lumen-vault-lab"
    if not (root / "sync-auto.json").exists():
        return
    helper = Path(__file__).with_name("vault_sync.py")
    if not helper.exists():
        helper = data / "lumen/files/vault_sync.py"
    if not helper.exists():
        return
    try:
        result = subprocess.run(
            [sys.executable, str(helper)],
            input=json.dumps({"op": "auto-poll", "root": str(root)}),
            text=True,
            capture_output=True,
            timeout=45,
        )
        if result.returncode:
            print(
                "Tresorabgleich nicht abgeschlossen; Status im nativen Serverabgleich prüfen.",
                file=sys.stderr,
            )
    except (OSError, subprocess.TimeoutExpired):
        print("Tresorabgleich unterbrochen; nächster Durchlauf prüft den Ausgang.", file=sys.stderr)


_NOTES_PROCESSES = {}
_DRIVE_PROCESS = None
_DRIVE_NEXT = 0


def sync_drive():
    global _DRIVE_PROCESS, _DRIVE_NEXT
    if time.monotonic() < _DRIVE_NEXT:
        return
    if _DRIVE_PROCESS is not None and _DRIVE_PROCESS.poll() is None:
        return
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    helper = Path(__file__).with_name("drive_sync.py")
    if not helper.exists():
        helper = data / "lumen/files/drive_sync.py"
    if helper.exists() and (data / "lumen-drive/sync.json").exists():
        _DRIVE_NEXT = time.monotonic() + 60
        _DRIVE_PROCESS = subprocess.Popen(
            [sys.executable, str(helper)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def sync_memory():
    """Keep the opted-in memory helper; User Notes are owned by the Server app."""
    helper_name="memory_sync.py"
    process = _NOTES_PROCESSES.get(helper_name)
    if process is not None and process.poll() is None:
        return
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    helper = Path(__file__).with_name(helper_name)
    if not helper.exists():
        helper = data / "lumen/files" / helper_name
    state = Path(
        os.environ.get(
            "LUMEN_DATA", str(Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "lumen")
        )
    )
    if not helper.exists() or not (state / "lumen.sqlite3").exists():
        return
    _NOTES_PROCESSES[helper_name] = subprocess.Popen(
        [sys.executable, str(helper)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config-dir", type=Path)
    sub = p.add_subparsers(dest="command", required=True)
    pair = sub.add_parser("pair")
    pair.add_argument("--file", type=Path, help="Exportierter Verbindungsschlüssel (JSON)")
    pair.add_argument("--ca-file", type=Path)
    sub.add_parser("sync")
    sub.add_parser("watch")
    management = sub.add_parser("manage-action")
    management.add_argument("id", type=UUID)
    sub.add_parser("mcp-config")
    sub.add_parser("backup-init")
    task = sub.add_parser("task")
    task.add_argument("prompt")
    task.add_argument("--kind", choices=["assistant", "summary", "backup_check"], default="assistant")
    task.add_argument("--idempotency-key", required=True)
    status = sub.add_parser("status")
    status.add_argument("id")
    backup = sub.add_parser("backup")
    backup.add_argument("paths", nargs="+", type=Path)
    restore = sub.add_parser("restore")
    restore.add_argument("snapshot")
    restore.add_argument("target", type=Path)
    sub.add_parser("snapshots")
    sub.add_parser("check")
    args = p.parse_args()
    global ROOT, CONFIG
    if args.config_dir:
        ROOT = args.config_dir.resolve()
        CONFIG = ROOT / "connection.json"
    if args.command == "pair":
        raw = (
            args.file.read_text()
            if args.file
            else getpass.getpass("Verbindungsschlüssel (JSON, Eingabe verborgen): ")
        )
        cfg = json.loads(raw)
        for key in ("server", "device_id", "token", "backup_token"):
            if not isinstance(cfg.get(key), str):
                raise ValueError("Unvollständiger Verbindungsschlüssel.")
        if args.ca_file:
            cfg["ca_file"] = str(args.ca_file.resolve())
        # Validate before touching an existing connection.
        url = urlsplit(cfg["server"])
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.path
            or url.query
            or url.fragment
        ):
            raise ValueError("Eine HTTPS-Adresse ist erforderlich.")
        if request(cfg, "/bridge/me")["device_id"] != cfg["device_id"]:
            raise ValueError("Gerätekennung stimmt nicht.")
        if CONFIG.exists():
            raise ValueError("Bereits verbunden. Für ein weiteres Profil --config-dir verwenden.")
        cfg["system_access"] = dict(
            server=cfg["server"],
            device_id=cfg["device_id"],
            version=2,
            enabled="system_read" in request(cfg, "/bridge/me").get("capabilities", []),
        )
        save_private(CONFIG, json.dumps(cfg))
        print("Verbunden.")
        return
    cfg = read_config()
    if args.command == "manage-action":
        management_request(cfg, str(args.id))
    elif args.command == "sync":
        print(json.dumps(synchronize(cfg)))
    elif args.command == "watch":
        while True:
            # Custom connector profiles must never sync the default personal vault.
            if not args.config_dir:
                sync_data()
            try:
                cfg = read_config()
                report_inventory(cfg)
                synchronize(cfg)
            except urllib.error.HTTPError as error:
                if error.code in (401, 403):
                    print("Serverzugriff beendet. Erneutes Verbinden ist im Server möglich.", file=sys.stderr)
                    return
                print("Server nicht erreichbar; neuer Versuch in 30 Sekunden.", file=sys.stderr)
            except (urllib.error.URLError, OSError, ValueError):
                print("Verbindung unterbrochen; neuer Versuch in 30 Sekunden.", file=sys.stderr)
            time.sleep(30)
    elif args.command == "task":
        print(
            json.dumps(
                request(
                    cfg,
                    "/bridge/tasks",
                    {
                        "prompt": args.prompt,
                        "kind": args.kind,
                        "idempotency_key": args.idempotency_key,
                    },
                )
            )
        )
    elif args.command == "status":
        print(json.dumps(request(cfg, "/bridge/tasks/" + args.id)))
    elif args.command == "mcp-config":
        # Save secret-bearing config privately, don't print it into logs/chat history.
        path = ROOT / "opencode-mcp.json"
        save_private(
            path,
            json.dumps(
                {
                    "mcp": {
                        "lumen-server": {
                            "type": "remote",
                            "url": cfg["server"] + "/mcp/",
                            "headers": {"Authorization": "Bearer " + cfg["token"]},
                        }
                    }
                },
                indent=2,
            ),
        )
        print("MCP-Konfiguration gespeichert: " + str(path))
    elif args.command == "backup-init":
        key = ROOT / "backup.key"
        if not key.exists():
            save_private(key, secrets.token_urlsafe(48))
        restic(cfg, ["init"])
        print("Wiederherstellungsschlüssel separat sicher verwahren: " + str(key))
    elif args.command == "backup":
        paths = [str(path.resolve(strict=True)) for path in args.paths]
        restic(cfg, ["backup", "--"] + paths)
        request(cfg, "/bridge/backup-complete", {})
        print("Sicherung abgeschlossen.")
    elif args.command == "restore":
        target = args.target.resolve()
        if target.exists() and any(target.iterdir()):
            raise ValueError("Wiederherstellungsziel muss leer sein.")
        restic(cfg, ["restore", args.snapshot, "--target", str(target)])
    elif args.command == "snapshots":
        restic(cfg, ["snapshots"])
    elif args.command == "check":
        restic(cfg, ["check", "--read-data"])


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, urllib.error.URLError, subprocess.CalledProcessError) as e:
        print(
            "Lumen-Verbindung: "
            + (str(e) if not isinstance(e, urllib.error.HTTPError) else f"Server meldet HTTP {e.code}."),
            file=sys.stderr,
        )
        sys.exit(1)
