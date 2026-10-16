"""Durable Lumen notifications. Foreign desktop messages stay in KDE's model."""

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path


def location():
    return (
        Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
        / "lumen/notifications.sqlite3"
    )


@contextmanager
def database(path=None):
    path = Path(path) if path else location()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    db = sqlite3.connect(path, timeout=2)
    db.row_factory = sqlite3.Row
    try:
        with db:
            db.execute("""CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY, scope TEXT NOT NULL, source TEXT NOT NULL,
                external_id TEXT NOT NULL, revision INTEGER NOT NULL, title TEXT NOT NULL,
                body TEXT NOT NULL, target TEXT NOT NULL, created REAL NOT NULL,
                updated REAL NOT NULL, attention INTEGER NOT NULL DEFAULT 0,
                read INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0,
                snoozed REAL NOT NULL DEFAULT 0)""")
            db.execute(
                "CREATE TABLE IF NOT EXISTS preferences(source TEXT PRIMARY KEY, mode TEXT NOT NULL)"
            )
            if "state_revision" not in {
                row[1] for row in db.execute("PRAGMA table_info(notifications)")
            }:
                db.execute(
                    "ALTER TABLE notifications ADD COLUMN state_revision INTEGER NOT NULL DEFAULT 0"
                )
            if "wake_notified" not in {
                row[1] for row in db.execute("PRAGMA table_info(notifications)")
            }:
                db.execute(
                    "ALTER TABLE notifications ADD COLUMN wake_notified REAL NOT NULL DEFAULT 0"
                )
            db.execute(
                "CREATE TABLE IF NOT EXISTS status_events(source TEXT,key TEXT,bad INTEGER,revision INTEGER,PRIMARY KEY(source,key))"
            )
            db.execute("""CREATE TABLE IF NOT EXISTS bindings (
                scope TEXT PRIMARY KEY, server TEXT NOT NULL, device TEXT NOT NULL, allowed INTEGER NOT NULL,
                cursor INTEGER NOT NULL DEFAULT 0)""")
            db.execute("""CREATE TABLE IF NOT EXISTS outbox (
                id TEXT PRIMARY KEY, changes TEXT NOT NULL, revision INTEGER NOT NULL, version TEXT NOT NULL)""")
            db.execute(
                "DELETE FROM notifications WHERE scope='local' AND archived=1 AND updated<?",
                (time.time() - 30 * 86400,),
            )
            yield db
    finally:
        db.close()


def publish(
    source,
    external_id,
    title,
    body="",
    *,
    target="",
    revision=1,
    scope="local",
    attention=False,
    popup=True,
    path=None,
):
    for value, limit in (
        (source, 100),
        (external_id, 200),
        (title, 300),
        (body, 2000),
        (scope, 300),
        (target, 4096),
    ):
        if not isinstance(value, str) or len(value) > limit or "\0" in value:
            raise ValueError("Invalid notification")
    if (
        not source
        or not external_id
        or not title
        or type(revision) is not int
        or revision < 1
    ):
        raise ValueError("Invalid notification")
    identity = hashlib.sha256(
        json.dumps([scope, source, external_id]).encode()
    ).hexdigest()
    now = time.time()
    with database(path) as db:
        changed = db.execute(
            """INSERT INTO notifications
            (id,scope,source,external_id,revision,title,body,target,created,updated,attention)
            VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            revision=excluded.revision,title=excluded.title,body=excluded.body,target=excluded.target,
            updated=excluded.updated,attention=excluded.attention,read=0,archived=0,snoozed=0
            WHERE excluded.revision>notifications.revision""",
            (
                identity,
                scope,
                source,
                external_id,
                revision,
                title,
                body,
                target,
                now,
                now,
                bool(attention),
            ),
        ).rowcount
        preference = db.execute(
            "SELECT mode FROM preferences WHERE source=?", (source,)
        ).fetchone()
    if changed and popup and (not preference or preference["mode"] == "popup"):
        toast(source, identity)
    return identity


