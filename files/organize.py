"""Bounded proposal context and reversible, no-overwrite file moves."""
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

from core import file_kind, move_entry, valid_name


def stamp(path):
    info = Path(path).lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('Nur reguläre Dateien; keine Ordner oder Verknüpfungen.')
    # ctime changes on rename; these fields also identify a move after interrupted journaling.
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]


def within_root(path, root):
    path, root = Path(path), Path(root)
    if not path.is_absolute() or not path.is_relative_to(root) or '..' in path.parts:
        raise ValueError('Das Ziel muss innerhalb des ausgewählten Ordners liegen.')
    if path.parent.resolve() != path.parent or path.is_symlink():
        raise ValueError('Pfade über Verknüpfungen sind nicht erlaubt.')


def snapshot(paths, root):
    root = Path(root).resolve()
    if not 1 <= len(paths) <= 100:
        raise ValueError('Bitte zwischen 1 und 100 Dateien auswählen.')
    items = []
    for path in dict.fromkeys(map(str, paths)):
        source = Path(path).absolute()
        within_root(source, root)
        items.append({'id': len(items), 'source': str(source), 'name': source.name,
                      'relative': str(source.relative_to(root)), 'stamp': stamp(source)})
    return items


def proposal_context(items, temp, stopped=lambda: False):
    """Use the existing isolated preview decoder; no tools are delegated to the model."""
    records, attachments = [], []
    for item in items:
        if stopped():
            raise ValueError('Abgebrochen. Keine Dateien verändert.')
        path = Path(item['source'])
        if stamp(path) != item['stamp']:
            raise ValueError(f'{path.name}: Datei inzwischen verändert. Bitte neu öffnen.')
        record = {'id': item['id'], 'path': item['relative'], 'size': item['stamp'][2]}
        kind = file_kind(path)
        output = Path(temp) / f"{item['id']}.png"
        try:
            if kind == 'pdf':
                text_file = Path(temp) / f"{item['id']}.txt"
                subprocess.run(['pdftotext', '-f', '1', '-l', '3', '-layout', str(path), str(text_file)],
                               capture_output=True, timeout=12, check=True)
                with text_file.open('rb') as stream:
                    record['excerpt'] = stream.read(4096).decode('utf-8', errors='replace')
            elif kind == 'text' or (kind == 'image' and len(attachments) < 12):
                result = subprocess.run(['/usr/bin/python3', str(Path(__file__).with_name('preview.py')),
                                         '--data', str(path), str(output), '1024'],
                                        capture_output=True, timeout=12, check=True)
                data = json.loads(result.stdout)
                if data['kind'] == 'image':
                    attachments.append((str(output), 'image/png'))
                    record['image'] = output.name
                elif data['kind'] == 'text':
                    record['excerpt'] = data['text'][:4096]
        except (OSError, ValueError, subprocess.SubprocessError):
            record['note'] = 'Inhalt nicht lesbar; nur Dateiname und Metadaten verwenden.'
        if not record.get('excerpt') and not record.get('image'):
            record.setdefault('note', 'Nur Dateiname und Metadaten verfügbar.')
        records.append(record)
    # ponytail: bounded batches (100 files / 12 images); chunking belongs here if needed.
    return records, attachments


def parse_proposal(text, items):
    text = text.strip()
    if text.startswith('```') and text.endswith('```'):
        text = '\n'.join(text.splitlines()[1:-1])
    try:
        rows = json.loads(text)['changes']
        if not isinstance(rows, list) or not 1 <= len(rows) <= len(items):
            raise ValueError()
        seen = set()
        for row in rows:
            index = row['id']
            if type(index) is not int or index in seen or not 0 <= index < len(items):
                raise ValueError()
            if not isinstance(row['target'], str) or not isinstance(row.get('reason', ''), str):
                raise ValueError()
            seen.add(index)
        return rows
    except (ValueError, KeyError, TypeError):
        raise ValueError('Keine gültigen Vorschläge erhalten. Bitte erneut versuchen.') from None


def validate_move(move):
    source, destination, root = (Path(move[key]) for key in ('source', 'destination', 'root'))
    within_root(source, root)
    within_root(destination, root)
    if stamp(source) != move['stamp']:
        raise ValueError('Datei inzwischen verändert. Bitte neue Vorschläge erstellen.')
    if source == destination:
        raise ValueError('Unverändert')
    if os.path.lexists(destination):
        raise ValueError('Ziel existiert bereits. Nichts überschrieben.')
    parent = destination.parent
    while not parent.exists():
        parent = parent.parent
    if not parent.is_dir() or parent.stat().st_dev != move['stamp'][0]:
        raise ValueError('Das Ziel muss ein Ordner auf demselben Dateisystem sein.')


