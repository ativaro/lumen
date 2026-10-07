"""Filesystem facts and bounded, explicit edits for Lumen Files properties."""
import hashlib
import mimetypes
import os
from pathlib import Path
import pwd
import grp
import shutil
import stat
from core import move_entry, valid_name
from lumen_i18n import tr


def identity(st):
    return (st.st_dev, st.st_ino)


def inspect(paths, job, remote=False):
    rows = []
    for value in paths:
        job.check()
        path = Path(value); st = path.lstat()
        kind = 'link' if stat.S_ISLNK(st.st_mode) else 'folder' if stat.S_ISDIR(st.st_mode) else 'file' if stat.S_ISREG(st.st_mode) else 'special'
        try: owner = pwd.getpwuid(st.st_uid).pw_name
        except KeyError: owner = str(st.st_uid)
        try: group = grp.getgrgid(st.st_gid).gr_name
        except KeyError: group = str(st.st_gid)
        acl = None
        if not remote and kind in ('file', 'folder'):
            try: acl = 'system.posix_acl_access' in os.listxattr(path, follow_symlinks=False)
            except OSError: pass
        rows.append(dict(path=str(path), name=path.name or str(path), kind=kind, identity=identity(st), mode=stat.S_IMODE(st.st_mode),
                         uid=st.st_uid, gid=st.st_gid, owner=owner, group=group, size=st.st_size,
                         modified=st.st_mtime, created=getattr(st, 'st_birthtime', None),
                         allocated=getattr(st, 'st_blocks', 0)*512, links=st.st_nlink,
                         mime=mimetypes.guess_type(str(path))[0] or 'application/octet-stream',
                         target=os.readlink(path) if kind == 'link' else '', acl=acl,
                         can_mode=not remote and kind in ('file','folder') and st.st_uid == os.geteuid() and acl is False,
                         remote=remote))
    result = dict(rows=rows, plans=[], metadata={}, acl_text='')
    if len(rows) == 1:
        row = rows[0]
        if row['created'] is None:
            try:
                from gi.repository import Gio
                info = Gio.File.new_for_path(row['path']).query_info('time::created', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None)
                row['created'] = info.get_attribute_uint64('time::created') or None
            except Exception:
                job.check()
        if row['kind'] == 'file':
            try:
                from gi.repository import Gio
                app = Gio.AppInfo.get_default_for_type(row['mime'], False)
                if app: result['metadata'][tr('Standard-App')] = app.get_display_name()
            except Exception:
                job.check()
            if row['mime'].startswith('image/'):
                from PySide6.QtGui import QImageReader
                reader = QImageReader(row['path']); dimensions = reader.size()
                if dimensions.isValid():
                    result['metadata'][tr('Bildmaße')] = f'{dimensions.width()} × {dimensions.height()} px'
                try:
                    from PIL import Image
                    if row['size'] > 64*1024*1024:raise ValueError('EXIF probe size limit')
                    with Image.open(row['path']) as image:
                        exif = image.getexif()
                        camera = ' '.join(str(exif.get(key, '')) for key in (271, 272)).strip()
                        if camera: result['metadata'][tr('Kamera')] = camera[:256]
                except Exception:
                    job.check()
            if row['mime'] == 'application/pdf' and shutil.which('pdfinfo'):
                try:
                    output = job.command(['pdfinfo', row['path']], timeout=5, max_output=32768, env=dict(os.environ, LC_ALL='C')).decode(errors='replace')
                    for line in output.splitlines():
                        if line.startswith('Pages:'): result['metadata'][tr('Seiten')] = line.partition(':')[2].strip()
                except Exception:
                    job.check()
        if row['kind'] in ('file','folder') and not remote and shutil.which('getfacl'):
            try:
                result['acl_text'] = job.command(['getfacl','--omit-header','--numeric','--',row['path']], timeout=4, max_output=32768).decode(errors='replace')
            except Exception:
                job.check()
        try:
            from interop_vault import coverage
            result['plans'] = coverage(paths)[0]['plans']
        except Exception:
            job.check(); result['backup_error'] = True
    return result


