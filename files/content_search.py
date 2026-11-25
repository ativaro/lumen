"""Local, bounded content search. The CLI runs in its own cancellable process group."""
from lumen_i18n import tr
import json
import os
import re
import subprocess
import sys
from pathlib import Path


MAX_TEXT = 1024 * 1024
OFFICE = {'.docx', '.docm', '.xlsx', '.xlsm', '.pptx', '.pptm', '.odt', '.ods', '.odp'}
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


def core_request(root, groups, hidden, max_hits, max_entries, ocr, thumbnail_dir):
    """The search request for the document core. Types, messages and the cache place stay Lumen's own."""
    import mimetypes
    from core import TEXT_EXTENSIONS
    from lumen_store import state_path
    mimetypes.init()
    # The order of core.file_kind: picture, PDF, sound or film, text; Office by its name.
    groups_of = (('image/', 'image'), ('video/', 'media'), ('audio/', 'media'), ('text/', 'text'))
    kinds = {suffix.lower(): kind for suffix, mime in mimetypes.types_map.items()
             for prefix, kind in groups_of if mime.startswith(prefix)}
    messages = ['Eintragslimit', 'Trefferlimit', 'Office-Datei zu groß.', 'Office-Datei nicht lesbar.',
                'PDF nicht lesbar.', 'Datei während der Suche verändert.']
    return dict(root=str(root), groups=groups, hidden=bool(hidden), max_hits=max_hits, max_entries=max_entries,
                visual=True, ocr=bool(ocr), thumbnails=bool(thumbnail_dir), kinds=kinds, texts=sorted(TEXT_EXTENSIONS),
                encodings=list(mimetypes.encodings_map), aliases=dict(mimetypes.suffix_map),
                cache=str(state_path() / 'content-cache'), messages={text: tr(text) for text in messages})


def scan(root, groups, hidden=False, max_hits=500, max_entries=100000, ocr=False, thumbnail_dir=None):
    """Walking, reading and matching run in the document core. Pictures it cannot answer from the cache
    come back as `visual` events: recognising them and making previews stays here."""
    from lumen_office import PDFError, program
    root = Path(root).resolve()
    try: command = [program(), 'search']
    except PDFError as error: raise ValueError(str(error)) from error
    extra = dict(scanned=0, hits=0, partial=0, empty=0, errors=0); details = []; images = 0
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        process.stdin.write(json.dumps(core_request(root, groups, hidden, max_hits, max_entries, ocr, thumbnail_dir)).encode())
        process.stdin.close()
        rust_hits = 0
        for line in process.stdout:
            event = json.loads(line)
            kind = event['type']
            if kind == 'hit': rust_hits += 1
            if kind == 'done':
                for key, value in extra.items(): event[key] += value
                event['error_details'] = (event['error_details'] + details)[:12]
                yield event
                break
            if kind != 'visual':
                yield event
                continue
            from lumen_ocr import visual_content
            extra['scanned'] += 1
            path = Path(event['path']); descriptor = None
            try:
                descriptor = folder_fd(root_fd, Path(event['relative']) if event['relative'] else Path('.'))
                text, cut, image = visual_content(path, descriptor, event['text'], ocr, thumbnail_dir if images < 100 else None)
                cut = cut or event['partial']
                if image:
                    images += 1
                    yield dict(image, type='image')
                extra['partial'] += int(cut); extra['empty'] += int(not text.strip())
                passage = find_passage(text, groups) if text else None
                if passage:
                    extra['hits'] += 1
                    yield dict(passage, type='hit', path=str(path), partial=cut, pdf=event['kind'] == 'pdf', image=event['kind'] == 'image')
                    if rust_hits + extra['hits'] >= max_hits:
                        process.kill()
                        yield {'type': 'done', 'scanned': None, 'visited': None, 'hits': rust_hits + extra['hits'], 'errors': extra['errors'],
                               'partial': extra['partial'], 'empty': extra['empty'], 'limit': tr('Trefferlimit'), 'error_details': details, 'elapsed': None}
                        break
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                extra['errors'] += 1
                if len(details) < 12: details.append(dict(path=str(path), error=str(error)[:200]))
            finally:
                if descriptor is not None: os.close(descriptor)
    finally:
        if process.poll() is None: process.kill()
        process.wait(); process.stdout.close(); os.close(root_fd)


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
