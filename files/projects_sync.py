"""Opt-in replication of native project records; no execution is replicated."""

from contextlib import contextmanager
import fcntl
import hashlib
import json
import time
from uuid import UUID
import lumen_connect
from lumen_i18n import tr
from projects_data import Projects


def identity(value):
    return str(UUID(value))


def scope(config):
    from sync_identity import scope as stable_scope
    legacy = hashlib.sha256((config["server"] + "\0" + config["token"]).encode()).hexdigest()
    return stable_scope(config, ["projects"], legacy)


def available(config):
    rows, offset = [], 0
    while True:
        page = lumen_connect.request(config, '/bridge/projects?offset=' + str(offset))
        rows.extend(page['items'])
        following = page['next_offset']
        if following is None:
            return rows
        if not isinstance(following, int) or following <= offset or following > 5000:
            raise ValueError(tr('Ungültige Projektliste. Erneut abgleichen.'))
        offset = following


def state_path(library):
    return library.root / "server-sync.json"


def read_state(library):
    try:
        return json.loads(state_path(library).read_text())
    except FileNotFoundError:
        return dict(enabled=False, scope="", projects={}, conflicts={})


def save_state(library, state):
    lumen_connect.save_private(state_path(library), json.dumps(state, ensure_ascii=False))


def info(library):
    config = lumen_connect.read_config()
    state = read_state(library)
    user = lumen_connect.request(config, "/bridge/me")
    if state.get("scope") not in ("", scope(config)):
        return dict(
            server=config["server"],
            enabled=False,
            changed_account=True,
            allowed="projects" in user["capabilities"],
        )
    return dict(
        server=config["server"],
        enabled=state["enabled"],
        allowed="projects" in user["capabilities"],
        projects=list(state["projects"]),
        last_sync=state.get("last_sync", 0),
        conflicts=list(state.get("conflicts", {})),
        changed_account=False,
        server_projects=available(config)
        if "projects" in user["capabilities"]
        else [],
    )


