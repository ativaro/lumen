"""PDF translation through Lumen's document core: it finds the text blocks and writes the translated copy.
The input is never edited in place; a new PDF is written only when every block fits."""
from lumen_i18n import tr
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile

MAX_FILE = 50 * 1024**2
NOTICE = 'Text in Bildern bleibt unverändert. Längere Übersetzungen können kleinere Schrift benötigen.'


def _core(request):
    from lumen_office import message, program
    result = subprocess.run([program(), 'pdf-translate'], input=json.dumps(request, ensure_ascii=False).encode(),
                            capture_output=True, timeout=170)
    if result.returncode: raise ValueError(message(result.stderr.decode(errors='replace')[:600]))
    return json.loads(result.stdout)


def inspect(path):
    """The blocks to translate: id, page, box, parts with their styles, and angle."""
    return dict(_core(dict(action='inspect', path=str(Path(path).absolute()))), notice=tr(NOTICE))


def write(manifest, translations, output):
    """A new PDF at `output` with every block of `manifest` replaced by its translated parts."""
    result = _core(dict(action='write', manifest=manifest, translations=translations, output=str(Path(output).absolute())))
    return dict(result, notice=tr(NOTICE))


def export_copy(source, output, job):
    target = Path(output)
    if target.suffix.lower() != '.pdf' or target.exists() or target.is_symlink():
        raise ValueError(tr('Bitte einen neuen PDF-Dateinamen wählen. Vorhandene Dateien werden nicht überschrieben.'))
    with tempfile.NamedTemporaryFile(prefix='.lumen-translate-', suffix='.pdf', dir=target.parent, delete=False) as stream:
        temp = Path(stream.name)
        try:
            with Path(source).open('rb') as input:
                while chunk := input.read(1024**2): job.check(); stream.write(chunk)
            stream.flush(); os.fsync(stream.fileno()); job.check(); os.link(temp, target)
        finally: temp.unlink(missing_ok=True)
    return str(target)


def worker(job, action, **values):
    output = job.command([sys.executable, str(Path(__file__))], json.dumps(dict(action=action, **values), ensure_ascii=False).encode(), timeout=180, max_output=4*1024**2)
    return json.loads(output)


if __name__ == '__main__':
    from lumen_office import limits
    limits()
    try:
        request = json.load(sys.stdin); action = request.pop('action')
        if action == 'inspect': result = inspect(**request)
        elif action == 'write': result = write(**request)
        else: raise ValueError('Unknown PDF action')
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
