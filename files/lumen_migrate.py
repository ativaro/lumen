"""Non-destructive, idempotent migration of legacy Lumen reports."""
import os
from pathlib import Path
import shutil


def copy_missing(source, target):
    source, target = Path(source), Path(target)
    if not source.is_dir() or source.is_symlink(): return
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    for item in source.iterdir():
        destination = target / item.name
        if item.is_symlink() or destination.is_symlink(): continue
        if item.is_dir(): copy_missing(item, destination)
        elif item.is_file() and not destination.exists():
            try:
                # Exclusive creation preserves files written concurrently by the new version.
                with item.open('rb') as before, destination.open('xb') as after: shutil.copyfileobj(before, after)
                shutil.copystat(item, destination, follow_symlinks=False)
            except FileExistsError: pass


def migrate_user():
    cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache')))
    copy_missing(cache / 'opencode-lumen', cache / 'lumen')


if __name__ == '__main__': migrate_user()
