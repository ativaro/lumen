#!/usr/bin/python3
"""Install only the standalone applications, without administrator access."""
import argparse
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

TOOLS = ('meetings', 'household', 'workbench', 'radio', 'vault', 'inbox', 'reader', 'sound', 'wissen')
MARKER = 'LumenStandaloneToolsInstaller'


def install(repo, data, binaries):
    repo, data, binaries = (Path(p).expanduser().resolve() for p in (repo, data, binaries))
    # Desktop Exec has two escaping layers; accept quoted paths with spaces and
    # refuse unusual metacharacters instead of producing an ambiguous launcher.
    if any(c in str(binaries) for c in '\n\r"\\`$%'):
        raise ValueError('Das Starterverzeichnis enthält nicht unterstützte Sonderzeichen.')
    sources = sorted(p for p in (repo/'files').iterdir()
                     if p.suffix in ('.py', '.qss', '.svg') and not p.name.startswith('test_'))
    if not (repo/'files/tools_app.py').is_file(): raise ValueError('Anwendungsquellen fehlen.')
    digest = hashlib.sha256()
    for p in sources: digest.update(p.name.encode()); digest.update(p.read_bytes())
    runtime = data/'lumen-tools/runtime'/digest.hexdigest()[:20]
    writes = {}
    for tool in TOOLS:
        name = 'lumen-'+tool; binary = binaries/name
        writes[binary] = ('#!/bin/sh\n# '+MARKER+'\n'
                         f'if [ -x /usr/bin/{name} ]; then exec /usr/bin/{name} "$@"; fi\n'
                         f'exec /usr/bin/python3 {shlex.quote(str(runtime/"tools_app.py"))} {tool} "$@"\n', 0o755)
        desktop = (repo/'data/applications'/f'{name}.desktop').read_text()
        desktop = desktop.replace(f'%INSTALL_BIN%/{name}', f'"{binary}"')
        writes[data/'applications'/f'{name}.desktop'] = (desktop+f'X-{MARKER}=true\n', 0o644)
        icon = (repo/'icons/hicolor/scalable/apps'/f'{name}.svg').read_text()
        writes[data/'icons/hicolor/scalable/apps'/f'{name}.svg'] = (icon+f'<!-- {MARKER} -->\n', 0o644)
    # Complete preflight before writing; leave unrelated/custom launchers intact.
    for path, (content, mode) in writes.items():
        if path.is_symlink() or (path.exists() and (not path.is_file() or MARKER not in path.read_text())):
            raise ValueError(f'Vorhandene eigene Datei bleibt erhalten: {path}')
    runtime.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not runtime.exists():
        with tempfile.TemporaryDirectory(prefix='.install-', dir=runtime.parent) as tmp:
            staged = Path(tmp)/'files'; staged.mkdir()
            for p in sources: shutil.copy2(p, staged/p.name)
            staged.rename(runtime)
    for path, (content, mode) in writes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            staged = Path(stream.name)
            try:
                os.fchmod(stream.fileno(), mode); stream.write(content); stream.flush(); os.fsync(stream.fileno())
                os.replace(staged, path)
            finally: staged.unlink(missing_ok=True)
    return runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-home', type=Path, default=Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share'))))
    parser.add_argument('--bin-dir', type=Path, default=Path.home()/'.local/bin')
    args = parser.parse_args()
    subprocess.run(['/usr/bin/python3', '-c', 'import PyQt5.QtWidgets, PyQt5.QtSvg, gi, PIL'], check=True)
    runtime = install(Path(__file__).resolve().parent, args.data_home, args.bin_dir)
    for command in (['update-desktop-database', str(args.data_home/'applications')], ['kbuildsycoca6', '--noincremental']):
        if shutil.which(command[0]):
            try: subprocess.run(command, check=True, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (subprocess.SubprocessError, OSError): print('Menü-Aktualisierung folgt beim nächsten Anmelden.')
    print('Eigenständige Anwendungen für diesen Benutzer installiert:', runtime)


if __name__ == '__main__': main()
