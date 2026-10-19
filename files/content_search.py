"""Local, bounded content search. The CLI runs in its own cancellable process group."""
from lumen_i18n import tr
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
import zlib
from xml.etree import ElementTree as ET
from collections import deque
from pathlib import Path


MAX_TEXT = 1024 * 1024
STOP_WORDS = set(('der die das den dem des ein eine einen einem einer eines für fuer von vom zum zur zu '
                  'und oder mit ohne im in auf am an aus bei nach über ueber unter ich du mir mich mein '
                  'meine meinen meinem meiner meines bitte suche suchen finde finden zeige zeigen wo ist '
                  'sind liegt liegen habe haben hast hat hatte wurde wurden es sich welche welcher welches '
                  'datei dateien dokument dokumente the a an for of with and or in on my me find show is are').split())


def query_groups(query):
    groups = []
    for phrase, word in re.findall(r'"([^"]+)"|(\w+)', query.lower()):
        if phrase:
            term = phrase.strip()
        else:
            if word in STOP_WORDS or len(word) < 2:
                continue
            term = word
            # ponytail: common German inflections, not a language model; Lumen adds synonyms.
            if len(term) > 6:
                for suffix in ('en', 'er', 'e', 's'):
                    if term.endswith(suffix):
                        term = term[:-len(suffix)]
                        break
        if [term] not in groups:
            groups.append([term])
    if not groups or len(groups) > 8:
        raise ValueError(tr('Bitte 1 bis 8 aussagekräftige Suchbegriffe eingeben.'))
    return groups


def parse_groups(text):
    text = text.strip()
    if text.startswith('```') and text.endswith('```'):
        text = '\n'.join(text.splitlines()[1:-1])
    try:
        groups = json.loads(text)['groups']
        if not isinstance(groups, list) or not 1 <= len(groups) <= 8:
            raise ValueError()
        for group in groups:
            if not isinstance(group, list) or not 1 <= len(group) <= 6:
                raise ValueError()
            for term in group:
                if (not isinstance(term, str) or not 2 <= len(term) <= 80 or
                        not re.fullmatch(r'[\w][\w .+\-]*', term)):
                    raise ValueError()
        return [[term.lower().strip() for term in group] for group in groups]
    except (ValueError, TypeError, KeyError):
        raise ValueError(tr('Lumen hat keine gültigen Suchbegriffe geliefert. Die lokale Suche bleibt verfügbar.')) from None


def find_passage(text, groups):
    matches = []
    for group in groups:
        alternatives = [re.escape(term).replace(r'\ ', r'\s+') for term in group]
        match = re.search(r'(?<!\w)(?:' + '|'.join(alternatives) + r')\w*', text, re.IGNORECASE)
        if not match:
            return None
        matches.append(match)
    anchor = max(matches, key=lambda match: match.start())
    page_end = text.find('\f', anchor.end())
    start = max(text.rfind('\f', 0, anchor.start()) + 1, anchor.start() - 100)
    end = min(page_end if page_end >= 0 else len(text), anchor.end() + 220)
    # Keep the literal passage; line/page positions refer to the original extracted text.
    return {'snippet': text[start:end].strip(), 'page': text.count('\f', 0, anchor.start()) + 1,
            'line': text.count('\n', 0, anchor.start()) + 1}


def read_content(path, directory_fd=None):
    path = Path(path)
    target = path.name if directory_fd is not None else path
    fd = os.open(target, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory_fd)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            return '', False
        partial = False
        from document_text import EXTENSIONS, extract
        if path.suffix.lower() in EXTENSIONS:
            if info.st_size > 64 * 1024 * 1024:
                raise ValueError(tr('Office-Datei zu groß.'))
            try:
                text, partial = extract(stream, path.suffix.lower(), MAX_TEXT)
                data = text.encode('utf-8')
            except (KeyError, IndexError, zipfile.BadZipFile, ET.ParseError, RuntimeError, zlib.error) as error:
                raise ValueError(tr('Office-Datei nicht lesbar.')) from error
        elif path.suffix.lower() == '.pdf':
            if info.st_size > 128 * 1024 * 1024:
                return '', True
            with tempfile.TemporaryFile() as output:
                # An inherited descriptor pins the checked file, even if its path changes.
                proc = subprocess.Popen([sys.executable,str(Path(__file__).with_name('lumen_pdf_worker.py')),'text',
                                         f'/proc/self/fd/{stream.fileno()}', '--limit',str(MAX_TEXT+1)],
                                        stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.DEVNULL,
                                        pass_fds=(stream.fileno(),))
                deadline = time.monotonic() + 12
                try:
                    while proc.poll() is None:
                        if os.fstat(output.fileno()).st_size > MAX_TEXT or time.monotonic() > deadline:
                            partial = True
                            proc.kill()
                            break
                        time.sleep(.02)
                    proc.wait()
                    if proc.returncode and not partial and os.fstat(output.fileno()).st_size <= MAX_TEXT:
                        raise ValueError(tr('PDF nicht lesbar.'))
                    output.seek(0)
                    data = output.read(MAX_TEXT + 1)
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait()
        else:
            data = stream.read(MAX_TEXT + 1)
        def signature(value):
            return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns
        current = os.stat(target, dir_fd=directory_fd, follow_symlinks=False)
        if signature(info) != signature(current) or signature(info) != signature(os.fstat(stream.fileno())):
            raise ValueError(tr('Datei während der Suche verändert.'))
        partial = partial or len(data) > MAX_TEXT
        data = data[:MAX_TEXT]
        if data.startswith((b'\xff\xfe', b'\xfe\xff')):
            return data.decode('utf-16', errors='replace'), partial
        if b'\0' in data or (data and sum(byte < 9 or 13 < byte < 32 for byte in data) / len(data) > .03):
            return '', partial
        return data.decode('utf-8-sig', errors='replace'), partial


