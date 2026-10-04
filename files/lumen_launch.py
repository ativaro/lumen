"""Resolve sibling apps without falling back to an older desktop PATH entry."""
import os
from pathlib import Path
import shutil


def executable(name):
    if not name.startswith('lumen-') or Path(name).name != name:
        raise ValueError('Expected a Lumen application name.')
    # Source checkout and user bundle keep bin/ alongside files/.
    candidates = [Path(__file__).resolve().parent.parent/'bin'/name]
    if os.environ.get('LUMEN_BIN_DIR'):
        candidates.append(Path(os.environ['LUMEN_BIN_DIR'])/name)
    # A system installation stores modules in /usr/share/lumen/files.
    candidates.append(Path('/usr/bin')/name)
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK): return str(candidate)
    found = shutil.which(name)
    if found:return found
    raise FileNotFoundError(name)
