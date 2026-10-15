"""Explicit Drive binding conversion with a durable local journal and server receipt."""

from copy import deepcopy
import hashlib
import json
import mimetypes
import os
from pathlib import Path
from uuid import uuid4
import drive_sync as sync
import drive_local as local
import drive_transport as transport
import lumen_connect
from lumen_i18n import tr
from sync_migration import migrate_drive_binding


def fingerprint(root):
    return hashlib.sha256(
        json.dumps(
            {
                k: v
                for k, v in root.items()
                if k not in ("enabled", "status", "errors", "migration", "migration_history")
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


def load(rootid):
    config = lumen_connect.read_config()
    state = sync.read()
    if state["scope"] != sync.scope(config):
        raise ValueError(tr("Serverkonto geändert. Die ursprüngliche Verbindung wiederherstellen."))
    root = next(r for r in state["roots"] if r["id"] == rootid)
    me = lumen_connect.request(config, "/bridge/me")
    if str(me["device_id"]) != root["device"] or "drive" not in me["capabilities"]:
        raise ValueError(tr("Die ursprüngliche Gerätefreigabe ist nicht verfügbar."))
    with local.directory(root):
        pass
    if root.get("folder"):
        raise ValueError(tr("Dieser Ordner ist bereits zugeordnet."))
    migrate_drive_binding(root)
    prepare(root)
    root["enabled"] = False
    root["status"] = tr("Umstellung erforderlich")
    sync.save(state)
    return config, state, root


def prepare(root):
    for entry in root["entries"].values():
        if not entry.get("request_id") or entry.get("pending"):
            continue
        if entry.get("base"):
            raise ValueError(tr("Unvollständige Ersatzübertragung. Originalzuordnung zuerst prüfen."))
        path = entry["path"]
        digest = local.checksum(root, path)
        if digest is None:
            raise ValueError(tr("Eine vorgemerkte lokale Datei fehlt. Warteschlange bleibt erhalten."))
        parent = str(Path(path).parent)
        folder = (
            None if parent == "." else next((k for k, e in root["dirs"].items() if e["path"] == parent), None)
        )
        if parent != "." and folder is None:
            raise ValueError(tr("Der ursprüngliche Upload-Ordner ist unklar."))
        staged = ".lumen-drive/outgoing-" + entry["request_id"]
        local.mkdir(root, ".lumen-drive")
        with local.directory(root, ".lumen-drive") as target, local.source(root, path) as source:
            local.capacity(root, os.fstat(source.fileno()).st_size)
            try:
                fd = os.open(
                    Path(staged).name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=target,
                )
            except FileExistsError:
                if local.checksum(root, staged) != digest:
                    raise ValueError(
                        tr("Vorbereitete Upload-Datei weicht ab. Beide Fassungen bleiben erhalten.")
                    )
            else:
                with os.fdopen(fd, "wb") as output:
                    count = 0
                    while chunk := source.read(128 * 1024):
                        count += len(chunk)
                        if count > local.LIMIT:
                            raise ValueError(tr("Datei während Vorbereitung vergrößert."))
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                os.fsync(target)
        if local.checksum(root, staged) != digest:
            raise ValueError(tr("Lokale Datei während Vorbereitung verändert."))
        entry["pending"] = dict(
            request_id=entry["request_id"],
            hash=digest,
            path=path,
            folder=folder,
            previous=None,
            staged=staged,
            legacy_upload_target=entry.get("legacy_upload_target", root["workspace"]),
        )


def pending(root):
    result = []
    for entry in root["entries"].values():
        intent = entry.get("pending")
        if not intent:
            if entry.get("request_id"):
                raise ValueError(
                    tr(
                        "Eine unvollständige lokale Upload-Vorbereitung muss zuerst geprüft werden. Die Kennung bleibt erhalten."
                    )
                )
            continue
        if local.checksum(root, intent["staged"]) != intent["hash"]:
            raise ValueError(tr("Die gesicherte Upload-Datei wurde geändert. Umstellung pausiert."))
        previous = intent.get("previous")
        name = Path(intent["path"]).name
        with local.source(root, intent["staged"]) as stream:
            size = os.fstat(stream.fileno()).st_size
        body = dict(
            name=name,
            size=size,
            sha256=intent["hash"],
            folder=intent["folder"],
            replaces=previous["id"] if previous else None,
            revision=previous["revision"] if previous else None,
            mime=mimetypes.guess_type(name)[0] or "application/octet-stream",
        )
        if intent.get("legacy_upload_target"):
            body["workspace"] = intent["legacy_upload_target"]
        result.append(dict(request_id=intent["request_id"], body=body))
    return result


def preview(rootid, folder=None, name=None, adopt=False):
    with sync.locked():
        config, state, root = load(rootid)
        if root.get("migration"):
            raise ValueError(tr("Die begonnene Umstellung zuerst fortsetzen oder sicher abbrechen."))
        cache = sync.inventory(config)
        files = []
        folders = []
        # Resolve current versions by the original family; never broaden to unrelated roots.
        for family, old in root["cache"]["files"].items():
            row = cache["files"].get(family)
            if row is None:
                raise ValueError(tr("Ein Original ist nicht mehr freigegeben. Zuordnung zuerst prüfen."))
            if not row["trashed"]:
                files.append(row["id"])
        for key, old in root["cache"]["folders"].items():
            row = cache["folders"].get(key)
            if row is None:
                raise ValueError(
                    tr("Ein Originalordner ist nicht mehr freigegeben. Zuordnung zuerst prüfen.")
                )
            if not row["trashed"]:
                folders.append(key)
        plan = dict(
            binding_fingerprint=fingerprint(root),
            legacy_target=root["workspace"],
            folder=folder or str(uuid4()),
            new_name=name,
            adopt=adopt,
            files=sorted(files),
            folders=sorted(folders),
            uploads=pending(root),
        )
        result = sync.request(config, "/migrations/preview", plan)
        proposal = dict(plan=plan, preview=result)
        check_bindings(state, root, proposal, cache)
        return proposal


def check_bindings(state, root, proposal, cache):
    target = proposal["plan"]["folder"]
    sources = {row["id"] for row in proposal["preview"]["folders"]}
    for other in state["roots"]:
        folder = other.get("folder")
        if other["id"] == root["id"] or not folder:
            continue
        if folder == target or folder in sources or sync.paths(cache, folder).get(target) is not None:
            raise ValueError(
                tr(
                    "Dieser Zielordner oder ein Original-Unterordner ist bereits separat synchronisiert. Überlappende Zuordnungen sind nicht möglich."
                )
            )


def check_preview(root, proposal):
    if fingerprint(root) != proposal["plan"]["binding_fingerprint"]:
        raise ValueError(tr("Die lokale Warteschlange wurde geändert. Neue Vorschau erforderlich."))


def finish_uploads(rootid, proposal, progress=lambda *_: None):
    with sync.locked():
        config, state, root = load(rootid)
        check_preview(root, proposal)
        for item in proposal["preview"]["uploads"]:
            if item["state"] != "uploading":
                continue
            entry = next(
                e
                for e in root["entries"].values()
                if e.get("pending", {}).get("request_id") == item["request_id"]
            )
            intent = entry["pending"]

            def remember(key):
                intent["transfer_id"] = key
                sync.save(state)

            transport.upload(
                config,
                root,
                intent["staged"],
                intent["folder"],
                intent["request_id"],
                intent["hash"],
                intent.get("previous"),
                progress,
                filename=Path(intent["path"]).name,
                legacy_target=intent.get("legacy_upload_target"),
                remember=remember,
            )
        return True


def durable_save(state):
    sync.save(state)
    fd = os.open(sync.HOME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def archive(root, identity):
    # Hard links preserve staged bytes without copying content or altering active queue paths.
    directory = ".lumen-drive/migrations/" + identity
    for part in (".lumen-drive", ".lumen-drive/migrations", directory):
        local.mkdir(root, part)
    for entry in root["entries"].values():
        intent = entry.get("pending")
        if not intent:
            continue
        if local.checksum(root, intent["staged"]) != intent["hash"]:
            raise ValueError(tr("Die gesicherte Upload-Datei wurde geändert."))
        path = local.relative(intent["staged"])
        with local.directory(root, path.parent) as source, local.directory(root, directory) as target:
            os.link(
                path.name, intent["request_id"], src_dir_fd=source, dst_dir_fd=target, follow_symlinks=False
            )
            os.fsync(target)
        if local.checksum(root, directory + "/" + intent["request_id"]) != intent["hash"]:
            raise ValueError(tr("Upload-Sicherung konnte nicht bestätigt werden."))
    target = sync.HOME / "migrations" / (identity + ".json")
    lumen_connect.save_private(target, json.dumps(root, ensure_ascii=False))
    fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def finalize(state, root, result):
    if state["scope"] != sync.scope(lumen_connect.read_config()):
        raise ValueError(
            tr("Die Serververbindung wurde geändert. Mit der ursprünglichen Verbindung fortsetzen.")
        )
    journal = root["migration"]
    check_preview(root, journal)
    current = deepcopy(root)
    for row in result["files"]:
        current["cache"]["files"][row["family"]] = row
    for row in [result["folder"], *result["folders"]]:
        current["cache"]["folders"][row["id"]] = row
    for item in result["uploads"]:
        key, entry = next(
            (k, e)
            for k, e in current["entries"].items()
            if e.get("pending", {}).get("request_id") == item["request_id"]
        )
        intent = entry["pending"]
        if item["state"] == "not_started":
            body = item["next_body"]
            intent["folder"] = body["folder"]
            if intent.get("previous"):
                intent["previous"]["revision"] = body["revision"]
        elif item["state"] == "completed":
            row = next((r for r in result["files"] if r["id"] == item["file"]["id"]), item["file"])
            family = row["family"]
            if family != key and family in current["entries"]:
                raise ValueError(
                    tr("Eine Upload-Kennung ist lokal doppelt belegt. Originale bleiben erhalten.")
                )
            entry["base"] = dict(
                path=intent["path"],
                hash=intent["hash"],
                trashed=False,
                revision=row["revision"],
                id=row["id"],
            )
            entry.pop("pending", None)
            entry.pop("request_id", None)
            if family != key:
                current["entries"].pop(key)
                current["entries"][family] = entry
            current["cache"]["files"][family] = row
    current["folder"] = result["folder"]["id"]
    current["enabled"] = True
    current["status"] = tr("Ordner zugeordnet – bereit zum Abgleich")
    current.setdefault("migration_history", []).append(journal["id"])
    current.pop("migration")
    state["roots"][state["roots"].index(root)] = current
    durable_save(state)
    return current


def apply(rootid, proposal=None):
    with sync.locked():
        config, state, root = load(rootid)
        if not root.get("migration"):
            if proposal is None or not proposal["preview"]["ready"]:
                raise ValueError(tr("Zuerst eine vollständige Vorschau bestätigen."))
            check_preview(root, proposal)
            check_bindings(state, root, proposal, sync.inventory(config))
            identity = str(uuid4())
            archive(root, identity)
            root["migration"] = dict(
                id=identity, plan=proposal["plan"], fingerprint=proposal["preview"]["fingerprint"]
            )
            durable_save(state)
        journal = root["migration"]
        check_preview(root, journal)
        # The same request resolves lost replies and a restart after the server commit.
        result = sync.request(
            config,
            "/migrations/" + journal["id"],
            dict(plan=journal["plan"], fingerprint=journal["fingerprint"]),
        )
        return finalize(state, root, result)


def cancel(rootid):
    with sync.locked():
        config, state, root = load(rootid)
        journal = root.get("migration")
        if not journal:
            return root
        result = transport.request(config, "/migrations/" + journal["id"], method="DELETE")
        if result.get("applied"):
            return finalize(state, root, result)
        if not result.get("cancelled"):
            raise ValueError(tr("Abbruch konnte nicht bestätigt werden."))
        root.pop("migration")
        durable_save(state)
        return root
