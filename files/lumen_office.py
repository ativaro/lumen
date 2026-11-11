"""Word, Excel, PowerPoint and OpenDocument files as local reading pages; no server and no office suite.

The reading itself is Lumen's document core in Rust (native/document-core). This module starts it
and passes on the few words it writes itself, translated.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess

from lumen_i18n import tr
from lumen_pdf import PDFError

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


def pdf_tool(*arguments, beside=__file__):
    """The command for text, information or a rendered page of a PDF, with the arguments of lumen_pdf_worker.py.

    The document core answers; what it does not read it hands to the Python worker before writing anything."""
    import sys
    worker = [sys.executable, str(Path(beside).with_name('lumen_pdf_worker.py'))]
    try: return [program(), 'pdf-cli', '--fallback', *worker, *arguments]
    except PDFError: return [*worker, *arguments]


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
