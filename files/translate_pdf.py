"""Isolated PDF translation layout engine. Never edits the input in place."""
from lumen_i18n import tr
from pathlib import Path
import hashlib
import html
import json
import os
import sys
import tempfile

MAX_FILE = 50 * 1024**2
MAX_CHARS = 100000


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        total = 0
        while chunk := stream.read(1024**2):
            total += len(chunk)
            if total > MAX_FILE: raise ValueError(tr('PDF ist größer als 50 MiB.'))
            digest.update(chunk)
    return digest.hexdigest()


def inspect(path):
    import pymupdf as pdf
    path = Path(path)
    if path.suffix.lower() != '.pdf' or not path.is_file(): raise ValueError(tr('Bitte eine PDF-Datei auswählen.'))
    stamp = fingerprint(path); segments = []; total = 0
    with pdf.open(path) as document:
        if document.needs_pass: raise ValueError(tr('Die PDF ist verschlüsselt. Bitte zuerst eine entsperrte Kopie erstellen.'))
        if document.is_form_pdf or document.get_sigflags() > 0:
            raise ValueError(tr('Formulare und signierte PDFs werden nicht verändert. Bitte eine normale PDF-Kopie verwenden.'))
        if not 1 <= len(document) <= 100: raise ValueError(tr('Bitte eine PDF mit 1 bis 100 Seiten verwenden.'))
        for index, page in enumerate(document):
            if any(True for _ in page.annots() or []):
                raise ValueError(tr('PDF-Anmerkungen zuerst in einer separaten Kopie entfernen, damit die Übersetzung keine Markierungen verändert.'))
            blocks = page.get_text('dict', flags=pdf.TEXTFLAGS_DICT & ~pdf.TEXT_PRESERVE_IMAGES)['blocks']
            page_text = False
            for block in blocks:
                if block.get('type') != 0: continue
                lines = block.get('lines', [])
                spans = [span for line in lines for span in line['spans'] if span['text']]
                if not spans or not any(s['text'].strip() for s in spans): continue
                page_text = True
                if any(abs(line['dir'][0]-1) > .001 or abs(line['dir'][1]) > .001 for line in lines):
                    raise ValueError(tr('Gedrehter Text wird noch nicht unterstützt. Bitte eine PDF mit waagerechtem Text verwenden.'))
                parts = []; styles = []
                for line_number, line in enumerate(lines):
                    for span_number, span in enumerate(line['spans']):
                        if not span['text']: continue
                        parts.append((' ' if line_number and span_number == 0 else '') + span['text'])
                        styles.append(dict(size=span['size'], color=span['color'], bold=bool(span['flags'] & 16), italic=bool(span['flags'] & 2)))
                total += sum(len(p) for p in parts)
                if total > MAX_CHARS or len(segments) >= 1500: raise ValueError(tr('PDF enthält zu viel Text. Bitte in kleinere Dokumente teilen.'))
                segments.append(dict(id=str(len(segments)), page=index, rect=list(block['bbox']), parts=parts, styles=styles))
            if not page_text and page.get_images():
                raise ValueError(tr('Diese PDF enthält Bildseiten ohne Textschicht. Zuerst OCR ausführen; Bildtext wird nicht automatisch übersetzt.'))
        if not segments: raise ValueError(tr('Keine Textschicht gefunden. Bitte zuerst OCR ausführen.'))
        result = dict(path=str(path), fingerprint=stamp, pages=len(document), segments=segments, characters=total,
                      notice=tr('Text in Bildern bleibt unverändert. Längere Übersetzungen können kleinere Schrift benötigen.'))
    if fingerprint(path) != stamp: raise ValueError(tr('Die Quelldatei wurde während des Lesens verändert.'))
    return result


def write(manifest, translations, output):
    import pymupdf as pdf
    source = Path(manifest['path']); target = Path(output)
    if target.suffix.lower() != '.pdf' or target.exists() or target.is_symlink() or source.resolve() == target.resolve():
        raise ValueError(tr('Bitte einen neuen PDF-Dateinamen wählen. Vorhandene Dateien werden nicht überschrieben.'))
    current = inspect(source)
    if current['fingerprint'] != manifest['fingerprint'] or current['segments'] != manifest['segments']:
        raise ValueError(tr('Die Quelldatei wurde verändert. Bitte erneut übersetzen.'))
    expected = {s['id'] for s in current['segments']}
    if set(translations) != expected: raise ValueError(tr('Die Übersetzung ist unvollständig. Es wurde keine PDF gespeichert.'))
    for segment in current['segments']:
        parts = translations[segment['id']]
        if not isinstance(parts, list) or len(parts) != len(segment['parts']) or any(not isinstance(p,str) or (o.strip() and not p.strip()) or len(p)>30000 for p,o in zip(parts,segment['parts'])):
            raise ValueError(tr('Ungültige Übersetzung für die PDF.'))
    reduced = []
    # Same-directory temporary output + exclusive hard link: no replacement races.
    with tempfile.NamedTemporaryFile(prefix='.lumen-translate-', suffix='.pdf', dir=target.parent, delete=False) as stream: temp = Path(stream.name)
    try:
        with pdf.open(source) as document:
            for index, page in enumerate(document):
                links = page.get_links()
                segments = [s for s in current['segments'] if s['page'] == index]
                for segment in segments: page.add_redact_annot(pdf.Rect(segment['rect']), fill=False, cross_out=False)
                if segments: page.apply_redactions(images=0, graphics=0, text=0)
                # Text redaction can remove overlapping links; restore those annotations.
                remaining = {link.get('xref') for link in page.get_links()}
                for link in links:
                    if link.get('xref') not in remaining:
                        page.insert_link({k:v for k,v in link.items() if k not in ('xref','id')})
                for segment in segments:
                    fragments = []
                    for value, style in zip(translations[segment['id']], segment['styles']):
                        css = f"font-size:{style['size']}pt;color:#{style['color']:06x};font-weight:{'bold' if style['bold'] else 'normal'};font-style:{'italic' if style['italic'] else 'normal'}"
                        fragments.append('<span style="'+css+'">'+html.escape(value).replace('\n','<br>')+'</span>')
                    rectangle = pdf.Rect(segment['rect'])
                    spare, scale = page.insert_htmlbox(rectangle, ''.join(fragments), css='* {font-family: sans-serif;} body {margin:0; padding:0;}', scale_low=.60)
                    if spare < 0: raise ValueError(tr('Übersetzung passt auf Seite {0} nicht in den ursprünglichen Textbereich. Bitte kürzer formulieren lassen.', index+1))
                    if scale < .99: reduced.append(dict(page=index+1, block=segment['id'], scale=round(scale,3)))
            document.save(temp, garbage=4, deflate=True)
        if fingerprint(source) != current['fingerprint']: raise ValueError(tr('Die Quelldatei wurde verändert. Bitte erneut übersetzen.'))
        with temp.open('rb') as stream: os.fsync(stream.fileno())
        os.link(temp, target)
        return dict(path=str(target), pages=current['pages'], reduced=reduced, notice=current['notice'])
    finally: temp.unlink(missing_ok=True)


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
    try:
        request = json.load(sys.stdin); action = request.pop('action')
        if action == 'inspect': result = inspect(**request)
        elif action == 'write': result = write(**request)
        else: raise ValueError('Unknown PDF action')
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
