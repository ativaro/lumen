"""Checked partial local copies, published only after the whole entry is ready."""

import os
from pathlib import Path
import shutil
import stat
import time

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


def verify_move(item, destination, source_name, renamed, current):
    """Check the complete tree and bytes before removing a copied source."""
    name = Path(item['source']).name
    children = {e['path']: set() for e in item['entries'] if e['kind'] == 'dir'}
    for entry in item['entries'][1:]:
        children[str(Path(entry['path']).parent)].add(Path(entry['path']).name)
    for entry in item['entries']:
        path = entry['path']
        source_path = str(Path(source_name) / Path(path).relative_to(name))
        current(Path(item['root']['path']) / source_path)
        with local.directory(item['root'], Path(source_path).parent) as parent:
            info = os.stat(Path(source_path).name, dir_fd=parent, follow_symlinks=False)
        signature = local.signature(info)
        expected = entry['stamp']
        if (signature[:4] != expected[:4] or
                (not renamed or path != name) and signature != expected or
                entry.get('mode', info.st_mode) != info.st_mode):
            raise ValueError(tr('Quelle wurde verändert. Beide Fassungen bleiben erhalten.'))
        with local.directory(destination, Path(path).parent) as parent:
            target = os.stat(Path(path).name, dir_fd=parent, follow_symlinks=False)
        if entry['kind'] == 'dir':
            if not stat.S_ISDIR(info.st_mode) or not stat.S_ISDIR(target.st_mode):
                raise ValueError(tr('Ordner wurde ersetzt.'))
            with local.directory(item['root'], source_path) as fd:
                if set(os.listdir(fd)) != children[path]:
                    raise ValueError(tr('Quelle enthält inzwischen andere Einträge.'))
            with local.directory(destination, path) as fd:
                if set(os.listdir(fd)) != children[path]:
                    raise ValueError(tr('Ziel enthält inzwischen andere Einträge.'))
        elif entry['kind'] == 'link':
            if not stat.S_ISLNK(info.st_mode) or not stat.S_ISLNK(target.st_mode):
                raise ValueError(tr('Verknüpfung wurde ersetzt.'))
            for folder, relative in ((item['root'], source_path), (destination, path)):
                with local.directory(folder, Path(relative).parent) as fd:
                    if os.readlink(Path(relative).name, dir_fd=fd) != entry['link']:
                        raise ValueError(tr('Verknüpfung wurde verändert.'))
        else:
            if not stat.S_ISREG(info.st_mode) or not stat.S_ISREG(target.st_mode):
                raise ValueError(tr('Nur reguläre Dateien und Ordner werden kopiert.'))
            if not renamed:
                continue  # Verify bytes once, after the source is held for recoverable disposal.
            with local.source(item['root'], source_path) as reader, local.source(destination, path) as copied:
                target_stamp = local.signature(os.fstat(copied.fileno()))
                while chunk := reader.read(1024**2):
                    if copied.read(len(chunk)) != chunk:
                        raise ValueError(tr('Quell- und Zieldatei stimmen nicht überein.'))
                    current(Path(item['root']['path']) / source_path)
                if (copied.read(1) or local.signature(os.fstat(reader.fileno())) != signature or
                        local.signature(os.fstat(copied.fileno())) != target_stamp):
                    raise ValueError(tr('Datei wurde während der Prüfung verändert.'))


def restore_source(item, quarantine):
    origin, source = item['root'], item['source']
    held = Path(origin['path']) / quarantine
    if not os.path.lexists(held):
        return
    with local.directory(origin):
        if (os.path.lexists(source) or
                local.signature(held.lstat())[:2] != item['entries'][0]['stamp'][:2]):
            raise ValueError(tr('Quelle zur Wiederherstellung prüfen: {0}', str(held)))
        local.move(origin, quarantine, Path(source).name)


def retire_source(store, value, item, destination, index, current):
    from gi.repository import Gio
    from lumen_transfers import PREFIX, update

    identity, source = value['id'], item['source']
    origin, name = item['root'], Path(source).name
    ticket = store.setting(PREFIX + identity)
    moving = dict(ticket.get('moving', {}))
    quarantine = moving.get(source, '.lumen-move-' + identity + '-' + str(index))
    held = Path(origin['path']) / quarantine
    try:
        if ticket['cancel']:
            raise ValueError(tr('Angehalten.'))
        if os.path.lexists(held):
            if source not in moving or os.path.lexists(source):
                raise ValueError(tr('Quellordner wurde inzwischen neu belegt.'))
        elif os.path.lexists(source):
            verify_move(item, destination, name, source in moving, current)
            moving[source] = quarantine
            update(store, identity, moving=moving)
            local.move(origin, name, quarantine)
        elif source in moving:
            return  # Trash succeeded before the completed-source checkpoint.
        else:
            raise ValueError(tr('Quelle ist nicht mehr erreichbar.'))
        verify_move(item, destination, quarantine, True, current)
        # Trash retains late writes/open handles; never recursively delete source data.
        if store.setting(PREFIX + identity)['cancel']:
            raise ValueError(tr('Angehalten.'))
        with local.directory(origin):
            if not Gio.File.new_for_path(str(held)).trash(None):
                raise OSError(tr('Quelle konnte nicht in den Papierkorb verschoben werden.'))
    except Exception as error:
        try:
            restore_source(item, quarantine)
        except (OSError, ValueError):
            pass
        remaining = str(held) if os.path.lexists(held) else source
        raise ValueError(tr('Verschieben angehalten. Quelle unter {0}, Kopie unter {1}. Nach Prüfung fortsetzen.',
                            remaining, str(Path(destination['path']) / name)) + ': ' + str(error)) from error


def execute(store, value, progress):
    from lumen_transfers import update

    identity = value["id"]
    last_current = float('-inf')
    def current(path):
        nonlocal last_current
        now = time.monotonic()
        if now - last_current >= .3:
            update(store, identity, current=str(path))
            last_current = now

    plan = value.get("copy_plan")
    if plan is None:
        destination = root(value["target"], True)
        items = []
        names = set()
        for source in value["sources"]:
            if source in value['done']:
                continue
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
                        mode=info.st_mode,
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
                    current(source)
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
    for index, item in enumerate(plan["items"]):
        source = item["source"]
        name = Path(source).name
        if source in done:
            count += sum(e["stamp"][2] for e in item["entries"] if e["kind"] == "file")
            continue
        receipt = store.setting("transfer/" + identity).get("publishing", {})
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
                current(Path(item["root"]["path"]) / relative)
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
        if value['action'] == 'move':
            retire_source(store, value, item, destination, index, current)
        done.append(source)
        update(store, identity, done=done, bytes=count, total=total)
        file_change(store, value['action'], source, str(Path(destination["path"]) / name),
                    undoable=value['action'] != 'move')
    update(store, identity, transfer_done=True)
    local.remove_empty(destination, staged)
