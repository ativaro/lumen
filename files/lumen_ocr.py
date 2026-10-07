"""Local OCR and private image-description cache, shared with document tools."""
from lumen_i18n import tr
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from lumen_store import state_path


def stamp(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def cache_path(path):
    folder = state_path() / 'content-cache'; folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder / (hashlib.sha256(str(path).encode()).hexdigest() + '.json')


def cached(path, signature):
    try:
        value = json.loads(cache_path(path).read_text())
        return value if value.get('stamp') == signature else {}
    except (OSError, ValueError): return {}


def save_cache(path, signature, **values):
    value = cached(path, signature); value.update(stamp=signature, **values)
    target = cache_path(path)
    with tempfile.NamedTemporaryFile(dir=target.parent, mode='w', delete=False) as stream:
        temp = Path(stream.name)
        try:
            json.dump(value, stream); stream.flush(); os.fsync(stream.fileno()); os.replace(temp, target)
        finally: temp.unlink(missing_ok=True)


def languages():
    result = subprocess.run(['tesseract', '--list-langs'], capture_output=True, text=True, timeout=10, check=True)
    available = (result.stdout + result.stderr).splitlines()
    selected = [name for name in ('deu', 'eng') if name in available]
    if not selected: raise ValueError(tr('OCR-Sprachdaten fehlen. In der Einrichtung Deutsch/Englisch installieren.'))
    return '+'.join(selected)


def image_text(path, language=None):
    result = subprocess.run(['tesseract', str(path), 'stdout', '-l', language or languages()],
                            capture_output=True, timeout=60, check=True)
    return result.stdout[:1024 * 1024].decode(errors='replace')


def visual_content(path, directory_fd=None, text='', ocr=False, thumbnail_dir=None):
    from PIL import Image, ImageOps
    path = Path(path)
    fd = os.open(path.name if directory_fd is not None else path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    with os.fdopen(fd, 'rb') as source:
        import stat
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 128 * 1024 * 1024:
            return text, True, None
        signature = stamp(info); cache = cached(path, signature); partial = False; thumbnail = None
        if ocr and 'ocr' not in cache:
            with tempfile.TemporaryDirectory(prefix='lumen-ocr-') as tmp:
                if path.suffix.lower() == '.pdf':
                    from lumen_pdf import Document
                    from lumen_pdf_page import Page
                    document=Document(source.read());pages=text.split('\f')
                    if pages and not pages[-1].strip():pages.pop()
                    pages=(pages+['']*len(document))[:len(document)];partial=len(pages)>80
                    # ponytail: bounded per-file OCR; split larger scans to search all pages.
                    for index in range(min(len(pages),80)):
                        if len(pages[index].strip())>=20:continue
                        page=Page(document,index);image=page.render(min(4,2200/max(page.width,page.height)));target=Path(tmp)/'page.png'
                        if not image.save(str(target),'PNG'):raise ValueError(tr('OCR-Vorschau konnte nicht gespeichert werden.'))
                        pages[index]=image_text(target)
                    cache['ocr'] = '\f'.join(pages)
                else:
                    image = ImageOps.exif_transpose(Image.open(source)); image.thumbnail((3000, 3000))
                    image.convert('RGB').save(Path(tmp) / 'image.png')
                    cache['ocr'] = image_text(Path(tmp) / 'image.png')
                cache['partial'] = partial
        if thumbnail_dir and 'caption' not in cache and path.suffix.lower() != '.pdf':
            source.seek(0)
            image = ImageOps.exif_transpose(Image.open(source)); image.thumbnail((1400, 1400))
            thumbnail = str(Path(thumbnail_dir) / (hashlib.sha256(str(path).encode()).hexdigest() + '.jpg'))
            image.convert('RGB').save(thumbnail, quality=85)
        current = os.stat(path.name if directory_fd is not None else path, dir_fd=directory_fd, follow_symlinks=False)
        if signature != stamp(current) or signature != stamp(os.fstat(source.fileno())):
            raise ValueError(tr('Datei während der Inhaltssuche verändert.'))
        if cache: save_cache(path, signature, **{k: v for k, v in cache.items() if k != 'stamp'})
        content = cache.get('ocr', text)
        if cache.get('caption'): content += '\n' + cache['caption']
        return content, cache.get('partial', partial), (dict(path=str(path), thumbnail=thumbnail, stamp=signature) if thumbnail else None)
