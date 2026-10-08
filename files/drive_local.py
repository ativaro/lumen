"""Linux directory-FD operations for Drive; replaced bytes stay in local history."""

from contextlib import contextmanager
from pathlib import Path
import ctypes
import errno
import hashlib
import os
import stat
from uuid import uuid4
from lumen_i18n import tr

LIMIT = 64 * 1024**2


def relative(value):
    p = Path(value)
    if (
        p.is_absolute()
        or ".." in p.parts
        or any(
            len(part) > 200
            or part != part.strip()
            or "\\" in part
            or any(ord(c) < 32 for c in part)
            for part in p.parts
        )
    ):
        raise ValueError(tr("Ungültiger Drive-Pfad."))
    return p


@contextmanager
def directory(root, path="."):
    fd = os.open(root["path"], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if [st.st_dev, st.st_ino] != root["identity"]:
            raise ValueError(tr("Drive-Ordner wurde ersetzt oder ist nicht verbunden."))
        for part in relative(path).parts:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def signature(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


@contextmanager
def source(root, path):
    p = relative(path)
    with directory(root, p.parent) as fd:
        handle = os.open(p.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(handle, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(tr("Keine reguläre Drive-Datei."))
            if info.st_size > LIMIT:
                raise ValueError(tr("Maximal 64 MB pro Datei."))
            yield stream


def checksum(root, path):
    try:
        with source(root, path) as stream:
            before = signature(os.fstat(stream.fileno()))
            value = hashlib.file_digest(stream, "sha256").hexdigest()
            if signature(os.fstat(stream.fileno())) != before:
                raise ValueError(tr("Datei während des Lesens verändert."))
            return value
    except FileNotFoundError:
        return None


def scan(root, cache=None):
    cache = cache or {}
    files = {}
    folders = {}
    errors = []

    def fail(error):
        raise error

    with directory(root) as fd:
        # A nested mount can disappear independently. Select it as its own sync root.
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            mount = (
                line.split()[4]
                .replace("\\040", " ")
                .replace("\\011", "\t")
                .replace("\\134", "\\")
            )
            if mount != root["path"] and Path(mount).is_relative_to(root["path"]):
                raise ValueError(
                    tr("Eingehängte Unterordner bitte getrennt synchronisieren.")
                )
        for path, dirs, names, parent in os.fwalk(
            ".", dir_fd=fd, follow_symlinks=False, onerror=fail
        ):
            if path == "." and ".lumen-drive" in dirs:
                dirs.remove(".lumen-drive")
            for name in dirs + names:
                if len(files) + len(folders) >= 10000:
                    raise ValueError(tr("Maximal 10.000 Einträge pro Drive-Ordner."))
                item = str(relative(Path(path) / name))
                info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    raise ValueError(
                        tr("Symbolische Verknüpfungen nicht synchronisieren: ") + item
                    )
                if info.st_dev != root["identity"][0]:
                    raise ValueError(
                        tr("Unterordner liegt auf einem anderen Datenträger.")
                    )
                if stat.S_ISDIR(info.st_mode):
                    folders[item] = dict(signature=signature(info))
                    continue
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError(tr("Keine reguläre Datei: ") + item)
                sig = signature(info)
                old = cache.get(item, {})
                blocked = info.st_size > LIMIT or Path(name).suffix.lower() == ".kdbx"
                value = (
                    None
                    if blocked
                    else old.get("hash")
                    if old.get("signature") == sig
                    else checksum(root, item)
                )
                files[item] = dict(signature=sig, hash=value, blocked=blocked)
                if blocked:
                    errors.append(
                        item
                        + tr(" · Nicht synchronisiert (Dateigrenze oder Tresordatei)")
                    )
                if len(files) + len(folders) > 10000:
                    raise ValueError(tr("Maximal 10.000 Einträge pro Drive-Ordner."))
    return files, folders, errors


def mkdir(root, path):
    p = relative(path)
    with directory(root, p.parent) as fd:
        try:
            os.mkdir(p.name, 0o700, dir_fd=fd)
        except FileExistsError:
            with directory(root, p):
                pass
        os.fsync(fd)


def move(root, old, new):
    """renameat2 prevents overwriting a file created between scan and commit."""
    a, b = relative(old), relative(new)
    with directory(root, a.parent) as src, directory(root, b.parent) as dst:
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.renameat2(src, os.fsencode(a.name), dst, os.fsencode(b.name), 1):
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), str(b))
        os.fsync(src)
        os.fsync(dst)


def capacity(root, needed):
    with directory(root) as fd:
        free = os.fstatvfs(fd)
        if free.f_bavail * free.f_frsize < needed + 64 * 1024**2:
            raise ValueError(tr("Zu wenig lokaler Speicher. Drive-Abgleich pausiert."))


def install(root, path, staged, expected):
    if checksum(root, path) != expected:
        raise ValueError(tr("Lokale Datei inzwischen geändert."))
    if expected is not None:
        mkdir(root, ".lumen-drive")
        mkdir(root, ".lumen-drive/history")
        saved = ".lumen-drive/history/" + uuid4().hex + "-" + Path(path).name[:100]
        move(root, path, saved)
        if checksum(root, saved) != expected:
            try:
                move(root, saved, path)
            except OSError:
                pass
            raise ValueError(
                tr("Lokale Änderung bleibt in der Drive-Wiederherstellung erhalten.")
            )
    if staged is not None:
        move(root, staged, path)


def remove_empty(root, path):
    p = relative(path)
    with directory(root, p.parent) as fd:
        try:
            os.rmdir(p.name, dir_fd=fd)
        except FileNotFoundError:
            pass
        except OSError as error:
            if error.errno in (errno.ENOTEMPTY, errno.EEXIST):
                raise ValueError(tr("Lokaler Ordner enthält noch Dateien.")) from None
            raise
        os.fsync(fd)
