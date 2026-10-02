"""PDF editing worker: immutable sources, verified export, real redaction."""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def opened(path):
    import pymupdf
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 512 * 1024**2:
        raise ValueError('PDF nicht verfügbar, verknüpft oder größer als 512 MiB.')
    doc = pymupdf.open(path)
    if not doc.is_pdf or doc.needs_pass or not 1 <= len(doc) <= 2000:
        doc.close(); raise ValueError('Bitte eine unverschlüsselte PDF mit höchstens 2.000 Seiten verwenden.')
    return doc


def signature(path):
    info = Path(path).stat()
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def inspect(paths):
    pages = []
    for path in paths:
        with opened(path) as doc:
            before = signature(path)
            for i in range(len(doc)):
                pages.append(dict(path=path, page=i, rotation=0, boxes=[], stamp=before))
    if len(pages) > 2000: raise ValueError('Höchstens 2.000 Seiten pro Arbeitsmappe.')
    return pages


def page_document(item):
    import pymupdf
    if signature(item['path']) != item['stamp']: raise ValueError('Eine Quelldatei wurde verändert. Bitte neu öffnen.')
    source = opened(item['path']); result = pymupdf.open()
    try:
        index = item['page']
        if type(index) is not int or not 0 <= index < len(source): raise ValueError('Ungültige Seite.')
        if item['rotation'] not in (0,90,180,270): raise ValueError('Ungültige Drehung.')
        result.insert_pdf(source, from_page=index, to_page=index)
        page = result[0]; page.set_rotation((page.rotation + item['rotation']) % 360)
        if signature(item['path']) != item['stamp']: raise ValueError('Quelldatei während Lesen verändert.')
        return result
    except BaseException: result.close(); raise
    finally: source.close()


def render(item, target):
    with page_document(item) as doc:
        page = doc[0]; scale = min(2, 1400 / max(page.rect.width, page.rect.height))
        import pymupdf
        page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).save(target)
    return target


def export(pages, target, ocr=False, dpi=200, progress=lambda _: None):
    import pymupdf
    if not pages or len(pages) > 2000 or dpi not in (150,200,300): raise ValueError('Ungültige Seitenauswahl oder Qualität.')
    target = Path(target).absolute()
    if target.suffix.lower() != '.pdf': raise ValueError('Als PDF speichern.')
    if os.path.lexists(target): raise FileExistsError('Die Zieldatei existiert bereits. Bitte einen neuen Namen wählen.')
    if any(target == Path(p['path']).absolute() for p in pages): raise ValueError('Originale bleiben unverändert. Neuen Dateinamen wählen.')
    output = pymupdf.open()
    try:
        with tempfile.TemporaryDirectory(prefix='lumen-pdf-') as tmp:
            for position, item in enumerate(pages):
                progress(f'Seite {position + 1} von {len(pages)}')
                with page_document(item) as doc:
                    page = doc[0]; boxes = item.get('boxes', [])
                    for box in boxes:
                        if not isinstance(box, list) or len(box) != 4 or any(not isinstance(v,(float,int)) or not math.isfinite(v) or not 0 <= v <= 1 for v in box):
                            raise ValueError('Ungültiger Schwärzungsbereich.')
                        x0,y0,x1,y1 = box
                        if x0 >= x1 or y0 >= y1: raise ValueError('Leerer Schwärzungsbereich.')
                        rect = pymupdf.Rect(x0*page.rect.width,y0*page.rect.height,x1*page.rect.width,y1*page.rect.height) * page.derotation_matrix
                        page.add_redact_annot(rect, fill=(0,0,0), cross_out=False)
                    if boxes:
                        page.apply_redactions(images=2, graphics=2, text=0)
                        # Rasterize redacted pages: no old streams, hidden text, attachments or annotations survive.
                        pix = page.get_pixmap(dpi=dpi, alpha=False, annots=True)
                        clean = pymupdf.open(); clean.new_page(width=page.rect.width, height=page.rect.height).insert_image(page.rect, stream=pix.tobytes('png'))
                        doc = clean; page = doc[0]
                    try:
                        if ocr and not page.get_text().strip():
                            png = str(Path(tmp) / 'scan.png'); page.get_pixmap(dpi=dpi, alpha=False).save(png)
                            from lumen_ocr import languages
                            prefix = str(Path(tmp) / 'ocr')
                            subprocess.run(['tesseract', png, prefix, '-l', languages(), '--dpi', str(dpi), 'pdf'], capture_output=True, timeout=120, check=True)
                            with pymupdf.open(prefix + '.pdf') as recognized: output.insert_pdf(recognized)
                        else: output.insert_pdf(doc)
                    finally:
                        if boxes: doc.close()
            output.set_metadata({})
            with tempfile.NamedTemporaryFile(suffix='.pdf', prefix='.lumen-pdf-', dir=target.parent, delete=False) as stream:
                staged = Path(stream.name)
            try:
                output.save(staged, garbage=4, deflate=True, clean=True)
                with pymupdf.open(staged) as check:
                    if len(check) != len(pages) or check.is_repaired: raise ValueError('Export konnte nicht bestätigt werden.')
                    for page in check: page.get_text()
                with staged.open('rb') as stream: os.fsync(stream.fileno())
                # Atomic no-clobber installation, including another process choosing the same name.
                try: os.link(staged, target)
                except OSError as error:
                    import errno
                    if error.errno not in (errno.EOPNOTSUPP, errno.EPERM, errno.EXDEV): raise
                    from core import move_entry
                    move_entry(staged, target, atomic=True)
            finally: staged.unlink(missing_ok=True)
    finally: output.close()
    return str(target)


if __name__ == '__main__':
    import resource
    os.setsid()
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
    try:
        request = json.loads(sys.stdin.readline())
        def progress(message): print(json.dumps({'progress': message}), flush=True)
        if request['action'] == 'inspect': result = inspect(request['paths'])
        elif request['action'] == 'render': result = render(request['page'], request['target'])
        elif request['action'] == 'export': result = export(request['pages'], request['target'], request['ocr'], request['dpi'], progress)
        else: raise ValueError('Unbekannte Dokumentenaktion.')
        print(json.dumps({'result': result}), flush=True)
    except Exception as error: print(json.dumps({'error': str(error)}), flush=True); sys.exit(1)
