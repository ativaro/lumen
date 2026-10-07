"""Full-resolution edits, staged beside the source with an exact original backup."""
from lumen_i18n import tr
import json
import os
import shutil
import stat
import sys
import tempfile
import uuid
from pathlib import Path


def file_stamp(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def save_image(path, operations, expected):
    from PIL import Image, ImageOps, PngImagePlugin
    path = Path(path)
    if path.is_symlink():
        raise ValueError(tr('Verknüpfungen bitte am Original bearbeiten.'))
    transforms = {'left': Image.Transpose.ROTATE_90, 'right': Image.Transpose.ROTATE_270,
                  'mirror': Image.Transpose.FLIP_LEFT_RIGHT}
    if not operations or any(op not in transforms for op in operations):
        raise ValueError(tr('Keine gültigen Änderungen.'))
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW), 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 128 * 1024 * 1024:
            raise ValueError(tr('Nur reguläre Bilder bis 128 MB können bearbeitet werden.'))
        def unchanged():
            if file_stamp(path.lstat()) != expected or file_stamp(os.fstat(stream.fileno())) != expected:
                raise ValueError(tr('Die Datei wurde inzwischen verändert. Bitte neu öffnen.'))
        unchanged()
        with Image.open(stream) as source:
            fmt = source.format
            if fmt not in {'JPEG', 'PNG', 'WEBP'} or getattr(source, 'n_frames', 1) != 1:
                raise ValueError(tr('Speichern ist nur für einzelne JPEG-, PNG- und WebP-Bilder möglich.'))
            if source.width * source.height > 80_000_000:
                raise ValueError(tr('Bilder über 80 Megapixel bitte extern bearbeiten.'))
            result = ImageOps.exif_transpose(source)
            for operation in operations:
                result = result.transpose(transforms[operation])
            options = {key: result.info[key] for key in ('icc_profile', 'dpi') if key in result.info}
            exif = result.getexif()
            for key, value in ((256, result.width), (257, result.height)):
                if key in exif:
                    exif[key] = value
            if exif:
                options['exif'] = exif.tobytes()
            if fmt == 'JPEG':
                options.update(quality=95, subsampling=0)
            elif fmt == 'WEBP':
                options['lossless'] = True
            elif fmt == 'PNG':
                metadata = PngImagePlugin.PngInfo()
                for key, value in result.info.items():
                    if isinstance(value, str):
                        metadata.add_text(key, value)
                options['pnginfo'] = metadata
            fd, name = tempfile.mkstemp(prefix='.lumen-edit-', dir=path.parent)
            staged = Path(name)
            try:
                with os.fdopen(fd, 'wb') as output:
                    result.save(output, format=fmt, **options)
                    output.flush()
                    os.fsync(output.fileno())
                # A server may reject POSIX attributes; content and backups still work.
                try:
                    staged.chmod(stat.S_IMODE(info.st_mode))
                except OSError:
                    pass
                unchanged()
                backup_dir = path.parent / '.lumen-originals'
                backup_dir.mkdir(mode=0o700, exist_ok=True)
                if backup_dir.is_symlink() or not backup_dir.is_dir():
                    raise ValueError(tr('Der Sicherungsordner ist keine reguläre Ablage.'))
                backup = backup_dir / f'{uuid.uuid4().hex[:12]}-{path.name}'
                stream.seek(0)
                with os.fdopen(os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as output:
                    shutil.copyfileobj(stream, output)
                    output.flush()
                    os.fsync(output.fileno())
                unchanged()
                os.replace(staged, path)
                return str(backup)
            finally:
                staged.unlink(missing_ok=True)


if __name__ == '__main__':
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    try:
        print(json.dumps({'backup': save_image(sys.argv[1], json.loads(sys.argv[2]), json.loads(sys.argv[3]))}))
    except Exception as exc:
        print(json.dumps({'error': str(exc)}))
        sys.exit(1)
