#!/usr/bin/python3
"""Remove only retired packaged code; never touch application/user data."""
from pathlib import Path
import sys


def retire(prefix, manifest=None):
    prefix = Path(prefix)
    files = prefix/'files'
    if not files.exists(): return []
    if files.is_symlink() or not files.is_dir(): raise ValueError('Unsafe installed code directory')
    manifest = Path(manifest) if manifest else Path(__file__).with_name('retired-desktop-files.txt')
    names = [line for line in manifest.read_text().splitlines() if line and not line.startswith('#')]
    targets = set(files.glob('test_*.py'))
    for name in names:
        relative = Path(name)
        if relative.is_absolute() or relative.parts[0] != 'files' or '..' in relative.parts:
            raise ValueError('Invalid retired code path')
        target = prefix/relative
        if target.exists() or target.is_symlink(): targets.add(target)
        if target.suffix == '.py': targets.update((files/'__pycache__').glob(target.stem+'.*.pyc'))
    targets.update((files/'__pycache__').glob('test_*.pyc'))
    for target in targets:
        if target.is_symlink() or not target.is_file() or not target.parent.resolve().is_relative_to(files.resolve()):
            raise ValueError('Unsafe retired code path: '+str(target))
    for target in sorted(targets): target.unlink()
    for name in ('notes_web', 'qml/vault', '__pycache__'):
        directory = files/name
        if directory.is_dir() and not directory.is_symlink():
            for path in sorted(directory.rglob('*'), reverse=True):
                if path.is_dir() and not path.is_symlink() and not any(path.iterdir()): path.rmdir()
            if not any(directory.iterdir()): directory.rmdir()
    return sorted(str(p.relative_to(prefix)) for p in targets) + retire_programs(prefix)


def retire_programs(prefix):
    """Retired program trees outside files/: the native Vault lab and the bundled restic."""
    removed = []
    for tree in (prefix/'vault-lab'/'bin', prefix/'vault-lab'/'share'):
        if tree.is_dir() and not tree.is_symlink():
            for path in sorted(tree.rglob('*'), reverse=True):
                if path.is_symlink() or path.is_file(): path.unlink(); removed.append(str(path.relative_to(prefix)))
                elif path.is_dir(): path.rmdir()
            tree.rmdir()
    for path in (prefix/'vault').glob('restic-*') if (prefix/'vault').is_dir() else ():
        if path.is_file() and not path.is_symlink(): path.unlink(); removed.append(str(path.relative_to(prefix)))
    for directory in (prefix/'vault-lab', prefix/'vault'):
        if directory.is_dir() and not directory.is_symlink() and not any(directory.iterdir()): directory.rmdir()
    return removed


if __name__ == '__main__':
    print('Retired packaged code files:', len(retire(sys.argv[1])))
