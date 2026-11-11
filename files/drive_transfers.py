"""Persistent Drive copy plans. Credentials are reloaded, never stored in tickets."""

import hashlib
import os
from pathlib import Path
from uuid import UUID, uuid5

import drive_local as local
import drive_sync as sync
import drive_transport as transport
import lumen_connect
from lumen_i18n import tr
from transfer_copy import root


resolve = sync.resolve


def identifier(value, name):
    return str(uuid5(UUID(value["id"]), name))


def checksum(origin, path, progress):
    with local.source(origin, path) as stream:
        before = local.signature(os.fstat(stream.fileno()))
        digest = hashlib.sha256()
        while chunk := stream.read(1024**2):
            digest.update(chunk)
            progress(0, 0)
        if not local.transfer_unchanged(before, os.fstat(stream.fileno())):
            raise ValueError(tr("Quelldatei während des Lesens verändert."))
        return digest.hexdigest(), before


def require_current(value):
    """Uploads queued before account-based sync are refused; never sent, cancelled or rewritten."""
    if value.get("drive", {}).get("space"):
        raise ValueError(tr("Diese Übertragung stammt aus einer älteren Lumen-Version und wird nicht gesendet. Bitte neu starten; lokale Dateien bleiben erhalten."))


def upload(store, value, config, sources, progress):
    from lumen_transfers import update, PREFIX
    require_current(value)

    plan = value.get("upload_plan")
    if plan is None:
        plan = dict(folders=[], files=[])
        for source in sources:
            path = Path(source)
            if path.is_symlink():
                raise ValueError(tr("Symbolische Ordner nicht verwenden."))
            origin = root(path.parent)
            pending = [(path.name, value["drive"]["folder"])]
            while pending:
                relative, folder = pending.pop()
                current = Path(origin["path"]) / relative
                update(store, value["id"], current=str(current))
                with local.directory(origin, Path(relative).parent) as fd:
                    import stat

                    info = os.stat(
                        Path(relative).name, dir_fd=fd, follow_symlinks=False
                    )
                if stat.S_ISDIR(info.st_mode):
                    key = identifier(value, "folder:" + str(current))
                    plan["folders"].append(
                        dict(id=key, name=current.name, parent_id=folder)
                    )
                    with local.directory(origin, relative) as fd:
                        pending.extend(
                            (str(Path(relative) / name), key)
                            for name in sorted(os.listdir(fd), reverse=True)
                        )
                else:
                    if relative != path.name and current.suffix.lower() == ".kdbx":
                        raise ValueError(
                            tr(
                                "Tresordateien werden nicht als Drive-Ordner synchronisiert."
                            )
                        )
                    digest, stamp = checksum(origin, relative, progress)
                    plan["files"].append(
                        dict(
                            root=origin,
                            path=relative,
                            folder=folder,
                            size=stamp[2],
                            sha256=digest,
                            stamp=stamp,
                            request=identifier(value, "file:" + str(current)),
                            previous=value["drive"]
                            .get("previous", {})
                            .get(str(current)),
                        )
                    )
                if len(plan["folders"]) + len(plan["files"]) > 10000:
                    raise ValueError(tr("Maximal 10.000 Einträge pro Drive-Ordner."))
        update(store, value["id"], upload_plan=plan)
    for folder in plan["folders"]:
        sync.request(config, '/folders', folder)
        progress(0, 0)
    total, count = sum(item["size"] for item in plan["files"]), 0
    done = list(store.setting(PREFIX + value["id"]).get("upload_done", []))
    for item in plan["files"]:
        update(
            store, value["id"], current=str(Path(item["root"]["path"]) / item["path"])
        )
        if item["request"] not in done:
            with local.source(item["root"], item["path"]) as stream:
                if not local.transfer_unchanged(item["stamp"], os.fstat(stream.fileno())):
                    raise ValueError(
                        tr(
                            "Quelldatei wurde verändert. Bitte einen neuen Upload starten."
                        )
                    )
            transport.upload(
                config,
                item["root"],
                item["path"],
                item["folder"],
                item["request"],
                item["sha256"],
                item["previous"],
                lambda n, _: progress(count + n, total),
            )
            done.append(item["request"])
            update(store, value["id"], upload_done=done)
        count += item["size"]
        progress(count, total)


