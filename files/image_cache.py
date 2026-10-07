"""Private, bounded preview cache. Called only by the killable image worker."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile


def location(path, stamp, side):
    root = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'lumen/previews'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = hashlib.sha256(json.dumps([str(Path(path).absolute()), stamp, side]).encode()).hexdigest()
    return root / key


def read(path, stamp, side, output):
    base = location(path, stamp, side)
    try:
        data = json.loads(base.with_suffix('.json').read_text())
        if (not isinstance(data, dict) or data.get('kind') != 'image' or data.get('stamp') != stamp
                or not isinstance(data.get('width'), int) or not isinstance(data.get('height'), int)):
            return None
        from PIL import Image
        with Image.open(base.with_suffix('.png')) as image: image.verify()
        shutil.copyfile(base.with_suffix('.png'), output)
        os.utime(base.with_suffix('.png'), None)
        return {**data, 'output': output}
    except (OSError, ValueError):
        return None


def write(path, stamp, side, image, data):
    base = location(path, stamp, side)
    for suffix, content in (('.png', image), ('.json', json.dumps(data).encode())):
        with tempfile.NamedTemporaryFile(dir=base.parent, delete=False) as stream:
            temp = Path(stream.name)
            try:
                stream.write(content); stream.close(); temp.replace(base.with_suffix(suffix))
            finally:
                temp.unlink(missing_ok=True)
    # ponytail: prune on writes; at most 2048 entries / 512 MiB, no cache daemon.
    entries = sorted(((p.stat().st_mtime, p.stat().st_size, p) for p in base.parent.glob('*.png')), reverse=True)
    total = 0
    for i, (_, size, p) in enumerate(entries):
        total += size
        if i >= 2048 or total > 512 * 1024 * 1024:
            p.unlink(missing_ok=True); p.with_suffix('.json').unlink(missing_ok=True)
