"""Lumen knows projects only: the retired workspace and room concepts must not return.

User decision: Arbeitsplatz, Arbeitsraum, Workspace, Workplace and Raum (rooms)
are removed completely, not renamed.  This guard searches file contents and
file names of the shipped source tree for those terms.  Anything that has to
keep one of the words (an external API, a brand name, the rule itself) needs
an entry in ALLOWED with one sentence of justification.

Run:     cd files && python3 -m unittest test_no_workspace_concept
Report:  python3 files/test_no_workspace_concept.py --report   (full list per file)
"""
import fnmatch
import os
import re
import sys
import unittest
from collections import Counter, namedtuple
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF = 'files/' + Path(__file__).name

# ---------------------------------------------------------------- scope
SCOPE_DIRS = ('files', 'agent-app', 'bin', 'tests', 'packaging', 'plasmoid', 'system',
              'systemd', 'data', 'native', 'opencode-skill', 'opencode-command')
ROOT_FILE_GLOBS = ('install*.sh', 'uninstall.sh', 'bootstrap.sh', '*.md')
# Directory names skipped wherever they occur below a scope directory.
SKIP_DIR_NAMES = {'.git', '__pycache__', 'graphify-out', 'docs', 'tasks', 'licenses',
                  'target', 'build', 'node_modules', '.venv', '.mypy_cache', '.pytest_cache'}
SKIP_FILES = {'THIRD_PARTY_NOTICES.md'}
LICENSE_NAME = re.compile(
    r'^(?:licen[sc]e|copying|notice|unlicense)(?:[-._](?:mit|apache|bsd|isc|zlib|unicode|txt|md|[0-9.]+))*$',
    re.I)
BINARY_SUFFIXES = {
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.icns', '.bmp', '.tif', '.tiff', '.svg', '.svgz',
    '.pdf', '.woff', '.woff2', '.ttf', '.otf', '.wav', '.mp3', '.ogg', '.oga', '.flac', '.mp4', '.webm',
    '.zip', '.gz', '.xz', '.zst', '.bz2', '.tar', '.7z', '.so', '.o', '.a', '.bin', '.pyc', '.pyo',
    '.db', '.sqlite', '.kdbx', '.icc', '.qm', '.rcc', '.onnx',
}

# ---------------------------------------------------------------- terms
# Case-insensitive.  The concept words match as substrings; the room model as
# whole words, as identifier parts (room_, _room) and as German "Raum…" compounds.
TERMS_ANYCASE = re.compile(
    r'workspace|workplace'
    r'|arbeitspl(?:a|ä|ae)tz|arbeitsr(?:a|ä|ae)um|arbeitsbereich'
    r'|project_rooms|room-shelf'
    r'|\b(?:rooms?|raum|räume|raeume)\b'
    r'|rooms?_|_rooms?'
    r'|\b(?:raum|räum|raeum)[a-zäöüß]+',
    re.I)
# Case-sensitive: CamelCase room identifiers (RoomModel, Room(, ProjectRooms, roomId).
TERMS_CAMEL = re.compile(r'Rooms?(?=[A-Z(])|(?<=[a-z0-9])Rooms?\b|\broom(?=[A-Z(])')
# Cheap pre-filter: every term above contains one of these (lower-cased).
PREFILTER = ('workspace', 'workplace', 'arbeitspl', 'arbeitsr', 'arbeitsbereich',
             'room', 'raum', 'räum', 'raeum')

# ---------------------------------------------------------------- exceptions
# path:     glob relative to the repository root (fnmatch; one file where possible)
# pattern:  regex; a hit is allowed only if it lies inside a match of this
#           pattern on the same line.  None allows the whole file.
# reason:   one sentence explaining why the term is legitimate there.
# optional: True = the entry may currently have no hit (see test 2).
# limit:    maximum number of lines the entry may cover (None = unlimited).
Allowed = namedtuple('Allowed', 'path pattern reason optional limit')


def allow(path, pattern, reason, optional=False, limit=None):
    return Allowed(path, re.compile(pattern) if pattern else None, reason, optional, limit)


KWIN_API = (r'\bworkspace\.(?:windowList|clientArea|currentDesktop|activeWindow|desktops|createDesktop'
            r'|activeScreen|screens|stackingOrder|raiseWindow|sendClientToScreen)\b')
KWIN_REASON = ('KWin scripting API: the global object of a KWin script is called "workspace"; '
               'the JavaScript is sent to KWin and the name is not ours to choose.')
KWIN_FILES = ('files/lumen_actions.py', 'files/lumen_activation.py',
              'files/test_lumen_activation.py', 'tests/check-screen-companion.py',
              'tests/desktop/session.py')
PLASMA_PKG = r'\bplasma-workspace\b'
PLASMA_REASON = 'Name of the upstream KDE package and repository "plasma-workspace".'
PLASMA_FILES = ('INSTALL.md', 'SPEC-appmenu.md', 'packaging/arch/PKGBUILD')

