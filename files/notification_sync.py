"""Bounded notification sync on the existing connector; no foreign-app upload."""

import hashlib
import json
import time
from datetime import datetime
from urllib.error import HTTPError
from uuid import UUID

from lumen_notifications import database, publish, toast


def timestamp(value):
    return (
        datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() if value else 0
    )


def synchronize(config, profile, request, path=None):
    if profile.get("notification_protocol") != 1:
        return False
    scope = hashlib.sha256(
        json.dumps([config["server"], str(UUID(profile["user_id"]))]).encode()
    ).hexdigest()
    allowed = "notifications" in profile.get("capabilities", [])
    with database(path) as db:
        db.execute(
            """INSERT INTO bindings(scope,server,device,allowed) VALUES (?,?,?,?)
            ON CONFLICT(scope) DO UPDATE SET server=excluded.server,device=excluded.device,allowed=excluded.allowed""",
            (scope, config["server"], config["device_id"], allowed),
        )
        pending = (
            [
                dict(row)
                for row in db.execute(
                    """SELECT o.*,n.external_id FROM outbox o
            JOIN notifications n ON n.id=o.id WHERE n.scope=? LIMIT 100""",
                    (scope,),
                )
            ]
            if allowed
            else []
        )
        cursor = db.execute(
            "SELECT cursor FROM bindings WHERE scope=?", (scope,)
        ).fetchone()["cursor"]
    if not allowed:
        return True
    for op in pending:
        try:
            remote = request(
                config,
                "/bridge/notifications/" + str(int(op["external_id"])),
                {"revision": op["revision"], **json.loads(op["changes"])},
            )
        except HTTPError as error:
            if error.code==422 and 'resolved' in json.loads(op['changes']):
                with database(path) as db:
                    removed=db.execute('DELETE FROM outbox WHERE id=? AND version=?',(op['id'],op['version'])).rowcount
                    if removed:db.execute('UPDATE notifications SET resolved=0,completion_supported=0 WHERE id=?',(op['id'],))
                publish('Lumen Notification','completion-protocol:'+scope,'Server unterstützt Erledigen noch nicht','Bitte den Lumen Server aktualisieren. Die Meldung bleibt offen.',kind='problem',popup=False,path=path)
                continue
            if error.code not in (404, 409):
                raise
            with database(path) as db:
                db.execute(
                    "DELETE FROM outbox WHERE id=? AND version=?",
                    (op["id"], op["version"]),
                )
            if error.code == 409:
                from lumen_i18n import tr

                publish(
                    "Lumen Notification",
                    "conflict:" + op["id"],
                    tr("Meldungszustand geändert"),
                    tr(
                        "Ein anderes Gerät hat diese Meldung inzwischen geändert. Der Serverstand wird übernommen; du kannst die Aktion erneut wählen."
                    ),
                    attention=True,
                    path=path,
                    popup=False,
                )
            continue
        with database(path) as db:
            db.execute(
                "DELETE FROM outbox WHERE id=? AND version=?", (op["id"], op["version"])
            )
            # A second click while this request was in flight builds on our own
            # acknowledged change, not on the previous server revision.
            db.execute(
                "UPDATE outbox SET revision=? WHERE id=? AND revision=?",
                (remote["state_revision"], op["id"], op["revision"]),
            )
        ingest(scope, remote, path)
    # Two pages per heartbeat bound work on small machines; subsequent polls continue.
    for _ in range(2):
        result = request(config, "/bridge/notifications?after=" + str(cursor))
        rows = result["items"]
        if not isinstance(rows, list) or len(rows) > 100:
            raise ValueError("Invalid notification page")
        for row in rows:
            ingest(scope, row, path)
        cursor = int(result["next"] or 0)
        with database(path) as db:
            db.execute("UPDATE bindings SET cursor=? WHERE scope=?", (cursor, scope))
        if not cursor:
            break
    return True


def ingest(scope, row, path=None):
    nid = int(row["id"])
    version = int(row["state_revision"])
    if nid < 1 or version < 1:
        raise ValueError("Invalid notification state")
    with database(path) as db:
        previous=db.execute("SELECT * FROM notifications WHERE scope=? AND source='Lumen Server' AND external_id=?",(scope,str(nid))).fetchone()
    identity = publish(
        "Lumen Server",
        str(nid),
        row["title"],
        row.get("body", ""),
        target="server-task:" + str(UUID(row["task_id"]))
        if row.get("task_id")
        else "server",
        scope=scope,
        attention=bool(row.get("attention")),
        kind=row.get("kind","message"),
        popup=False,
        path=path,
    )
    with database(path) as db:
        # An in-flight response must not erase a newer local click or server version.
        changed=db.execute(
            """UPDATE notifications SET read=?,archived=?,snoozed=?,state_revision=?,created=?,updated=?,title=?,body=?,kind=?,resolved=?,completion_supported=?
            WHERE id=? AND state_revision<=? AND NOT EXISTS(SELECT 1 FROM outbox WHERE id=?)""",
            (
                bool(row["read"]),
                bool(row["archived"]),
                timestamp(row.get("snoozed_until")),
                version,
                timestamp(row["created"]),
                timestamp(row.get("updated",row["created"])),
                row["title"][:300],row.get("body","")[:2000],row.get("kind","message"),bool(row.get("resolved")),"resolved" in row,
                identity,
                version,
                identity,
            ),
        )
    if changed.rowcount and (previous is None or timestamp(row.get("updated",row["created"]))>previous["updated"]) and not (row["read"] or row["archived"] or row.get("resolved") or timestamp(row.get("snoozed_until"))>time.time()):
        with database(path) as db:
            preference=db.execute("SELECT mode FROM preferences WHERE source='Lumen Server'").fetchone()
        if not preference or preference["mode"]=="popup":toast("Lumen Server",identity)