def validate_moves(items, rows, root, mode):
    root = Path(root).resolve()
    moves, errors, targets = [], {}, {}
    for row in rows:
        index, target = row['id'], row['target']
        try:
            source = Path(items[index]['source'])
            if (not target or len(target) > 4096 or target.startswith('/') or
                    any(ord(char) < 32 or ord(char) == 127 for char in target)):
                raise ValueError('Bitte einen gültigen Namen eingeben.')
            for part in target.split('/'):
                valid_name(part)
            if mode == 'rename':
                valid_name(target)
                destination = source.with_name(target)
                if destination.suffix != source.suffix:
                    raise ValueError('Die Dateiendung muss erhalten bleiben.')
            elif mode == 'sort':
                destination = root / target
                if destination.name != source.name:
                    raise ValueError('Beim Sortieren bleibt der Dateiname erhalten.')
            else:
                raise ValueError('Unbekannte Dateiaktion.')
            conflicts = [key for path, key in targets.items()
                         if destination.is_relative_to(path) or path.is_relative_to(destination)]
            if conflicts:
                for key in conflicts:
                    errors[key] = 'Ziele überschneiden sich oder sind doppelt belegt.'
                raise ValueError('Ziele überschneiden sich oder sind doppelt belegt.')
            targets[destination] = index
            move = {'id': index, 'source': str(source), 'destination': str(destination),
                    'root': str(root), 'stamp': items[index]['stamp']}
            validate_move(move)
            moves.append(move)
        except (OSError, ValueError) as exc:
            errors[index] = str(exc)
    return moves, errors


def sync_directory(path):
    directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def save_journal(path, moves):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.lumen-undo-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(moves, stream, ensure_ascii=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load_journal(path):
    try:
        with Path(path).open() as stream:
            moves = json.load(stream)
        if not isinstance(moves, list) or len(moves) > 100:
            raise ValueError('Ungültiges Rückgängig-Protokoll.')
        for move in moves:
            if not isinstance(move, dict) or not all(key in move for key in ('source', 'destination', 'root', 'stamp')):
                raise ValueError('Ungültiges Rückgängig-Protokoll.')
            for key in ('source', 'destination'):
                within_root(move[key], move['root'])
        return moves
    except FileNotFoundError:
        return []


def apply_moves(moves, journal, stopped=lambda: False, progress=lambda *_: None):
    done, errors = [], []
    try:
        for move in moves:
            validate_move(move)
        if stopped():
            return [], ['Abgebrochen. Keine Dateien verändert.']
        # Persist intent BEFORE any mutation so undo can recover interrupted batches.
        save_journal(journal, moves)
        for move in moves:
            if stopped():
                errors.append('Abgebrochen. Bereits geänderte Dateien können rückgängig gemacht werden.')
                break
            validate_move(move)
            Path(move['destination']).parent.mkdir(parents=True, exist_ok=True)
            move_entry(move['source'], move['destination'], atomic=True)
            done.append(move)
            progress(len(done), Path(move['destination']).name)
    except Exception as exc:
        errors.append(str(exc))
    return done, errors


def undo_moves(journal, stopped=lambda: False, progress=lambda *_: None):
    done, errors = [], []
    moves = load_journal(journal)
    remaining = list(moves)
    for move in reversed(moves):
        if stopped():
            errors.append('Rückgängig abgebrochen; verbleibende Änderungen bleiben im Protokoll.')
            break
        try:
            source, destination = Path(move['source']), Path(move['destination'])
            if os.path.lexists(source) and stamp(source) == move['stamp']:
                # Never applied, or already restored before an interruption.
                pass
            else:
                reverse = dict(move, source=str(destination), destination=str(source))
                validate_move(reverse)
                move_entry(destination, source, atomic=True)
                done.append(move)
                progress(len(done), source.name)
            # Persist restored names BEFORE removing recovery intent, including retries
            # after a rename succeeded but a previous sync/journal write failed.
            for parent in {source.parent, destination.parent}:
                if parent.exists():
                    sync_directory(parent)
            remaining.remove(move)
        except Exception as exc:
            errors.append(f"{Path(move['source']).name}: {exc}")
    save_journal(journal, remaining)
    return done, errors
