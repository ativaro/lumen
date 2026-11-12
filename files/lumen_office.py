"""Lumen's document core in Rust (native/document-core): where it is, and how its PDF and Office answers reach the apps.

The core reads and writes PDFs and reads Word, Excel, PowerPoint and OpenDocument files; no server and no office suite.
This module starts it and passes on the few words it writes itself, translated.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess

from lumen_i18n import tr


class PDFError(ValueError):
    """A document the core cannot read or write, with the reason for the user."""


OFFICE = {'.docx', '.docm', '.xlsx', '.xlsm', '.pptx', '.pptm', '.odt', '.ods', '.odp'}
# Translated at use: the core writes the German words unless it is given others.
LABELS = ('WAHR', 'FALSCH', 'Folie', 'Folie ohne Text', 'Leeres Tabellenblatt', '[Bild in diesem Format nicht darstellbar]',
          'Gekürzt auf {0} Zeilen und {1} Spalten.', 'Das Dokument ist zu groß für die Leseansicht und wurde hier gekürzt.')
MESSAGES = ('Geschützte oder beschädigte Office-Datei.', 'Diese Office-Datei enthält zu viele, doppelte, verschlüsselte oder zu große Inhalte.',
            'Office-Datei unvollständig: ', 'Word-Dokument ohne Inhalt.', 'Arbeitsmappe ohne sichtbares Tabellenblatt.', 'Präsentation ohne Folien.',
            'OpenDocument-Datei ohne Inhalt.', 'XML-Entitäten im EPUB werden nicht geladen.')


def program():
    here = Path(__file__).resolve().parent
    for candidate in (Path(os.environ.get('LUMEN_BIN_DIR', here.parent / 'bin')) / 'lumen-document',
                      here.parent / 'native/document-core/target/release/lumen-document'):
        if candidate.is_file(): return str(candidate)
    found = shutil.which('lumen-document')
    if not found: raise PDFError(tr('Der Dokumentleser fehlt. Bitte die Lumen-Installation prüfen.'))
    return found


def pdf_tool(*arguments):
    """The command for text, information or a rendered page of a PDF: `text|info|render <file> [options]`."""
    return [program(), 'pdf-cli', *arguments]


def signature(path):
    """Device, inode, size and both change times: what a caller saw when it listed a file."""
    info = Path(path).stat()
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def limits():
    """Caps the memory and processor time of a worker process that reads untrusted files."""
    import resource
    for kind, budget in ((resource.RLIMIT_AS, 3*1024**3), (resource.RLIMIT_CPU, 90)):
        soft, hard = resource.getrlimit(kind)
        bound = min(budget, hard) if hard != resource.RLIM_INFINITY else budget
        if soft != resource.RLIM_INFINITY: bound = min(bound, soft)
        resource.setrlimit(kind, (bound, bound))


def message(error):
    """The core's reason from a failed job command, translated where the catalogue knows it."""
    text = str(error).strip()
    if text.startswith('lumen-document:'): text = text[len('lumen-document:'):].strip()
    return tr(text)


def read(path):
    """Title and one HTML section per document, sheet or slide."""
    command = [program(), 'office', str(path)]
    for label in LABELS: command += ['--label', label + '=' + tr(label)]
    try: result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as error: raise PDFError(tr('Die Verarbeitung hat zu lange gedauert.')) from error
    if result.returncode:
        message = result.stderr.strip()
        known = next((text for text in MESSAGES if message.startswith(text)), None)
        raise PDFError(tr(known) + message[len(known):] if known else tr('Geschützte oder beschädigte Office-Datei.'))
    value = json.loads(result.stdout)
    return value['title'], value['sections']
