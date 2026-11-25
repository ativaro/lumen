"""Private, bounded clipboard attachments that survive draft recovery."""
import fcntl
import hashlib
import os
from pathlib import Path
from PySide6.QtCore import QBuffer, QIODevice, QSaveFile, QFileDevice
from PySide6.QtGui import QImage, QPixmap, QImageReader
from lumen_i18n import tr


FORMATS = ('image/png', 'image/jpeg', 'image/webp', 'image/bmp')


def protected_clipboard(clipboard, mode=None):
    """True when a password manager marked the clipboard content as secret."""
    mime = clipboard.mimeData() if mode is None else clipboard.mimeData(mode)
    return bool(mime and mime.data('x-kde-passwordManagerHint') == b'secret')


def has_image(mime):
    return bool(mime and (mime.hasImage() or any(mime.hasFormat(kind) for kind in FORMATS)))


def save(mime):
    if mime is None or mime.data('x-kde-passwordManagerHint') == b'secret':
        raise ValueError(tr('Geschützte Zwischenablage kann nicht an Lumen angehängt werden.'))
    if not has_image(mime): return None
    if mime.hasImage():
        value=mime.imageData()
        image=value.toImage() if isinstance(value,QPixmap) else QImage(value)
    else:
        kind=next(kind for kind in FORMATS if mime.hasFormat(kind));raw=mime.data(kind)
        if len(raw)>32*1024**2: raise ValueError(tr('Der Bildanhang darf höchstens 32 MiB groß sein.'))
        source=QBuffer();source.setData(raw);source.open(QIODevice.ReadOnly)
        reader=QImageReader(source,kind.split('/')[1].encode());size=reader.size()
        if not size.isValid() or size.width()*size.height()>32_000_000:
            raise ValueError(tr('Das Bild ist ungültig oder zu groß. Bitte einen kleineren Ausschnitt kopieren.'))
        image=reader.read()
    if image.isNull(): raise ValueError(tr('Das Bild in der Zwischenablage konnte nicht gelesen werden.'))
    if image.width()*image.height()>32_000_000:
        raise ValueError(tr('Das Bild ist zu groß. Bitte einen kleineren Ausschnitt kopieren.'))
    buffer=QBuffer();buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer,'PNG'): raise ValueError(tr('Das Bild konnte nicht als Anhang gespeichert werden.'))
    data=bytes(buffer.data())
    if len(data)>32*1024**2: raise ValueError(tr('Der Bildanhang darf höchstens 32 MiB groß sein.'))
    root=Path(os.environ.get('XDG_CACHE_HOME',str(Path.home()/'.cache')))/'lumen/clipboard'
    if root.is_symlink(): raise OSError(tr('Ungültiger Zwischenablage-Speicher.'))
    root.mkdir(parents=True,exist_ok=True,mode=0o700);root.chmod(0o700)
    with (root/'cache.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        target=root/('clipboard-'+hashlib.sha256(data).hexdigest()+'.png')
        if target.is_symlink(): raise OSError(tr('Ungültiger Bildanhang.'))
        if target.is_file(): return str(target)
        # Retain referenced drafts rather than evicting their images behind the user's back.
        if sum(p.stat().st_size for p in root.glob('clipboard-*.png'))+len(data)>256*1024**2:
            raise ValueError(tr('Der Zwischenablage-Speicher ist voll. Bitte das Bild als Datei anhängen.'))
        output=QSaveFile(str(target))
        if not output.open(QIODevice.WriteOnly): raise OSError(tr('Der Bildanhang konnte nicht gespeichert werden.'))
        if not output.setPermissions(QFileDevice.ReadOwner|QFileDevice.WriteOwner):
            output.cancelWriting();raise OSError(tr('Der Bildanhang konnte nicht geschützt gespeichert werden.'))
        if output.write(data)!=len(data) or not output.commit():
            output.cancelWriting();raise OSError(tr('Der Bildanhang konnte nicht gespeichert werden.'))
        return str(target)