@contextmanager
def locked(library):
    with (library.root / "server-sync.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def configure(library, enabled, project=None, remote_project=None, all_projects=None):
    raise ValueError(tr('Lumen Projekte wird direkt auf dem Lumen Server bearbeitet.'))
    with locked(library):
        state = read_state(library)
        if not enabled:
            state["enabled"] = False
            save_state(library, state)
            return
        config = lumen_connect.read_config()
        user = lumen_connect.request(config, "/bridge/me")
        if "projects" not in user["capabilities"]:
            raise ValueError(tr("Auf dem Server zuerst „Projekte synchronisieren“ freigeben."))
        if state.get("scope") not in ("", scope(config)):
            raise ValueError(tr("Anderes Serverkonto. Bestehende Projektbindungen zuerst getrennt prüfen."))
        state.update(enabled=True, scope=scope(config))
        if all_projects is not None: state["all_projects"] = bool(all_projects)
        if remote_project:
            remote_projects = available(config)
            if not any(p["id"] == remote_project for p in remote_projects):
                raise ValueError(tr("Projekt nicht mehr freigegeben."))
            local = UUID(remote_project).hex
            if local not in state["projects"]:
                with library.connect() as db:
                    if db.execute("SELECT 1 FROM records WHERE id=?", (local,)).fetchone():
                        raise ValueError(tr("Lokale Projektkennung ist bereits belegt."))
                state["projects"][local] = dict(remote=remote_project, nodes={})
        if project: bind_local(library, state, project)
        save_state(library, state)


def bind_local(library, state, project):
    library.get(project)
    with library.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute(
            "SELECT 1 FROM project_runs r JOIN project_items i ON i.id=r.task WHERE i.project=? AND r.status='running'",
            (project,),
        ).fetchone():
            raise ValueError(tr("Zuerst die laufenden lokalen Projektaufträge beenden."))
        stored = db.execute("SELECT data FROM records WHERE id=?", (project,)).fetchone()
        data = json.loads(stored["data"])
        data["server_bound"] = True
        db.execute(
            "UPDATE records SET data=?,updated=? WHERE id=?", (json.dumps(data), time.time(), project)
        )
    state["projects"].setdefault(project, dict(remote=identity(project), nodes={}, publish=True))


def payload(row, root=False):
    return dict(
        title=row["title"],
        notes=row.get("notes", ""),
        goal=row.get("goal", ""),
        attachments=row.get("server_attachments", []),
        depends=[identity(i) for i in row.get("depends", [])],
        done=bool(row.get("status") == "done" and not root and row["kind"] == "manual"),
        operation=row.get("operation", "analysis"),
        interval_minutes=max(60, int(row.get("interval", 86400)) // 60),
    )


def remote_payload(row):
    return {
        k: row.get(k, default)
        for k, default in dict(
            title="",
            notes="",
            goal="",
            attachments=[],
            depends=[],
            done=False,
            operation="analysis",
            interval_minutes=1440,
        ).items()
    }


def local_rows(library, project):
    root = library.get(project)
    root["kind"] = "project"
    root["archived"] = root["_archived"]
    rows = [
        root,
        *Projects(library).items(project, archived=False),
        *Projects(library).items(project, archived=True),
    ]
    return {identity(row["id"]): row for row in rows}


def apply_remote(library, project, remote, before):
    """CAS against the fields read before the request; keep unrelated local data."""
    now = time.time()
    key = UUID(remote["id"]).hex
    isroot = remote["kind"] == "project"
    with library.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        table = "records" if isroot else "project_items"
        existing = db.execute("SELECT * FROM " + table + " WHERE id=?", (key,)).fetchone()
        if before:
            expected = payload(before, isroot)
            if not existing:
                raise ValueError(tr("Projekt wurde während des Abgleichs geändert. Erneut versuchen."))
            current = dict(
                json.loads(existing["data"]), **{k: existing[k] for k in existing.keys() if k != "data"}
            )
            if payload(current, isroot) != expected or bool(current["archived"]) != bool(before["archived"]):
                raise ValueError(tr("Projekt wurde während des Abgleichs geändert. Erneut versuchen."))
        elif existing:
            raise ValueError(tr("Lokale Projektkennung ist bereits belegt."))
        data = json.loads(existing["data"]) if existing else dict(resources=[], questions=[])
        data.update(
            notes=remote["notes"],
            goal=remote.get("goal", ""),
            server_attachments=remote.get("attachments", []),
            depends=[UUID(i).hex for i in remote.get("depends", [])],
            status="done"
            if remote.get("done") or remote.get("state") == "completed"
            else remote.get("state", "open"),
            server_state=remote.get("state", "open"),
            operation=remote.get("operation", "analysis"),
            interval=remote.get("interval_minutes", 1440) * 60,
            enabled=False,
            server_bound=True,
            server_role=remote.get("role", data.get("server_role", "editor")),
        )
        if isroot:
            db.execute(
                "INSERT INTO records VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,data=excluded.data,archived=excluded.archived,updated=excluded.updated",
                (key, remote["title"], json.dumps(data), int(remote["archived"]), now),
            )
        else:
            parent = "" if remote["kind"] == "initiative" else UUID(remote["parent_id"]).hex
            db.execute(
                "INSERT INTO project_items VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,data=excluded.data,archived=excluded.archived,updated=excluded.updated",
                (
                    key,
                    project,
                    parent,
                    remote["kind"],
                    remote["title"],
                    json.dumps(data),
                    now,
                    now,
                    int(remote["archived"]),
                ),
            )
    return key


def normalized_links(value):
    kinds = {'file', 'note', 'conversation', 'task', 'project_task'}
    if not isinstance(value, list) or len(value) > 5000:
        raise ValueError(tr('Ungültige Projektverweise.'))
    links = set()
    for row in value:
        if set(row) != {'kind', 'resource_id'} or row['kind'] not in kinds:
            raise ValueError(tr('Ungültiger Projektverweis.'))
        links.add((row['kind'], identity(row['resource_id'])))
    return [dict(kind=k, resource_id=i) for k, i in sorted(links)]


def apply_links(library, project, links, before):
    with library.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT data FROM records WHERE id=?', (project,)).fetchone()
        if row is None:
            raise ValueError(tr('Projekt nicht mehr vorhanden.'))
        data = json.loads(row['data'])
        if normalized_links(data.get('server_links', [])) != before:
            raise ValueError(tr('Projektverweise während des Abgleichs geändert. Erneut versuchen.'))
        data['server_links'] = links
        db.execute('UPDATE records SET data=?,updated=? WHERE id=?', (json.dumps(data), time.time(), project))


def sync_links(library, project, binding, state, snapshot, request):
    root = library.get(project)
    local = normalized_links(root.get('server_links', []))
    remote = normalized_links(snapshot['links'])
    base = binding.get('links', [] if 'server_links' in root else remote)
    conflict_key = 'links:' + binding['remote']
    if local != base and remote != base and local != remote:
        state.setdefault('conflicts', {})[conflict_key] = dict(
            project=project, kind='links', title=root['title'] + ' · ' + tr('Verweise'),
            local=local, server=remote, server_revision=snapshot['collection_revision'])
        save_state(library, state)
        return 0
    if local != base and local != remote and 'server_links' in root:
        if snapshot['role'] == 'reader':
            raise ValueError(tr('Dieses Serverprojekt ist nur lesbar.'))
        answer = request('/' + binding['remote'] + '/links',
                         dict(revision=snapshot['collection_revision'], links=local))
        remote = normalized_links(answer['links'])
    if local != remote or 'server_links' not in root:
        apply_links(library, project, remote, local)
    binding['links'] = remote
    state.setdefault('conflicts', {}).pop(conflict_key, None)
    save_state(library, state)
    return int(local != remote)


def synchronize(library):
    raise ValueError(tr('Lumen Projekte wird direkt auf dem Lumen Server bearbeitet.'))
    Projects(library)
    with (library.root / "server-sync.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = read_state(library)
        if not state["enabled"]:
            return dict(changed=0, conflicts=[])
        config = lumen_connect.read_config()
        if state["scope"] != scope(config):
            raise ValueError(tr("Serverkonto geändert. Projektabgleich angehalten."))

        def request(path, body=None):
            return lumen_connect.request(config, "/bridge/projects" + path, body)

        remote_projects = available(config)
        known = {p["id"]: p for p in remote_projects}
        changed = 0
        for remote_project in remote_projects:
            if remote_project["owned"]:
                key = UUID(remote_project["id"]).hex
                if key not in state["projects"]:
                    # Never adopt an unrelated local record just because its ID matches.
                    with library.connect() as db:
                        if db.execute("SELECT 1 FROM records WHERE id=?", (key,)).fetchone():
                            raise ValueError(tr("Lokale Projektkennung ist bereits belegt."))
                    state["projects"][key] = dict(remote=remote_project["id"], nodes={})
        if state.get("all_projects"):
            for project in library.all():
                if project["id"] not in state["projects"]:
                    bind_local(library, state, project["id"])
        save_state(library, state)
        for project, binding in state["projects"].items():
            remote = binding["remote"]
            path = "/" + remote
            if remote not in known:
                if not binding.get("publish"):
                    raise ValueError(tr("Projekt nicht mehr freigegeben. Lokale Daten bleiben erhalten."))
                root = library.get(project)
                base = remote_payload(dict(title=root["title"]))
                binding["nodes"].setdefault(remote, dict(payload=base, revision=0, archived=False))
                save_state(library, state)
                request(path, dict(title=root["title"]))
                binding.pop("publish", None)
                save_state(library, state)
            snapshot = request(path)
            remote_rows = {r["id"]: r for r in [snapshot["project"], *snapshot["items"]]}
            with library.connect() as db:
                exists = db.execute("SELECT 1 FROM records WHERE id=?", (project,)).fetchone()
            rows = local_rows(library, project) if exists else {}
            # Publish new children in hierarchy order before resolving dependencies.
            for rid, row in sorted(rows.items(), key=lambda pair: pair[1]["kind"] != "initiative"):
                if row["kind"] == "project" or rid in remote_rows:
                    continue
                if snapshot["role"] == "reader":
                    raise ValueError(tr("Dieses Serverprojekt ist nur lesbar."))
                binding["nodes"].setdefault(
                    rid, dict(payload=remote_payload(dict(title=row["title"])), revision=1, archived=False)
                )
                save_state(library, state)
                request(
                    path + "/items",
                    dict(
                        id=rid,
                        parent_id=remote if row["kind"] == "initiative" else identity(row["parent"]),
                        kind=row["kind"],
                        title=row["title"],
                    ),
                )
            snapshot = request(path)
            ordered = [
                snapshot["project"],
                *sorted(snapshot["items"], key=lambda r: r["kind"] != "initiative"),
            ]
            for row in ordered:
                rid = row["id"]
                local = rows.get(rid)
                base = binding["nodes"].get(rid)
                rp = remote_payload(row)
                lp = payload(local, row["kind"] == "project") if local else None
                local_changed = bool(
                    local
                    and (base is None or lp != base["payload"] or bool(local["archived"]) != base["archived"])
                )
                remote_changed = base is None or rp != base["payload"] or row["archived"] != base["archived"]
                same = local is not None and lp == rp and bool(local["archived"]) == row["archived"]
                if local_changed and remote_changed and not same:
                    state.setdefault("conflicts", {})[rid] = dict(
                        project=project,
                        title=row["title"],
                        local=lp,
                        server=rp,
                        server_revision=row["revision"],
                    )
                    save_state(library, state)
                    continue
                pushed = False
                if local_changed and not same:
                    if snapshot["role"] == "reader":
                        raise ValueError(tr("Dieses Serverprojekt ist nur lesbar."))
                    if row["archived"] and not local["archived"]:
                        row = request(
                            path + "/items/" + rid + "/archive",
                            dict(revision=row["revision"], archived=False),
                        )
                    if lp != rp:
                        row = request(path + "/items/" + rid, dict(revision=row["revision"], **lp))
                    if bool(local["archived"]) != row["archived"]:
                        row = request(
                            path + "/items/" + rid + "/archive",
                            dict(revision=row["revision"], archived=bool(local["archived"])),
                        )
                    pushed = True
                receipt = dict(
                    payload=remote_payload(row), revision=row["revision"], archived=row["archived"]
                )
                if pushed:
                    binding["nodes"][rid] = receipt
                    save_state(library, state)
                if (
                    not same
                    or not local.get("server_bound", False)
                    or local.get("server_role") != snapshot["role"]
                    or local.get("server_state") != row.get("state", "open")
                ):
                    apply_remote(library, project, {**row, "role": snapshot["role"]}, local)
                    changed += 1
                binding["nodes"][rid] = receipt
                state.setdefault("conflicts", {}).pop(rid, None)
                save_state(library, state)
            changed += sync_links(library, project, binding, state, request(path), request)
        state["last_sync"] = time.time()
        save_state(library, state)
        return dict(changed=changed, conflicts=list(state.get("conflicts", {})))


def resolve(library, identity_value, keep_local):
    raise ValueError(tr('Lumen Projekte wird direkt auf dem Lumen Server bearbeitet.'))
    with locked(library):
        config = lumen_connect.read_config()
        state = read_state(library)
        if state["scope"] != scope(config):
            raise ValueError("Server account changed")
        conflict = state["conflicts"][identity_value]
        binding = state["projects"][conflict["project"]]
        snapshot = lumen_connect.request(config, "/bridge/projects/" + binding["remote"])
        if conflict.get('kind') == 'links':
            if snapshot['collection_revision'] != conflict['server_revision']:
                raise ValueError(tr('Serverfassung inzwischen geändert. Erneut abgleichen.'))
            remote = normalized_links(snapshot['links'])
            if not keep_local:
                current = normalized_links(library.get(conflict['project']).get('server_links', []))
                if current != conflict['local']:
                    raise ValueError(tr('Lokale Projektverweise inzwischen geändert. Erneut abgleichen.'))
                apply_links(library, conflict['project'], remote, current)
            binding['links'] = remote
            del state['conflicts'][identity_value]
            save_state(library, state)
            return
        row = next(r for r in [snapshot["project"], *snapshot["items"]] if r["id"] == identity_value)
        if row["revision"] != conflict["server_revision"]:
            raise ValueError(tr("Serverfassung inzwischen geändert. Erneut abgleichen."))
        if not keep_local:
            local = local_rows(library, conflict["project"])[identity_value]
            apply_remote(library, conflict["project"], row, local)
        binding["nodes"][identity_value] = dict(
            payload=remote_payload(row), revision=row["revision"], archived=row["archived"]
        )
        del state["conflicts"][identity_value]
        save_state(library, state)


if __name__ == "__main__":
    import sys
    print("Lumen Projekte wird direkt auf dem Lumen Server bearbeitet; der lokale Projektabgleich ist stillgelegt.", file=sys.stderr)
    sys.exit(1)