def toast(source, identity):
    source = "Lumen Notes" if source == "Lumen Wissen" else source
    # KDE remains the only popup owner and applies its own DND/lock-screen rules.
    # Keep private task titles/bodies out of the lock-screen toast.
    try:
        from lumen_i18n import tr

        subprocess.run(
            [
                "notify-send",
                "-a",
                source,
                "-h",
                "string:x-lumen-id:" + identity,
                source,
                tr("Eine neue Meldung ist in Lumen Notification bereit."),
            ],
            timeout=3,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        pass  # The durable card survives a missing popup service.


def snapshot(path=None, wake=True):
    with database(path) as db:
        allowed = active_scopes(db)
        due = (
            [
                dict(row)
                for row in db.execute(
                    """SELECT id,source FROM notifications WHERE
            snoozed>0 AND snoozed<=? AND wake_notified<snoozed AND archived=0
            AND scope IN ("""
                    + ",".join("?" for _ in allowed)
                    + """)
            AND source NOT IN (SELECT source FROM preferences WHERE mode!='popup') LIMIT 10""",
                    (time.time(), *allowed),
                )
            ]
            if wake
            else []
        )
        for row in due:
            db.execute(
                "UPDATE notifications SET wake_notified=snoozed WHERE id=?",
                (row["id"],),
            )
        rows = [
            dict(row)
            for row in db.execute(
                """SELECT * FROM notifications
            WHERE source NOT IN (SELECT source FROM preferences WHERE mode='muted')
            AND scope IN ("""
                + ",".join("?" for _ in allowed)
                + """)
            ORDER BY updated DESC LIMIT 500""",
                allowed,
            )
        ]
    for row in due:
        toast(row["source"], row["id"])
    # Display name only: existing source IDs still govern deduplication and mutes.
    for row in rows:
        if row["source"] == "Lumen Wissen":
            row["source"] = "Lumen Notes"
    return {
        "items": rows,
        "unread": sum(
            not row["read"] and not row["archived"] and row["snoozed"] <= time.time()
            for row in rows
        ),
    }


def change(identity, action, path=None):
    if not re.fullmatch("[a-f0-9]{64}", identity):
        raise ValueError("Invalid notification ID")
    with database(path) as db:
        row = db.execute(
            "SELECT * FROM notifications WHERE id=?", (identity,)
        ).fetchone()
        if not row:
            raise ValueError("Notification no longer available")
        if row["scope"] not in active_scopes(db):
            raise ValueError("Server connection no longer available")
        if action == "open":
            target = row["target"]
            if row["scope"] != "local":
                from urllib.parse import urlencode
                from uuid import UUID

                binding = db.execute(
                    "SELECT server FROM bindings WHERE scope=?", (row["scope"],)
                ).fetchone()
                route = (
                    {
                        "app": "tasks",
                        "task": str(UUID(target.removeprefix("server-task:"))),
                    }
                    if target.startswith("server-task:")
                    else {"app": "notifications"}
                )
                subprocess.Popen(
                    [
                        "xdg-open",
                        binding["server"] + "/?" + urlencode(route),
                    ],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif target in (
                "app:files",
                "app:drive",
                "app:wissen",
                "app:vault",
                "app:backups",
                "app:updater",
                "app:system",
                "app:settings",
            ):
                from lumen_launch import executable

                name, args = {
                    "app:drive": ("files", ["lumen-drive://"]),
                    "app:settings": ("settings", ["--sync"]),
                    "app:backups": ("vault", ["--backups"]),
                }.get(target, (target[4:], []))
                subprocess.Popen(
                    [executable("lumen-" + name), *args],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif target.startswith("lumen:"):
                from interop_open import open_url

                open_url(target)
            else:
                raise ValueError("Notification has no local target")
            action = "read"
        changes = {
            "read": ("read", 1),
            "unread": ("read", 0),
            "archive": ("archived", 1),
            "restore": ("archived", 0),
            "later": ("snoozed", time.time() + 3600),
            "now": ("snoozed", 0),
        }
        if action not in changes:
            raise ValueError("Invalid notification action")
        field, value = changes[action]
        db.execute(
            "UPDATE notifications SET " + field + "=? WHERE id=?", (value, identity)
        )
        if action == "archive" and row["scope"] == "local":
            db.execute(
                "UPDATE notifications SET updated=? WHERE id=?", (time.time(), identity)
            )
        if action == "later":
            db.execute("UPDATE notifications SET read=0 WHERE id=?", (identity,))
        if row["scope"] != "local":
            import uuid
            from datetime import datetime, timezone

            queued = db.execute(
                "SELECT changes,revision FROM outbox WHERE id=?", (identity,)
            ).fetchone()
            fields = json.loads(queued["changes"]) if queued else {}
            if action == "later":
                fields["read"] = False
            fields["snoozed_until" if field == "snoozed" else field] = (
                (
                    datetime.fromtimestamp(value, timezone.utc).isoformat()
                    if value
                    else None
                )
                if field == "snoozed"
                else bool(value)
            )
            db.execute(
                "INSERT OR REPLACE INTO outbox VALUES (?,?,?,?)",
                (
                    identity,
                    json.dumps(fields),
                    queued["revision"] if queued else row["state_revision"],
                    uuid.uuid4().hex,
                ),
            )


def active_scopes(db):
    scopes = ["local"]
    try:
        from lumen_connect import read_config

        config = read_config()
        scopes += [
            row["scope"]
            for row in db.execute(
                "SELECT scope FROM bindings WHERE server=? AND device=? AND allowed=1",
                (config["server"], config["device_id"]),
            )
        ]
    except (OSError, ValueError, KeyError):
        pass
    return scopes


def preferences(path=None):
    with database(path) as db:
        return dict(db.execute("SELECT source,mode FROM preferences").fetchall())


def set_preference(source, mode, path=None):
    if (
        mode not in ("popup", "center", "muted")
        or not isinstance(source, str)
        or not 0 < len(source) <= 100
    ):
        raise ValueError("Invalid notification preference")
    with database(path) as db:
        db.execute("INSERT OR REPLACE INTO preferences VALUES (?,?)", (source, mode))


def report(source, key, bad, title, body="", target="", path=None):
    """One card per incident; caller retains its existing per-job/source lease."""
    try:
        with database(path) as db:
            old = db.execute(
                "SELECT bad,revision FROM status_events WHERE source=? AND key=?",
                (source, key),
            ).fetchone()
            if not old and not bad or old and old["bad"] == bool(bad):
                return
            revision = old["revision"] + 1 if old else 1
            # Commit the card first. After interruption the same revision replays safely.
        publish(
            source,
            key,
            title,
            body,
            target=target,
            attention=bad,
            revision=revision,
            path=path,
        )
        with database(path) as db:
            db.execute(
                "INSERT OR REPLACE INTO status_events VALUES (?,?,?,?)",
                (source, key, bool(bad), revision),
            )
    except (OSError, sqlite3.Error, ValueError):
        import logging

        logging.getLogger(__name__).warning("Lumen notification could not be stored")


def announce(*args, **kwargs):
    """A notification failure must not fail an already completed backup/update."""
    try:
        return publish(*args, **kwargs)
    except (OSError, sqlite3.Error, ValueError):
        import logging

        logging.getLogger(__name__).warning("Lumen notification could not be stored")


def remind(title, due, key, path=None):
    from datetime import datetime, timezone

    moment = datetime.fromisoformat(due.replace("Z", "+00:00"))
    if (
        moment.tzinfo is None
        or not time.time() < moment.timestamp() <= time.time() + 366 * 86400
    ):
        raise ValueError(
            "Reminder requires a future time with a timezone (within one year)"
        )
    identity = publish("Lumen", key, title, popup=False, path=path)
    with database(path) as db:
        row = db.execute(
            "SELECT title,snoozed FROM notifications WHERE id=?", (identity,)
        ).fetchone()
        if (
            row["title"] != title
            or row["snoozed"]
            and row["snoozed"] != moment.timestamp()
        ):
            raise ValueError("Reminder key already used with other contents")
        db.execute(
            "UPDATE notifications SET snoozed=? WHERE id=? AND snoozed=0 AND wake_notified=0",
            (moment.timestamp(), identity),
        )
    return {"id": identity, "due": moment.astimezone(timezone.utc).isoformat()}


def open_center():
    # Keep KDE's notification model in Plasma's process, where its full history lives.
    script = """var found=false; panels().forEach(function(p){p.widgets().forEach(function(w){
        if(!found && w.type==="org.lumen.control"){w.currentConfigGroup=["General"];
        w.writeConfig("notificationRequest",String(Date.now()));w.reloadConfig();found=true;}
    });}); print(found);"""
    result = subprocess.run(
        [
            "qdbus6",
            "org.kde.plasmashell",
            "/PlasmaShell",
            "org.kde.PlasmaShell.evaluateScript",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    if result.stdout.strip() != "true":
        raise ValueError("Lumen Notification benötigt das Lumen-Panel in KDE Plasma.")


def notification_options(changes=None):
    """Read or explicitly change the same two options exposed in Settings."""
    from PySide6.QtCore import QSettings

    keys = {
        "native_popups": "notifications/nativePopups",
        "quiet_games": "notifications/quietGames",
    }
    settings = QSettings("Lumen", "Assistant")
    if changes is not None:
        if (
            not isinstance(changes, dict)
            or not changes
            or set(changes) - keys.keys()
            or any(type(v) is not bool for v in changes.values())
        ):
            raise ValueError("Choose native_popups and/or quiet_games as booleans")
        if "native_popups" in changes and changes["native_popups"] != settings.value(
            keys["native_popups"], True, type=bool
        ):
            configure_popups(changes["native_popups"])
        if "quiet_games" in changes:
            settings.setValue(keys["quiet_games"], changes["quiet_games"])
        settings.sync()
        if settings.status() != QSettings.NoError:
            raise ValueError("Notification settings could not be saved")
    return {name: settings.value(key, True, type=bool) for name, key in keys.items()}


def popup_context():
    from lumen_hardware import gaming as game_active
    from PySide6.QtCore import QSettings

    settings = QSettings("Lumen", "Assistant")
    gaming = settings.value("notifications/quietGames", True, type=bool) and game_active()
    return {
        "gaming": gaming,
        "native": settings.value("notifications/nativePopups", True, type=bool),
    }


def configure_popups(enabled=True):
    """Switch only the notification applet; keep KDE's shared model/receiver."""
    from PySide6.QtCore import QSettings

    backup = location().with_name("notification-trays.json")
    backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    saved = json.loads(backup.read_text()) if backup.exists() else []

    def evaluate(script):
        result = subprocess.run(
            [
                "qdbus6",
                "org.kde.plasmashell",
                "/PlasmaShell",
                "org.kde.PlasmaShell.evaluateScript",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return json.loads(result.stdout)

    base = """const plugin="org.kde.plasma.notifications";
const trays=[];panels().forEach(p=>p.widgets().forEach(w=>{if(w.type==="org.kde.plasma.systemtray")trays.push(w);}));
function items(w){w.currentConfigGroup=["General"];return String(w.readConfig("extraItems","")).split(",").filter(Boolean);}
"""
    if enabled:
        changed = evaluate(
            base
            + """
if(!panels().some(p=>p.widgets().some(w=>w.type==="org.lumen.control"))) throw Error("Lumen panel missing");
print(JSON.stringify(trays.filter(w=>items(w).includes(plugin)).map(w=>w.id)));"""
        )
        saved = sorted(set(saved + changed))
        # Save the restoration receipt before changing the tray, including on retries.
        staged = backup.with_suffix(".next")
        fd = os.open(
            staged, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(fd, "w") as stream:
            json.dump(saved, stream)
        os.replace(staged, backup)
        evaluate(
            base
            + """trays.forEach(w=>{const before=items(w);if(before.includes(plugin)){w.writeConfig("extraItems",before.filter(i=>i!==plugin));w.reloadConfig();}});print("true");"""
        )
    elif saved:
        evaluate(
            base
            + "const saved="
            + json.dumps(saved)
            + ';trays.forEach(w=>{const before=items(w);if(saved.includes(w.id)&&!before.includes(plugin)){before.push(plugin);w.writeConfig("extraItems",before);w.reloadConfig();}});print("true");'
        )
    settings = QSettings("Lumen", "Assistant")
    settings.setValue("notifications/nativePopups", enabled)
    settings.sync()


if __name__ == "__main__":
    import sys

    if "--restore-kde" in sys.argv:
        configure_popups(False)
    else:
        open_center()
