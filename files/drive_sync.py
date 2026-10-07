"""Selective Drive folders on the existing paired connector; no model is involved."""

from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4, uuid5, UUID
import fcntl
import hashlib
import json
import os
import time
import urllib.error
import lumen_connect
import drive_local as local
import drive_transport as transport
from lumen_i18n import tr

HOME = (
    Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "lumen-drive"
)


def read():
    try:
        return json.loads((HOME / "sync.json").read_text())
    except FileNotFoundError:
        return dict(scope="", roots=[])


def save(state):
    lumen_connect.save_private(
        HOME / "sync.json", json.dumps(state, ensure_ascii=False)
    )


def scope(config):
    return hashlib.sha256(
        (config["server"] + "\0" + config["token"]).encode()
    ).hexdigest()


@contextmanager
def locked():
    HOME.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (HOME / "sync.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def request(config, path, body=None):
    return lumen_connect.request(config, "/bridge/drive" + path, body)


def inventory(config, workspace):
    files = {}
    folders = {}
    after = None
    cursor = None
    while True:
        page = request(
            config,
            "/inventory?"
            + urlencode(
                dict(workspace=workspace, **({"after": after} if after else {}))
            ),
        )
        if cursor is None:
            cursor = page["cursor"]
        files.update((r["family"], r) for r in page["items"])
        folders.update((r["id"], r) for r in page["folders"])
        after = page["next"]
        if not after:
            break
        if len(files) > 100000:
            raise ValueError(tr("Drive-Bestand zu groß."))
    result = dict(files=files, folders=folders, cursor=cursor)
    refresh(config, workspace, result)
    return result


def refresh(config, workspace, cache):
    while True:
        page = request(
            config,
            "/changes?" + urlencode(dict(workspace=workspace, cursor=cache["cursor"])),
        )
        cache["files"].update((r["family"], r) for r in page["items"])
        cache["folders"].update((r["id"], r) for r in page["folders"])
        cache["cursor"] = page["cursor"]
        if not page["more"]:
            break


def paths(cache, selected):
    result = {}
    visiting = set()

    def path(key):
        if key == selected:
            return ""
        if key is None:
            return "" if selected is None else None
        if key in visiting:
            raise ValueError(tr("Ungültige Serverordner."))
        if key in result:
            return result[key]
        row = cache["folders"].get(key)
        if not row or row["trashed"]:
            return None
        visiting.add(key)
        parent = path(row["parent_id"])
        visiting.remove(key)
        value = (
            str(local.relative((parent + "/" if parent else "") + row["name"]))
            if parent is not None
            else None
        )
        if value and value.split("/")[0] == ".lumen-drive":
            raise ValueError(tr("Reservierter Drive-Ordnername."))
        result[key] = value
        return value

    for key in cache["folders"]:
        path(key)
    return result


def configure(path, workspace, folder=None):
    """The UI confirms this preview before persisting an enabled scope."""
    with locked():
        config = lumen_connect.read_config()
        me = lumen_connect.request(config, "/bridge/me")
        if "drive" not in me["capabilities"]:
            raise ValueError(
                tr("Auf dem Server zuerst „Lumen Drive synchronisieren“ freigeben.")
            )
        state = read()
        if state["scope"] not in ("", scope(config)):
            raise ValueError(
                tr(
                    "Serverkonto geändert. Bestehende Drive-Zuordnungen zuerst entfernen."
                )
            )
        chosen = Path(path).expanduser().absolute()
        if chosen.is_symlink():
            raise ValueError(tr("Symbolische Ordner nicht synchronisieren."))
        chosen = chosen.resolve(strict=True)
        from lumen_store import Store
        from tools_data import Library

        store = Store()
        notebook = store.setting("knowledge/notebook", "")
        protected = [
            HOME,
            Library("workbench").root,
            store.directory,
            Path.home() / ".config/lumen-server",
        ]
        if notebook:
            protected.append(Path(notebook).expanduser().resolve())
        for other in [*protected, *(Path(r["path"]) for r in state["roots"])]:
            if chosen.is_relative_to(other) or other.is_relative_to(chosen):
                raise ValueError(
                    tr(
                        "Dieser Ordner überschneidet sich mit einem vorhandenen Abgleich oder Lumen-App-Daten."
                    )
                )
        cache = inventory(config, workspace)
        if folder and (
            folder not in cache["folders"] or cache["folders"][folder]["trashed"]
        ):
            raise ValueError(tr("Drive-Ordner nicht verfügbar."))
        # Two local writers for overlapping remote trees would turn removals into recreations.
        newpaths = paths(cache, folder)
        for root in state["roots"]:
            if root["workspace"] == workspace and (
                root["folder"] == folder
                or root["folder"] is None
                or folder is None
                or newpaths.get(root["folder"]) is not None
                or paths(cache, root["folder"]).get(folder) is not None
            ):
                raise ValueError(
                    tr(
                        "Dieser Drive-Bereich ist bereits mit einem lokalen Ordner verbunden."
                    )
                )
        info = chosen.stat()
        root = dict(
            id=uuid4().hex,
            path=str(chosen),
            identity=[info.st_dev, info.st_ino],
            workspace=workspace,
            folder=folder,
            enabled=True,
            entries={},
            dirs={},
            cache=cache,
            conflicts={},
            status=tr("Bereit für den ersten Abgleich"),
            device=str(me["device_id"]),
        )
        local.scan(root)
        state["scope"] = scope(config)
        state["roots"].append(root)
        save(state)
        return root


def toggle(identity, enabled=None, remove=False):
    with locked():
        state = read()
        root = next(r for r in state["roots"] if r["id"] == identity)
        if remove:
            state["roots"].remove(root)
        else:
            root["enabled"] = bool(enabled)
        save(state)


def choose(rootid, key, side):
    if side not in ("local", "server"):
        raise ValueError("Invalid resolution")
    with locked():
        state = read()
        root = next(r for r in state["roots"] if r["id"] == rootid)
        root["conflicts"][key]["choice"] = side
        save(state)


def actual(path, signature, scan):
    if signature:
        matches = [p for p, r in scan.items() if r["signature"][:2] == signature[:2]]
        if len(matches) == 1:
            return matches[0]
    return path if path in scan else None


def reconcile(config, root, persist, progress):
    with local.directory(root):
        pass
    try:
        with local.directory(root, ".lumen-drive") as parent:
            pending = {
                Path(e["pending"]["staged"]).name
                for e in root["entries"].values()
                if e.get("pending")
            }
            for name in os.listdir(parent):
                if (
                    name.startswith(("stage-", "outgoing-"))
                    and name not in pending
                    and os.stat(name, dir_fd=parent, follow_symlinks=False).st_mtime
                    < time.time() - 86400
                ):
                    os.unlink(name, dir_fd=parent)
    except FileNotFoundError:
        pass
    cache = root["cache"]
    try:
        refresh(config, root["workspace"], cache)
    except urllib.error.HTTPError as error:
        if error.code != 409:
            raise
        restored = inventory(config, root["workspace"])
        cache.clear()
        cache.update(restored)
    persist()
    if root["folder"] and (
        root["folder"] not in cache["folders"]
        or cache["folders"][root["folder"]]["trashed"]
    ):
        raise ValueError(
            tr(
                "Der verbundene Drive-Ordner wurde entfernt. Lokale Dateien bleiben erhalten."
            )
        )
    scan, dirs, errors = local.scan(root, root.get("scan"))
    root["scan"] = scan
    remote_paths = paths(cache, root["folder"])
    conflicts = {}

    def conflict(key, title, row):
        previous = root["conflicts"].get(key, {})
        fingerprint = hashlib.sha256(
            json.dumps(row, sort_keys=True).encode()
        ).hexdigest()
        if previous.get("fingerprint") == fingerprint and previous.get("choice"):
            return previous["choice"]
        conflicts[key] = dict(title=title, fingerprint=fingerprint)
        return None

    def rewrite(old, new):
        for entry in [*root["dirs"].values(), *root["entries"].values()]:
            if entry["path"] == old or entry["path"].startswith(old + "/"):
                entry["path"] = new + entry["path"][len(old) :]
            # A parent rename changes descendants' logical path without independently editing them.
            base = entry.get("base", {})
            if isinstance(base, dict) and (
                base.get("path") == old or base.get("path", "").startswith(old + "/")
            ):
                base["path"] = new + base["path"][len(old) :]

    for key, path in sorted(
        remote_paths.items(), key=lambda pair: (pair[1] or "").count("/")
    ):
        if not path or key in root["dirs"]:
            continue
        local.mkdir(root, path)
        root["dirs"][key] = dict(path=path, base=path)
        persist()
    scan, dirs, errors = local.scan(root, scan)
    # Existing folders retain their IDs across local and remote renames.
    for key, entry in sorted(
        list(root["dirs"].items()), key=lambda pair: pair[1]["path"].count("/")
    ):
        row = cache["folders"].get(key)
        if not row and entry.get("pending"):
            parent = str(Path(entry["path"]).parent)
            target = (
                root["folder"]
                if parent == "."
                else next(k for k, e in root["dirs"].items() if e["path"] == parent)
            )
            row = request(
                config,
                "/folders?" + urlencode(dict(workspace=root["workspace"])),
                dict(id=key, name=Path(entry["path"]).name, parent_id=target),
            )
            cache["folders"][key] = row
            entry.pop("pending", None)
            remote_paths = paths(cache, root["folder"])
            persist()
        if not row:
            raise ValueError(tr("Unvollständiger Drive-Bestand."))
        old = entry["path"]
        current = actual(old, entry.get("signature"), dirs)
        remote = remote_paths.get(key)
        base = entry.get("base", old)
        changed_local = current != base
        changed_remote = remote != base
        if changed_local and changed_remote and current != remote:
            choice = conflict("folder:" + key, old, row)
            if choice == "local":
                changed_remote = False
            elif choice == "server":
                changed_local = False
            else:
                continue
        if changed_local and not changed_remote:
            if current is None:
                continue  # Remove empty server folders after file tombstones.
            parent = str(Path(current).parent)
            target = (
                root["folder"]
                if parent == "."
                else next(
                    (k for k, e in root["dirs"].items() if e["path"] == parent), None
                )
            )
            if parent != "." and target is None:
                continue
            row = request(
                config,
                "/folders/" + key,
                dict(
                    name=Path(current).name, parent_id=target, revision=row["revision"]
                ),
            )
            cache["folders"][key] = row
            rewrite(old, current)
            entry["path"] = current
            entry["base"] = current
            remote_paths = paths(cache, root["folder"])
            persist()
        elif changed_remote and not changed_local and current is not None:
            if remote is None:
                continue  # Children first, then empty directory.
            try:
                local.move(root, current, remote)
            except FileNotFoundError:
                conflicts["folder:" + key] = dict(
                    title=old, fingerprint="parent-pending"
                )
                continue
            rewrite(old, remote)
            entry["path"] = remote
            entry["base"] = remote
            persist()
            scan, dirs, errors = local.scan(root, scan)
        elif (
            changed_remote
            and not changed_local
            and current is None
            and remote is not None
        ):
            local.mkdir(root, remote)
            entry["path"] = remote
            entry["base"] = remote
            persist()
            scan, dirs, errors = local.scan(root, scan)
        elif current == remote:
            entry["base"] = current
    if conflicts:
        root["conflicts"] = conflicts
        root["status"] = tr("Ordnerkonflikte zuerst lösen")
        persist()
        return
    # Bring down missing remote folders, then publish new local directories.
    for key, path in sorted(
        remote_paths.items(), key=lambda pair: (pair[1] or "").count("/")
    ):
        if path is None or key == root["folder"]:
            continue
        if key in root["dirs"]:
            continue
        local.mkdir(root, path)
        root["dirs"][key] = dict(path=path, base=path)
        persist()
    scan, dirs, errors = local.scan(root, scan)
    bound = {actual(e["path"], e.get("signature"), dirs) for e in root["dirs"].values()}
    for path in sorted(dirs, key=lambda p: p.count("/")):
        if path in bound:
            continue
        parent = str(Path(path).parent)
        target = (
            root["folder"]
            if parent == "."
            else next((k for k, e in root["dirs"].items() if e["path"] == parent), None)
        )
        if parent != "." and target is None:
            continue
        key = str(uuid4())
        root["dirs"][key] = dict(
            path=path, base=path, signature=dirs[path]["signature"], pending=True
        )
        persist()
        row = request(
            config,
            "/folders?" + urlencode(dict(workspace=root["workspace"])),
            dict(id=key, name=Path(path).name, parent_id=target),
        )
        root["dirs"][key].pop("pending", None)
        cache["folders"][key] = row
        persist()
    # Case-insensitive filesystems must not bind two remote folders to one inode.
    identities = {}
    for key, entry in root["dirs"].items():
        path = entry["path"]
        try:
            with local.directory(root, path) as fd:
                info = os.fstat(fd)
                marker = (info.st_dev, info.st_ino)
        except FileNotFoundError:
            continue
        if marker in identities and identities[marker] != path:
            raise ValueError(
                tr("Drive-Ordnernamen kollidieren auf diesem Dateisystem.")
            )
        identities[marker] = path
    remote_paths = paths(cache, root["folder"])

    def file_path(row):
        parent = (
            ""
            if row["folder_id"] == root["folder"]
            else remote_paths.get(row["folder_id"])
        )
        if parent is None:
            return None
        path = str(local.relative((parent + "/" if parent else "") + row["name"]))
        if path.split("/")[0] == ".lumen-drive" or Path(path).suffix.lower() == ".kdbx":
            return None
        return path

    def version(row):
        return dict(
            path=file_path(row),
            hash=row["sha256"],
            trashed=row["trashed"],
            revision=row["revision"],
            id=row["id"],
        )

    def write_file(key, entry, path, digest, row):
        parent = str(Path(path).parent)
        folder = (
            root["folder"]
            if parent == "."
            else next(k for k, e in root["dirs"].items() if e["path"] == parent)
        )
        intent = entry.get("pending")
        if not intent:
            intent = dict(
                request_id=entry.get("request_id", str(uuid4())),
                hash=digest,
                path=path,
                folder=folder,
                previous=row,
            )
            local.capacity(root, scan[path]["signature"][2])
            local.mkdir(root, ".lumen-drive")
            intent["staged"] = ".lumen-drive/outgoing-" + intent["request_id"]
            with (
                local.directory(root, ".lumen-drive") as parent,
                local.source(root, path) as source,
            ):
                try:
                    os.unlink(Path(intent["staged"]).name, dir_fd=parent)
                except FileNotFoundError:
                    pass
                fd = os.open(
                    Path(intent["staged"]).name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent,
                )
                with os.fdopen(fd, "wb") as output:
                    copied = 0
                    while chunk := source.read(128 * 1024):
                        copied += len(chunk)
                        if copied > local.LIMIT:
                            raise ValueError(tr("Maximal 64 MB pro Datei."))
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
            if local.checksum(root, intent["staged"]) != digest:
                raise ValueError(tr("Datei während des Lesens verändert."))
            entry["pending"] = intent
            persist()
        # Hash-checked transport refuses any local edits during transfer.
        if local.checksum(root, intent["staged"]) != intent["hash"]:
            raise ValueError(
                tr(
                    "Ausstehende Übertragung lokal geändert. Erneut abgleichen oder Konflikt prüfen."
                )
            )
        result = transport.upload(
            config,
            root,
            intent["staged"],
            root["workspace"],
            intent["folder"],
            intent["request_id"],
            intent["hash"],
            intent["previous"],
            progress,
            filename=Path(intent["path"]).name,
        )
        entry["base"] = dict(
            path=intent["path"],
            hash=intent["hash"],
            trashed=False,
            revision=result["revision"],
            id=result["id"],
        )
        entry.pop("pending", None)
        entry.pop("request_id", None)
        cache["files"][result["family"]] = result
        persist()
        with local.directory(root, ".lumen-drive") as parent:
            os.unlink(Path(intent["staged"]).name, dir_fd=parent)
        return result

    # New remote files join by stable family, with collisions kept as conflicts.
    for key, row in cache["files"].items():
        path = file_path(row)
        if (
            not row["trashed"]
            and Path(row["name"]).suffix.lower() == ".kdbx"
            and (
                row["folder_id"] == root["folder"]
                or remote_paths.get(row["folder_id"]) is not None
            )
        ):
            errors.append(
                row["name"]
                + tr(" · Nicht synchronisiert (Dateigrenze oder Tresordatei)")
            )
        if key not in root["entries"] and path is not None and not row["trashed"]:
            root["entries"][key] = dict(path=path, base=None)
            persist()
    owned = set()
    for key, entry in list(root["entries"].items()):
        row = cache["files"].get(key)
        base = entry.get("base")
        path = actual(entry["path"], entry.get("signature"), scan)
        if path:
            owned.add(path)
        if path and scan[path]["blocked"]:
            continue
        if (
            entry.get("pending")
            and row
            and row["id"]
            == str(
                uuid5(
                    UUID(root["device"]),
                    root["workspace"] + ":" + entry["pending"]["request_id"],
                )
            )
        ):
            intent = entry.pop("pending")
            entry["base"] = base = dict(
                path=intent["path"],
                hash=intent["hash"],
                trashed=False,
                revision=row["revision"],
                id=row["id"],
            )
            entry.pop("request_id", None)
            persist()
        if row is None:
            if base:
                raise ValueError(tr("Unvollständiger Drive-Bestand."))
            if path:
                write_file(key, entry, path, scan[path]["hash"], None)
            continue
        remote = version(row)
        rpath = remote["path"]
        if rpath is None and row["trashed"]:
            rpath = entry["path"]
            remote["path"] = rpath
        if rpath is None:
            unchanged = (
                path is None
                or base
                and path == base["path"]
                and scan[path]["hash"] == base["hash"]
            )
            choice = "server" if unchanged else conflict(key, entry["path"], row)
            if choice == "server":
                if path:
                    local.install(root, path, None, scan[path]["hash"])
                del root["entries"][key]
                persist()
                continue
            if choice == "local" and path:
                parent = str(Path(path).parent)
                folder = (
                    root["folder"]
                    if parent == "."
                    else next(k for k, e in root["dirs"].items() if e["path"] == parent)
                )
                row = request(
                    config,
                    "/files/" + row["id"],
                    dict(
                        name=Path(path).name,
                        folder_id=folder,
                        revision=row["revision"],
                        trashed=False,
                    ),
                )
                cache["files"][key] = row
                remote = version(row)
                rpath = remote["path"]
                base = remote
            else:
                continue
        remote_value = None if row["trashed"] else (rpath, row["sha256"])
        local_value = (path, scan[path]["hash"]) if path else None
        baseline = None if not base or base["trashed"] else (base["path"], base["hash"])
        lc = local_value != baseline
        rc = remote_value != baseline
        if lc and rc and local_value != remote_value:
            choice = conflict(key, path or rpath, row)
            if choice == "local":
                rc = False
            elif choice == "server":
                lc = False
            else:
                continue
        if local_value == remote_value:
            entry.update(
                path=path or entry["path"],
                base=remote,
                signature=scan[path]["signature"] if path else None,
            )
            entry.pop("pending", None)
            persist()
            continue
        if lc and not rc:
            if path is None:
                row = request(
                    config,
                    "/files/" + row["id"],
                    dict(
                        name=row["name"],
                        folder_id=row["folder_id"],
                        revision=row["revision"],
                        trashed=True,
                    ),
                )
            else:
                parent = str(Path(path).parent)
                folder = (
                    root["folder"]
                    if parent == "."
                    else next(k for k, e in root["dirs"].items() if e["path"] == parent)
                )
                if (row["name"], row["folder_id"], row["trashed"]) != (
                    Path(path).name,
                    folder,
                    False,
                ):
                    row = request(
                        config,
                        "/files/" + row["id"],
                        dict(
                            name=Path(path).name,
                            folder_id=folder,
                            revision=row["revision"],
                            trashed=False,
                        ),
                    )
                    cache["files"][key] = row
                    persist()
                if scan[path]["hash"] != row["sha256"]:
                    row = write_file(key, entry, path, scan[path]["hash"], row)
            cache["files"][key] = row
            entry.update(
                path=path or entry["path"],
                base=version(row),
                signature=scan[path]["signature"] if path else None,
            )
            persist()
        elif rc or base is None:
            if row["size"] > local.LIMIT:
                errors.append(rpath + tr(" · Maximal 64 MB pro Datei."))
                continue
            if path and path != rpath and not row["trashed"]:
                local.move(root, path, rpath)
                path = rpath
                entry["path"] = rpath
                persist()
            expected = local_value[1] if local_value else None
            staged = (
                None
                if row["trashed"]
                else transport.download(config, root, row, progress)
            )
            local.install(root, path or rpath, staged, expected)
            entry.update(path=rpath, base=remote, signature=None)
            persist()
    # New local files are bound before upload; a lost response cannot duplicate them.
    for path, item in scan.items():
        if path in owned or item["blocked"]:
            continue
        if any(e["path"] == path for e in root["entries"].values()):
            continue
        request_id = str(uuid4())
        key = str(uuid5(UUID(root["device"]), root["workspace"] + ":" + request_id))
        entry = dict(
            path=path, signature=item["signature"], base=None, request_id=request_id
        )
        root["entries"][key] = entry
        persist()
        write_file(key, entry, path, item["hash"], None)
    # Empty folders disappear only after all contained files have been reconciled.
    scan, dirs, scan_errors = local.scan(root, scan)
    errors = list(dict.fromkeys(errors + scan_errors))
    for key, entry in sorted(
        list(root["dirs"].items()), key=lambda pair: -pair[1]["path"].count("/")
    ):
        row = cache["folders"].get(key)
        if not row:
            continue
        current = actual(entry["path"], entry.get("signature"), dirs)
        remote = paths(cache, root["folder"]).get(key)
        if current is None and remote is not None:
            try:
                cache["folders"][key] = request(
                    config,
                    "/folders/" + key,
                    dict(
                        name=row["name"],
                        parent_id=row["parent_id"],
                        revision=row["revision"],
                        trashed=True,
                    ),
                )
            except Exception:
                conflicts["folder:" + key] = dict(
                    title=entry["path"], fingerprint="not-empty"
                )
                continue
        elif current is not None and remote is None:
            try:
                local.remove_empty(root, current)
            except ValueError:
                conflicts["folder:" + key] = dict(
                    title=current, fingerprint="not-empty"
                )
                continue
        if (current is None or remote is None) and not conflicts.get("folder:" + key):
            entry["base"] = None
        entry["signature"] = (
            dirs[current]["signature"] if current and current in dirs else None
        )
    root["conflicts"] = conflicts
    root["scan"] = scan
    root["errors"] = errors
    root["last_sync"] = time.time()
    root["status"] = (
        tr("Konflikte prüfen")
        if conflicts
        else tr("Einige Dateien wurden ausgelassen")
        if errors
        else tr("Synchronisiert")
    )
    persist()


def synchronize(identity=None, progress=lambda *_: None):
    with locked():
        state = read()
        config = lumen_connect.read_config()
        if state["scope"] != scope(config):
            raise ValueError(tr("Serverkonto geändert. Drive-Abgleich angehalten."))
        for root in state["roots"]:
            if not root["enabled"] or identity and root["id"] != identity:
                continue
            if not identity and root.get("next_try", 0) > time.time():
                continue
            try:
                reconcile(config, root, lambda: save(state), progress)
                root["failures"] = 0
                root["next_try"] = 0
                save(state)
            except Exception as error:
                root["failures"] = min(5, root.get("failures", 0) + 1)
                root["next_try"] = time.time() + min(900, 30 * 2 ** root["failures"])
                root["status"] = tr("Abgleich angehalten: ") + str(error)
                save(state)
                from lumen_notifications import report
                report('Lumen Drive',root['id'],True,tr('Drive-Abgleich braucht deine Aufmerksamkeit'),
                       tr('Öffne die verbundenen Ordner in Lumen Files und prüfe den Abgleich.'),target='app:drive')
                if identity:
                    raise
            else:
                from lumen_notifications import report
                bad=bool(root.get('conflicts') or root.get('errors'))
                report('Lumen Drive',root['id'],bad,tr('Drive-Abgleich braucht deine Aufmerksamkeit') if bad else tr('Drive-Abgleich wieder in Ordnung'),
                       tr('Öffne die verbundenen Ordner in Lumen Files und prüfe den Abgleich.') if bad else '',target='app:drive')
        return state


if __name__ == "__main__":
    import signal

    signal.alarm(180)
    if any(r["enabled"] for r in read()["roots"]):
        synchronize()
