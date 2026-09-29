"""Local search and filesystem operations; no shell or permanent deletion."""
import mimetypes
import os
import shutil
import tempfile
import threading
import time
from collections import deque
from pathlib import Path

from gi.repository import Gio
from PyQt5.QtCore import QThread, pyqtSignal

TEXT_EXTENSIONS = {'.md', '.py', '.js', '.ts', '.tsx', '.jsx', '.json', '.yaml', '.yml',
                   '.toml', '.ini', '.conf', '.sh', '.log', '.rs', '.c', '.cpp', '.h',
                   '.css', '.html', '.xml', '.csv', '.tex', '.sql', '.srt', '.svg'}


def file_kind(path):
    suffix = Path(path).suffix.lower()
    mime = mimetypes.guess_type(str(path))[0] or ''
    if mime.startswith('image/'):
        return 'image'
    if suffix == '.pdf':
        return 'pdf'
    if mime.startswith('video/'):
        return 'video'
    if mime.startswith('audio/'):
        return 'audio'
    if mime.startswith('text/') or suffix in TEXT_EXTENSIONS:
        return 'text'
    return 'other'


def size_text(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024 or unit == 'TB':
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024


def valid_name(name):
    if not name or name in {'.', '..'} or '/' in name or '\x00' in name:
        raise ValueError('Bitte einen gültigen Namen ohne / eingeben.')
    return name


def search_paths(root, query, hidden, stop, progress=None):
    """Breadth-first filename search. Symlink directories are never traversed."""
    # ponytail: O(n) live scan; use a local index if very large trees become slow.
    terms = query.casefold().split()
    queue = deque([Path(root)])
    visited = errors = 0
    last_report = time.monotonic()
    while queue and not stop.is_set():
        folder = queue.popleft()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if stop.is_set():
                        return
                    if not hidden and entry.name.startswith('.'):
                        continue
                    visited += 1
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            queue.append(Path(entry.path))
                        if all(term in entry.name.casefold() for term in terms):
                            yield Path(entry.path)
                    except OSError:
                        errors += 1
                    if progress and time.monotonic() - last_report > .15:
                        progress(visited, errors)
                        last_report = time.monotonic()
        except OSError:
            errors += 1
    if progress:
        progress(visited, errors)


def check_destination(source, destination):
    if os.path.lexists(destination):
        raise FileExistsError(f'„{destination.name}“ existiert bereits. Nichts überschrieben.')
    if source.is_dir() and not source.is_symlink():
        if destination.resolve().is_relative_to(source.resolve()):
            raise ValueError('Ein Ordner kann nicht in sich selbst kopiert oder verschoben werden.')


def move_entry(source, destination, atomic=False):
    source, destination = Path(source), Path(destination)
    check_destination(source, destination)
    flags = Gio.FileCopyFlags.NOFOLLOW_SYMLINKS
    if atomic:
        flags |= Gio.FileCopyFlags.NO_FALLBACK_FOR_MOVE
    Gio.File.new_for_path(str(source)).move(
        Gio.File.new_for_path(str(destination)), flags, None, None)
    return destination


def copy_portable(source, destination):
    """Copy content without POSIX metadata that WebDAV/SMB may reject."""
    # ponytail: server-default metadata; add per-protocol preservation if needed.
    if source.is_symlink():
        destination.symlink_to(os.readlink(source))
    elif source.is_dir():
        destination.mkdir()
        for child in source.iterdir():
            copy_portable(child, destination / child.name)
    else:
        shutil.copyfile(source, destination, follow_symlinks=False)


def copy_entry(source, target_dir, portable=False):
    source, target_dir = Path(source), Path(target_dir)
    destination = target_dir / source.name
    check_destination(source, destination)
    # Stage on the destination volume: failures never expose an incomplete final copy.
    with tempfile.TemporaryDirectory(prefix='.lumen-copy-', dir=target_dir) as temp:
        staged = Path(temp) / source.name
        if portable:
            copy_portable(source, staged)
        elif source.is_dir() and not source.is_symlink():
            shutil.copytree(source, staged, symlinks=True)
        else:
            shutil.copy2(source, staged, follow_symlinks=False)
        move_entry(staged, destination)
    return destination


class SearchWorker(QThread):
    batch = pyqtSignal(list)
    progress = pyqtSignal(int, int)
    summary = pyqtSignal(int, bool, float)

    def __init__(self, root, query, hidden, limit=5000):
        super().__init__()
        self.root, self.query, self.hidden = root, query, hidden
        self.limit = max(100, min(50000, int(limit)))
        self.stop = threading.Event()

    def run(self):
        start = time.monotonic()
        batch, count, last = [], 0, start
        for path in search_paths(self.root, self.query, self.hidden, self.stop, self.progress.emit):
            batch.append(str(path))
            count += 1
            if len(batch) >= 40 or time.monotonic() - last > .06:
                self.batch.emit(batch)
                batch, last = [], time.monotonic()
            if count >= self.limit:
                break
        if batch:
            self.batch.emit(batch)
        self.summary.emit(count, count >= self.limit, time.monotonic() - start)


class FileWorker(QThread):
    progress = pyqtSignal(str)
    completed = pyqtSignal(list, list)

    def __init__(self, action, sources, target=None, portable=False):
        super().__init__()
        self.action, self.sources, self.target = action, sources, target
        self.portable = portable

    def run(self):
        done, errors = [], []
        for source in self.sources:
            path = Path(source)
            self.progress.emit(path.name)
            try:
                if self.action == 'copy':
                    copy_entry(path, self.target, self.portable)
                elif self.action == 'move':
                    move_entry(path, Path(self.target) / path.name)
                elif self.action == 'rename':
                    move_entry(path, self.target)
                elif self.action == 'mkdir':
                    path.mkdir()
                elif self.action == 'trash':
                    Gio.File.new_for_path(str(path)).trash(None)
                done.append(source)
            except Exception as exc:
                errors.append(f'{path.name}: {exc}')
        self.completed.emit(done, errors)