def folder_totals(paths, job):
    """Apparent bytes, no symlink traversal; repeated selections are counted once."""
    pending = list(paths); roots = {os.path.abspath(p) for p in paths}; seen = set(); directories = set(); files = folders = skipped = total = 0
    types = {}
    while pending:
        job.check(); value = os.path.abspath(pending.pop())
        if value in seen: continue
        seen.add(value)
        try:
            st = os.lstat(value)
            if stat.S_ISDIR(st.st_mode):
                if identity(st) in directories: continue
                directories.add(identity(st)); folders += value not in roots
                with os.scandir(value) as items:
                    for item in items:
                        job.check(); pending.append(item.path)
            elif stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
                files += 1; total += st.st_size
                family = 'links' if stat.S_ISLNK(st.st_mode) else (mimetypes.guess_type(value)[0] or 'other').split('/')[0]
                types[family] = types.get(family, 0) + st.st_size
        except OSError: skipped += 1
        if len(seen) % 200 == 0: job.progress.emit(tr('{0} Einträge geprüft', len(seen)))
    return dict(size=total, files=files, folders=folders, skipped=skipped, types=types)


def checksum(row, job):
    fd = os.open(row['path'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or identity(before) != tuple(row['identity']):
            raise ValueError(tr('Die Datei hat sich geändert. Eigenschaften erneut öffnen.'))
        digest = hashlib.sha256()
        while True:
            job.check(); chunk = stream.read(1024*1024)
            if not chunk: break
            digest.update(chunk)
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError(tr('Die Datei wurde während der Berechnung verändert.'))
        if identity(os.lstat(row['path'])) != identity(before):
            raise ValueError(tr('Die Datei hat sich geändert. Eigenschaften erneut öffnen.'))
        return digest.hexdigest()


def apply_local(row, name, mode, job):
    """No overwrite, no recursive chmod, no symlink permission changes."""
    path = Path(row['path']); name = valid_name(name); target = path.with_name(name)
    fd = os.open(path, os.O_PATH | os.O_NOFOLLOW)
    try:
        current = os.fstat(fd)
        if (identity(current), stat.S_IMODE(current.st_mode), current.st_uid, current.st_gid) != (tuple(row['identity']), row['mode'], row['uid'], row['gid']):
            raise ValueError(tr('Die Datei hat sich geändert. Eigenschaften erneut öffnen.'))
        if name != path.name and os.path.lexists(target):
            raise FileExistsError(tr('„{0}“ existiert bereits. Nichts überschrieben.', name))
        changing_mode = mode != row['mode']
        if changing_mode:
            if not row['can_mode'] or row['remote'] or not (stat.S_ISREG(current.st_mode) or stat.S_ISDIR(current.st_mode)):
                raise ValueError(tr('Diese Zugriffsrechte werden nicht lokal bearbeitet.'))
            if 'system.posix_acl_access' in os.listxattr(f'/proc/self/fd/{fd}'):
                raise ValueError(tr('Erweiterte ACL-Rechte vorhanden. Einfache Rechte nicht überschrieben.'))
            if mode & ~0o777 != row['mode'] & ~0o777:
                raise ValueError(tr('Sonderrechte bleiben unverändert.'))
        job.check()
        # Cancellation is no longer checked after the first mutation; report its actual result.
        warning = ''
        if changing_mode: os.chmod(f'/proc/self/fd/{fd}', mode)
        if name != path.name:
            try:
                if identity(path.lstat()) != identity(current):
                    raise ValueError(tr('Die Datei hat sich geändert. Eigenschaften erneut öffnen.'))
                move_entry(path, target, atomic=True)
                path = target
                from interop_paths import relocate
                try: relocate(row['path'], str(target))
                except Exception as error:
                    warning = tr('Name gespeichert; Verknüpfungen konnten nicht aktualisiert werden: {0}', str(error))
            except Exception as error:
                if not changing_mode: raise
                warning = tr('Rechte gespeichert; Umbenennen fehlgeschlagen: {0}', str(error))
        return dict(path=str(path), warning=warning)
    finally:
        os.close(fd)