def publish(store, value, destination, staging, name, source):
    from lumen_transfers import update, PREFIX

    receipt = store.setting(PREFIX + value["id"]).get("publishing", {})
    staged_path = Path(destination["path"]) / staging / name
    if os.path.lexists(staged_path):
        info = staged_path.lstat()
        receipt[source] = [info.st_dev, info.st_ino]
        update(store, value["id"], publishing=receipt)
        local.move(destination, staging + "/" + name, name)
    else:
        info = (Path(destination["path"]) / name).lstat()
        if receipt.get(source) != [info.st_dev, info.st_ino]:
            raise ValueError(tr("Zieldatei wurde inzwischen ersetzt."))


def download(store, value, config, target, progress):
    from lumen_transfers import update, PREFIX

    plan = value.get("download_plan")
    if plan is None:
        destination = root(target)
        entries = []
        names = set()
        for source, (kind, row) in zip(
            value["sources"], resolve(config, value["sources"])
        ):
            name = str(local.relative(row["name"]))
            if name in names or os.path.lexists(Path(target) / name):
                raise ValueError(tr("Datei existiert bereits: {0}", name))
            names.add(name)
            files = [(name, row)] if kind == "file" else []
            folders = []
            if kind == "folder":
                cache = sync.inventory(config)
                paths = sync.paths(cache, row["id"])
                paths[row["id"]] = ""
                folders = [name] + [
                    str(Path(name) / p)
                    for key, p in paths.items()
                    if p and not cache["folders"][key]["trashed"]
                ]
                for child in cache["files"].values():
                    parent = paths.get(child["folder_id"])
                    if parent is not None and not child["trashed"]:
                        files.append((str(Path(name) / parent / child["name"]), child))
            for path, _ in files:
                local.relative(path)
            if len(files) + len(folders) > 10000:
                raise ValueError(tr("Maximal 10.000 Einträge pro Drive-Ordner."))
            entries.append(dict(source=source, name=name, files=files, folders=folders))
        plan = dict(
            root=destination, entries=entries, stage=".lumen-drive/copy-" + value["id"]
        )
        local.mkdir(destination, ".lumen-drive")
        local.mkdir(destination, plan["stage"])
        plan["stage_root"] = root(Path(target) / plan["stage"])
        update(store, value["id"], download_plan=plan)
    destination, staging = plan["root"], plan["stage"]
    stage_root = plan["stage_root"]
    with local.directory(destination), local.directory(stage_root):
        pass
    total = sum(row["size"] for entry in plan["entries"] for _, row in entry["files"])
    count, outputs = 0, []
    done = list(store.setting(PREFIX + value["id"]).get("download_done", []))
    for entry in plan["entries"]:
        outputs.append(str(Path(target) / entry["name"]))
        if entry["source"] not in done:
            receipt = store.setting(PREFIX + value["id"]).get("publishing", {})
            if entry["source"] not in receipt:
                for path in sorted(entry["folders"], key=lambda p: len(Path(p).parts)):
                    local.mkdir(stage_root, path)
                for path, row in entry["files"]:
                    update(store, value["id"], current=path)
                    try:
                        existing = checksum(
                            stage_root, path, lambda *_: progress(count, total)
                        )[0]
                    except FileNotFoundError:
                        existing = None
                    if existing is not None and existing != row["sha256"]:
                        raise ValueError(
                            tr("Zwischenablage der Kopie wurde verändert.")
                        )
                    if existing is None:
                        part = transport.download(
                            config,
                            stage_root,
                            row,
                            lambda n, _: progress(count + n, total),
                        )
                        local.install(stage_root, path, part, None)
                    count += row["size"]
                    progress(count, total)
            publish(store, value, destination, staging, entry["name"], entry["source"])
            done.append(entry["source"])
            update(store, value["id"], download_done=done)
        else:
            count += sum(row["size"] for _, row in entry["files"])
    return outputs


def execute(store, value, progress):
    from lumen_transfers import update, PREFIX

    config = lumen_connect.read_config()
    if sync.scope(config) != value["drive"]["scope"]:
        raise ValueError(
            tr(
                "Serververbindung geändert. Übertragung mit der ursprünglichen Verbindung fortsetzen."
            )
        )
    with transport.session(config):
        if value["action"] == "drive-upload":
            upload(store, value, config, value["sources"], progress)
        elif value["action"] == "drive-download":
            download(store, value, config, value["target"], progress)
        else:
            target = store.directory / ("drive-copy-" + value["id"])
            target.mkdir(mode=0o700, exist_ok=True)
            sources = download(store, value, config, str(target), progress)
            upload(store, store.setting(PREFIX + value["id"]), config, sources, progress)
    update(store, value["id"], done=value["sources"])
