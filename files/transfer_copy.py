"""Checked partial local copies, published only after the whole entry is ready."""

import os
from pathlib import Path
import shutil
import stat

import drive_local as local
from lumen_i18n import tr
from lumen_history import file_change


def root(path, native_names=False):
    path = Path(path).absolute()
    if path.resolve() != path:
        raise ValueError(tr("Übertragungsordner darf kein symbolischer Link sein."))
    info = path.stat()
    return dict(
        path=str(path), identity=[info.st_dev, info.st_ino], native_names=native_names
    )


def metadata(item, staged, portable):
    if portable:
        return
    for entry in reversed(item["entries"]):
        shutil.copystat(
            Path(item["root"]["path"]) / entry["path"],
            Path(staged["path"]) / entry["path"],
            follow_symlinks=False,
        )


def execute(store, value, progress):
    from lumen_transfers import update

    identity = value["id"]
    plan = value.get("copy_plan")
    if plan is None:
        destination = root(value["target"], True)
        items = []
        names = set()
        for source in value["sources"]:
            path = Path(source)
            if value.get("expected") is not None:
                from image_edit import file_stamp

                if file_stamp(path.lstat()) != value["expected"].get(source):
                    raise ValueError(
                        tr("Datei seit der Vorschau verändert. Bitte erneut prüfen.")
                    )
            from core import check_destination

            check_destination(path, Path(value["target"]) / path.name)
            if path.name in names:
                raise ValueError(tr("Mehrere Quellen haben denselben Namen."))
            names.add(path.name)
            origin = root(path.parent, True)
            pending = [path.name]
            entries = []
            while pending:
                name = pending.pop()
                with local.directory(origin, Path(name).parent) as parent:
                    info = os.stat(
                        Path(name).name, dir_fd=parent, follow_symlinks=False
                    )
                kind = (
                    "link"
                    if stat.S_ISLNK(info.st_mode)
                    else "dir"
                    if stat.S_ISDIR(info.st_mode)
                    else "file"
                )
                if kind == "file" and not stat.S_ISREG(info.st_mode):
                    raise ValueError(
                        tr("Nur reguläre Dateien und Ordner werden kopiert.")
                    )
                entries.append(
                    dict(
                        path=name,
                        kind=kind,
                        stamp=local.signature(info),
                        link=os.readlink(path.parent / name)
                        if kind == "link"
                        else None,
                    )
                )
                if kind == "dir":
                    with local.directory(origin, name) as fd:
                        pending.extend(
                            str(Path(name) / child)
                            for child in sorted(os.listdir(fd), reverse=True)
                        )
                if len(entries) % 100 == 0:
                    update(store, identity, current=source)
            items.append(dict(source=source, root=origin, entries=entries))
        plan = dict(root=destination, items=items, stage=".lumen-copy-" + identity)
        update(store, identity, copy_plan=plan)
    destination, staged = plan["root"], plan["stage"]
    local.mkdir(destination, staged)
    stage_root = root(Path(destination["path"]) / staged, True)
    if (
        value.get("stage_identity")
        and stage_root["identity"] != value["stage_identity"]
    ):
        raise ValueError(tr("Zwischenablage der Kopie wurde ersetzt."))
    update(store, identity, stage_identity=stage_root["identity"])
    total = sum(
        e["stamp"][2]
        for item in plan["items"]
        for e in item["entries"]
        if e["kind"] == "file"
    )
    count = 0
    done = list(value["done"])
    for item in plan["items"]:
        source = item["source"]
        name = Path(source).name
        if source in done:
            count += sum(e["stamp"][2] for e in item["entries"] if e["kind"] == "file")
            continue
        receipt = store.setting("workplace/transfer/" + identity).get("publishing", {})
        if source in receipt:
            pending = os.path.lexists(Path(stage_root["path"]) / name)
            info = (
                Path(stage_root["path"] if pending else destination["path"]) / name
            ).lstat()
            if [info.st_dev, info.st_ino] != receipt[source]:
                raise ValueError(tr("Zieldatei wurde inzwischen ersetzt."))
            if pending:
                metadata(item, stage_root, value["portable"])
                local.move(destination, staged + "/" + name, name)
            count += sum(e["stamp"][2] for e in item["entries"] if e["kind"] == "file")
        else:
            for entry in item["entries"]:
                relative = entry["path"]
                update(
                    store, identity, current=str(Path(item["root"]["path"]) / relative)
                )
                if entry["kind"] == "dir":
                    local.mkdir(stage_root, relative)
                elif entry["kind"] == "link":
                    with local.directory(stage_root, Path(relative).parent) as fd:
                        try:
                            os.symlink(entry["link"], Path(relative).name, dir_fd=fd)
                        except FileExistsError:
                            if (
                                os.readlink(Path(relative).name, dir_fd=fd)
                                != entry["link"]
                            ):
                                raise
                        os.fsync(fd)
                else:
                    with (
                        local.source(item["root"], relative) as reader,
                        local.directory(stage_root, Path(relative).parent) as parent,
                    ):
                        if local.signature(os.fstat(reader.fileno())) != entry["stamp"]:
                            raise ValueError(
                                tr(
                                    "Quelldatei wurde verändert. Bitte einen neuen Kopiervorgang starten."
                                )
                            )
                        fd = os.open(
                            Path(relative).name,
                            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                            0o600,
                            dir_fd=parent,
                        )
                        with os.fdopen(fd, "r+b") as writer:
                            if not stat.S_ISREG(os.fstat(writer.fileno()).st_mode):
                                raise ValueError(tr("Ungültige Teildatei."))
                            offset = os.fstat(writer.fileno()).st_size
                            if offset > entry["stamp"][2]:
                                raise ValueError(tr("Teildatei wurde verändert."))
                            checked = 0
                            while checked < offset:
                                chunk = reader.read(min(1024**2, offset - checked))
                                if not chunk or writer.read(len(chunk)) != chunk:
                                    raise ValueError(tr("Teildatei wurde verändert."))
                                checked += len(chunk)
                                progress(count + checked, total)
                            local.capacity(destination, entry["stamp"][2] - offset)
                            while chunk := reader.read(1024**2):
                                writer.write(chunk)
                                checked += len(chunk)
                                progress(count + checked, total)
                            writer.flush()
                            os.fsync(writer.fileno())
                            os.fsync(parent)
                            if (
                                local.signature(os.fstat(reader.fileno()))
                                != entry["stamp"]
                            ):
                                raise ValueError(
                                    tr(
                                        "Quelldatei wurde während des Kopierens verändert."
                                    )
                                )
                            count += checked
            info = (Path(stage_root["path"]) / name).lstat()
            receipt[source] = [info.st_dev, info.st_ino]
            update(store, identity, publishing=receipt)
            metadata(item, stage_root, value["portable"])
            local.move(destination, staged + "/" + name, name)
        done.append(source)
        update(store, identity, done=done, bytes=count, total=total)
        file_change(store, "copy", source, str(Path(destination["path"]) / name))
    update(store, identity, transfer_done=True)
    local.remove_empty(destination, staged)
