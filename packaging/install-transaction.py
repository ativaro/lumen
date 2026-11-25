#!/usr/bin/python3
"""Keep a rollback of program files only; environments and user data stay in place."""
import shutil
import sys
from pathlib import Path

PAYLOAD = ('bin', 'files', 'agent-app', 'desktop', 'shell', 'opencode-command',
           'opencode-skill', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_LICENSES.txt', 'uninstall.sh', 'install.json')


def remove(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def copy(source, target):
    if source.is_dir() and not source.is_symlink():
        shutil.copytree(source, target, symlinks=True)
    elif source.exists() or source.is_symlink():
        shutil.copy2(source, target, follow_symlinks=False)


def snapshot(prefix, backup):
    backup.mkdir(mode=0o700)
    for name in PAYLOAD:
        copy(prefix / name, backup / name)


def restore(prefix, backup):
    for name in PAYLOAD:
        remove(prefix / name)
        copy(backup / name, prefix / name)
    (prefix / 'install.json.next').unlink(missing_ok=True)


if __name__ == '__main__':
    {'snapshot': snapshot, 'restore': restore}[sys.argv[1]](Path(sys.argv[2]), Path(sys.argv[3]))
