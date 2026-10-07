"""Release only dead, previously used KIO-FUSE mounts; never live shared mounts."""
import errno
import os
from pathlib import Path
import re
import subprocess
import sys


def mount_records(text, uid):
    records = {}
    for line in text.splitlines():
        fields = line.split()
        try: split = fields.index('-')
        except ValueError: continue
        if len(fields) <= split+3 or fields[split+1] != 'fuse.kio-fuse': continue
        path = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), fields[4])
        if (Path(path).parent != Path(f'/run/user/{uid}') or not Path(path).name.startswith('kio-fuse-')
                or f'user_id={uid}' not in fields[split+3].split(',')): continue
        records[path] = fields[0]
    return records


def mounts():
    return mount_records(Path('/proc/self/mountinfo').read_text(), os.getuid())


def probe(path):
    # A bounded child avoids hanging the UI/cleanup process on a broken network.
    result = subprocess.run([sys.executable, __file__, '--probe', path], capture_output=True, timeout=2)
    return result.returncode == errno.ENOTCONN


def cleanup(paths):
    known = [Path(os.path.abspath(p)) for p in paths]
    for mount, identity in mounts().items():
        if not any(path.is_relative_to(Path(mount)) for path in known): continue
        try:
            if not probe(mount) or mounts().get(mount) != identity: continue
            # No lazy/forced unmount. ENOTCONN means the FUSE daemon is gone.
            subprocess.run(['fusermount3', '-u', '--', mount], capture_output=True, timeout=3, check=False)
        except (OSError, subprocess.TimeoutExpired): continue


if __name__ == '__main__':
    if sys.argv[1:2] == ['--probe']:
        try: os.stat(sys.argv[2])
        except OSError as exc: sys.exit(exc.errno if exc.errno == errno.ENOTCONN else 1)
        sys.exit(0)
    cleanup(sys.argv[1:])
