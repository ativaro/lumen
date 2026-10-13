"""Cooperative exclusion for Lumen capture; no secret data or broker endpoint.

All native Vault windows hold a shared lease for their full lifetime. Lumen
captures need an exclusive lease, held until the capture process has finished.
This does not prevent independent screenshot applications or privileged capture.
"""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import subprocess
import sys

MESSAGE = 'Use Lock and quit in the Lumen Vault tray menu before starting screen analysis.'


def acquire_capture():
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', ''))
    if not runtime.is_absolute():
        raise PermissionError('XDG_RUNTIME_DIR must be an absolute private directory.')
    directory = os.open(runtime, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        meta = os.fstat(directory)
        if meta.st_uid != os.getuid() or meta.st_mode & 0o077:
            raise PermissionError('Private runtime directory required.')
        fd = os.open('lumen-vault-privacy.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
    finally:
        os.close(directory)
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.getuid() or meta.st_nlink != 1 or meta.st_mode & 0o077:
            raise PermissionError('Invalid privacy lease.')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextmanager
def capture_guard():
    fd = acquire_capture()
    try:
        yield
    finally:
        os.close(fd)


def protected_clipboard(clipboard, mode=None):
    mime = clipboard.mimeData() if mode is None else clipboard.mimeData(mode)
    return bool(mime and mime.data('x-kde-passwordManagerHint') == b'secret')


if __name__ == '__main__':
    try:
        with capture_guard():
            raise SystemExit(subprocess.call(sys.argv[1:]))
    except OSError:
        print(MESSAGE, file=sys.stderr)
        subprocess.run(['notify-send', 'Lumen Vault', MESSAGE], check=False)
        raise SystemExit(1)