ALLOWED = (
    *(allow(path, KWIN_API, KWIN_REASON) for path in KWIN_FILES),
    *(allow(path, PLASMA_PKG, PLASMA_REASON) for path in PLASMA_FILES),
    allow('plasmoid/contents/ui/NotificationHost.qml', r'\borg\.kde\.plasma\.workspace\b',
          'QML import of the KDE module org.kde.plasma.workspace.dbus, an upstream name.'),
    allow('packaging/GOOGLE_DRIVE.md', r'developers\.google\.com/workspace\b',
          'Google publishes its Drive API documentation under developers.google.com/workspace.'),
    allow('*', r'\bGoogle Workspace\b',
          'Brand name of the Google product; it is not a Lumen concept.', optional=True),
    allow('native/*Cargo.toml', r'^\s*\[workspace(?:\.[\w.-]+)?\]\s*$|\bworkspace\s*=\s*true\b',
          'Cargo manifest syntax ([workspace] table, key inheritance) is fixed by Cargo.', optional=True),
    allow('native/*Cargo.*', r'\brustc-std-workspace-(?:core|alloc|std)\b',
          'Names of crates from the Rust standard library build, fixed upstream.', optional=True),
    allow('AGENTS.md', None,
          'The binding rule against workspaces has to name the forbidden terms.'),
    allow('packaging/retired-desktop-files.txt', r'^[\w./-]+$',
          'Lines are old file names that upgrades delete; they must keep the retired names.'),
    allow(SELF, None,
          'This guard defines the forbidden terms and their exceptions.'),
    allow('files/lumen_store.py', r'workplace/',
          'One-time takeover of settings stored under the old key prefix "workplace/"; '
          'limited to the two lines of that single SQL statement.', limit=2),
    allow('files/test_store_migration.py', r'workplace/?',
          'The takeover test has to create a database that still holds the old key prefix.'),
    # Knowingly kept until Lumen Server stops sending the field and version 1 pairings are renewed
    # (see HANDOVER-server-arbeitsplatz-reste.md). Removing these lines changes stored scope keys.
    *(allow(path, r'\bworkspace(?:_id)?\b', 'Stored version 1 pairings and the reply of /bridge/me still carry '
            'workspace_id, and existing scope keys hash it; the desktop only reads it to keep those scopes or to refuse old records.')
      for path in ('files/sync_identity.py', 'files/memory_sync.py', 'files/drive_sync.py')),
    *(allow(path, r'workspace(?:_id)?', 'Test data for the kept server contract: replies that still carry workspace_id, '
            'and old records or requests with the retired field that must be refused.')
      for path in ('files/test_desktop_backend.py', 'files/test_sync_identity.py', 'files/test_sync_settings.py',
                   'files/test_drive_http.py', 'files/test_drive_mcp.py', 'files/test_drive_outdated.py')),
    allow('README.md', r'\bleave room for\b',
          'English idiom for spare capacity (retained update runs), not the room model.'),
    allow('files/translations/en/troubleshooter.json', r'\bMake room so\b',
          'English idiom for freeing disk space, not the room model.'),
    allow('files/translations/en/desktop-workbench.json', r'\bRoom for your result\b',
          'English wording for "Platz für dein Ergebnis" (empty answer area), not the room model.'),
    allow('files/test_files_layout.py', r'\bRaumplan\.pdf\b',
          'Sample file name in a layout test; a "Raumplan" is a floor plan, not the room model.'),
)

Hit = namedtuple('Hit', 'path line text')   # line 0 = the file or directory name itself


# ---------------------------------------------------------------- scanning
def _in_scope_files():
    """Yield (relative posix path, absolute path) of every file and directory in scope."""
    for name in sorted(os.listdir(ROOT)):
        full = ROOT / name
        if full.is_file() and any(fnmatch.fnmatch(name, glob) for glob in ROOT_FILE_GLOBS):
            if name not in SKIP_FILES and not LICENSE_NAME.match(name):
                yield name, full, False
    for top in SCOPE_DIRS:
        base = ROOT / top
        if not base.is_dir():
            continue
        for folder, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIR_NAMES)
            relative = Path(folder).relative_to(ROOT).as_posix()
            if folder != str(base):
                yield relative, Path(folder), True
            for name in sorted(files):
                if name in SKIP_FILES or LICENSE_NAME.match(name):
                    continue
                yield relative + '/' + name, Path(folder) / name, False


def _raw_matches(line):
    spans = [match.span() for match in TERMS_ANYCASE.finditer(line)]
    spans += [match.span() for match in TERMS_CAMEL.finditer(line)]
    return spans


def _token(line, start, end):
    """Widen a hit to the surrounding identifier or word so the list reads as a work list."""
    while start > 0 and (line[start - 1].isalnum() or line[start - 1] in '_-./'):
        start -= 1
    while end < len(line) and (line[end].isalnum() or line[end] in '_-./'):
        end += 1
    while end > start and line[end - 1] in '-./':      # sentence punctuation, path separators
        end -= 1
    while start < end and line[start] in '-./':
        start += 1
    return start, end


