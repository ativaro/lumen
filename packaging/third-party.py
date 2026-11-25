#!/usr/bin/env python3
"""Collect notices from the source used by both installers, without network access."""
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
NOTICE = re.compile(r"^(?:licen[cs]e|copying|copyright|notice|authors|unlicense)(?:$|[._-])", re.I)
EXTRAS = (
    'packaging/licenses/Adobe-Glyph-List.txt', 'files/fonts/OFL.txt',
    'files/notes_icons/LICENSE', 'files/memory-runtime/LICENSE', 'files/memory-runtime/NOTICE.md',
    'native/service/vendor/unicode-ident/LICENSE-UNICODE', 'desktop/CREDITS.md',
    'desktop/COPYING.LGPL-3.0', 'packaging/licenses/Lumen-MIT.txt',
)


def collect(output):
    texts = {}
    references = defaultdict(list)
    inventory = []

    def include(path):
        data = path.read_bytes()
        digest = sha256(data).hexdigest()
        texts[digest] = data
        references[digest].append(path.relative_to(ROOT).as_posix())

    for extra in EXTRAS:
        include(ROOT / extra)
    for component in ('document-core', 'service'):
        base = ROOT / 'native' / component
        locked = {(p['name'], p['version']) for p in
                  tomllib.loads((base / 'Cargo.lock').read_text())['package'] if 'source' in p}
        found = set()
        for crate in sorted((base / 'vendor').iterdir()):
            pkg = tomllib.loads((crate / 'Cargo.toml').read_text())['package']
            key = pkg['name'], pkg['version']
            found.add(key)
            files = [p for p in crate.rglob('*') if p.is_file()]
            notices = [p for p in files if NOTICE.match(p.name) or
                       any(d.lower() in ('licenses', 'licences') for d in p.relative_to(crate).parts[:-1])]
            stub = {p.relative_to(crate).as_posix() for p in files} == {
                'Cargo.toml', '.cargo-checksum.json', 'src/lib.rs'} and not (crate / 'src/lib.rs').stat().st_size
            if not notices and not stub:
                raise ValueError(f'Missing third-party notice: {component}/{crate.name}')
            inventory.append(f'{component} | {key[0]} {key[1]} | {pkg["license"]}' +
                             (' | metadata stub (empty source)' if stub else ''))
            for path in notices:
                include(path)
        if locked != found:
            raise ValueError(f'{component}: vendor/lock mismatch: {sorted(locked ^ found)}')
    with output.open('wb') as stream:
        stream.write(('Lumen Desktop third-party inventory\n\n' + '\n'.join(inventory) +
                      '\n\nOriginal notices (identical copies grouped by source path)\n').encode())
        for digest in sorted(texts, key=lambda key: min(references[key])):
            stream.write(('\n' + '\n'.join(sorted(references[digest])) + '\n\n').encode())
            stream.write(texts[digest])
            stream.write(b'\n')


if __name__ == '__main__':
    collect(Path(sys.argv[1]))