def folder_fd(root_fd, relative):
    """Open every component relative to the pinned root, refusing replaced symlinks."""
    current = os.dup(root_fd)
    try:
        for part in relative.parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            os.close(current)
            current = child
        return current
    except OSError:
        os.close(current)
        raise


def scan(root, groups, hidden=False, max_hits=500, max_entries=100000, ocr=False, thumbnail_dir=None):
    root = Path(root).resolve()
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        yield from scan_tree(root, root_fd, groups, hidden, max_hits, max_entries, ocr, thumbnail_dir)
    finally:
        os.close(root_fd)


def scan_tree(root, root_fd, groups, hidden, max_hits, max_entries, ocr=False, thumbnail_dir=None, visual=True):
    from core import file_kind
    from document_text import EXTENSIONS
    root = Path(root).resolve()
    queue = deque([Path('.')])
    visited = scanned = hits = errors = partial = empty = 0
    error_details = []
    limit = ''; images = 0
    started = last_report = time.monotonic()
    while queue and not limit:
        relative = queue.popleft()
        folder = root / relative
        descriptor = None
        try:
            descriptor = folder_fd(root_fd, relative)
            with os.scandir(descriptor) as entries:
                for entry in entries:
                    path = folder / entry.name
                    if not hidden and entry.name.startswith('.'):
                        continue
                    if visited >= max_entries:
                        limit = tr('Eintragslimit')
                        break
                    visited += 1
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            queue.append(relative / entry.name)
                        elif entry.is_file(follow_symlinks=False) and (file_kind(path) in {'text', 'pdf', 'image'} or path.suffix.lower() in EXTENSIONS):
                            scanned += 1
                            kind = file_kind(path)
                            text, incomplete = read_content(path, descriptor) if kind != 'image' else ('', False)
                            if visual and kind in {'image', 'pdf'}:
                                from lumen_ocr import visual_content
                                text, cut, image = visual_content(path, descriptor, text, ocr, thumbnail_dir if images < 100 else None)
                                incomplete = incomplete or cut
                                if image:
                                    images += 1
                                    yield dict(image, type='image')
                            partial += int(incomplete)
                            empty += int(not text.strip())
                            passage = find_passage(text, groups) if text else None
                            if passage:
                                hits += 1
                                yield dict(passage, type='hit', path=str(path), partial=incomplete,
                                           pdf=path.suffix.lower() == '.pdf', image=kind == 'image')
                                if hits >= max_hits:
                                    limit = tr('Trefferlimit')
                                    break
                    except (OSError, ValueError, subprocess.SubprocessError) as error:
                        errors += 1
                        if len(error_details) < 12:
                            error_details.append(dict(path=str(path), error=str(error)[:200]))
                    if time.monotonic() - last_report > .15:
                        yield {'type': 'progress', 'scanned': scanned, 'visited': visited, 'hits': hits}
                        last_report = time.monotonic()
        except OSError as error:
            errors += 1
            if len(error_details) < 12:
                error_details.append(dict(path=str(folder), error=str(error)[:200]))
        finally:
            if descriptor is not None:
                os.close(descriptor)
    yield {'type': 'done', 'scanned': scanned, 'visited': visited, 'hits': hits, 'errors': errors,
           'partial': partial, 'empty': empty, 'limit': limit, 'error_details': error_details, 'elapsed': time.monotonic() - started}


if __name__ == '__main__' and sys.argv[1:] == ['--scan']:
    import resource
    os.setsid()
    resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 * MAX_TEXT, 32 * MAX_TEXT))
    try:
        request = json.loads(sys.stdin.buffer.readline(16384))
        groups = parse_groups(json.dumps({'groups': request['groups']}))
        for event in scan(request['root'], groups, bool(request.get('hidden')), ocr=bool(request.get('ocr')), thumbnail_dir=request.get('thumbnail_dir')):
            print(json.dumps(event, ensure_ascii=True), flush=True)
    except Exception as exc:
        print(json.dumps({'type': 'error', 'message': str(exc)}), flush=True)
        sys.exit(1)