def _line_hits(path, number, line, entries, used):
    """Return the display tokens of all hits on a line that no exception covers."""
    spans = _raw_matches(line)
    if not spans:
        return []
    covers = []
    for index, entry in entries:
        if entry.pattern is None:
            covers.append((index, entry, 0, len(line)))
        else:
            covers += [(index, entry, *match.span()) for match in entry.pattern.finditer(line)]
    open_spans = []
    for start, end in spans:
        for index, entry, low, high in covers:
            if low <= start and end <= high:
                lines = used.setdefault(index, set())
                if entry.limit is None or (path, number) in lines or len(lines) < entry.limit:
                    lines.add((path, number))
                    break
        else:
            open_spans.append(_token(line, start, end))
    tokens, last_end = [], -1
    for start, end in sorted(set(open_spans)):
        if start >= last_end:
            tokens.append(line[start:end][:80])
            last_end = end
    return tokens


def scan():
    """Return (hits, used); used maps the index in ALLOWED to the lines it covered."""
    hits, used = [], {}
    for path, full, is_dir in _in_scope_files():
        entries = [(index, entry) for index, entry in enumerate(ALLOWED)
                   if fnmatch.fnmatch(path, entry.path)]
        name = path.rsplit('/', 1)[-1]
        if any(key in name.lower() for key in PREFILTER):
            whole_file = [pair for pair in entries if pair[1].pattern is None]
            hits += [Hit(path, 0, token) for token in _line_hits(path, 0, name, whole_file, used)]
        if is_dir or full.is_symlink() or full.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            data = full.read_bytes()
        except OSError:
            continue
        if b'\0' in data[:8192]:
            continue
        text = data.decode('utf-8', 'replace')
        lowered = text.lower()
        if not any(key in lowered for key in PREFILTER):
            continue
        for number, line in enumerate(text.split('\n'), 1):
            low = line.lower()
            if any(key in low for key in PREFILTER):
                hits += [Hit(path, number, token)
                         for token in _line_hits(path, number, line, entries, used)]
    return hits, used


def _where(hit):
    return f'{hit.path}:{hit.line}: {hit.text}' if hit.line else f'{hit.path}: [Dateiname] {hit.text}'


def report(hits):
    """Full list, grouped by file with counts, most hits first."""
    per_file = Counter(hit.path for hit in hits)
    out = [f'Treffer gesamt: {len(hits)} in {len(per_file)} Dateien', '']
    for path, count in sorted(per_file.items(), key=lambda item: (-item[1], item[0])):
        out.append(f'{path} ({count})')
        out += ['  ' + _where(hit) for hit in hits if hit.path == path]
        out.append('')
    return '\n'.join(out)


# ---------------------------------------------------------------- tests
class NoWorkspaceConceptTest(unittest.TestCase):
    LIMIT = 60

    @classmethod
    def setUpClass(cls):
        cls.hits, cls.used = scan()

    def test_retired_workspace_and_room_terms_do_not_return(self):
        hits = self.hits
        if not hits:
            return
        files = len({hit.path for hit in hits})
        lines = [_where(hit) for hit in hits[:self.LIMIT]]
        if len(hits) > self.LIMIT:
            lines.append(f'… und {len(hits) - self.LIMIT} weitere')
        self.fail(
            f'{len(hits)} Treffer in {files} Dateien: Lumen kennt nur Projekte. '
            'Arbeitsplatz/Arbeitsraum/Workspace/Workplace/Raum entfernen (nicht umbenennen) '
            'oder eine eng begründete Ausnahme in ALLOWED eintragen.\n'
            + '\n'.join(lines)
            + f'\nGesamt: {len(hits)} (vollständige Liste: python3 {SELF} --report)')

    def test_every_exception_is_still_needed(self):
        stale = [f'{entry.path}  /{entry.pattern.pattern if entry.pattern else "*"}/  ({entry.reason})'
                 for index, entry in enumerate(ALLOWED)
                 if not entry.optional and not self.used.get(index)]
        self.assertFalse(stale, 'Ausnahmen ohne Treffer bitte aus ALLOWED entfernen:\n' + '\n'.join(stale))

    def test_exceptions_are_narrow_and_justified(self):
        for entry in ALLOWED:
            with self.subTest(path=entry.path):
                self.assertGreater(len(entry.reason.split()), 5, 'Begründung fehlt')
                self.assertTrue(entry.pattern is not None or not set('*?[') & set(entry.path),
                                'Ganze Dateien nur einzeln ausnehmen, nie per Platzhalter')


if __name__ == '__main__':
    if '--report' in sys.argv[1:]:
        print(report(scan()[0]))
    else:
        unittest.main()
