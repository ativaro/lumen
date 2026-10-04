#!/usr/bin/env python3
"""Fail closed when the lock file or collected attribution texts change."""
import hashlib
import json
from pathlib import Path
import tomllib

root = Path(__file__).resolve().parent
lock = tomllib.loads((root / 'Cargo.lock').read_text())
packages = {(p['name'], p['version']) for p in lock['package'] if p.get('source') or p['name']=='keepass'}
inventory = json.loads((root / 'licenses/inventory.json').read_text())
assert packages == {(p['name'], p['version']) for p in inventory}, 'License inventory differs from Cargo.lock'
reviewed = {
    'MIT', 'Apache-2.0', 'MIT OR Apache-2.0', 'Apache-2.0 OR MIT',
    '0BSD OR MIT OR Apache-2.0', 'MIT OR Apache-2.0 OR Zlib', 'MIT OR Zlib OR Apache-2.0', 'MIT/Apache-2.0',
    'CC0-1.0 OR MIT-0 OR Apache-2.0',
    '(MIT OR Apache-2.0) AND Unicode-3.0', 'Unicode-3.0',
    'MIT OR Apache-2.0 OR LGPL-2.1-or-later', 'Zlib', 'Unlicense OR MIT',
    'Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT',
}
for p in inventory:
    assert p['spdx'] in reviewed, f"Unreviewed license: {p['name']} {p['spdx']}"
    assert p['files'] and p['sha256'], p['name']
    directory = root / 'licenses' / (p['name'] + '-' + p['version'])
    for name, digest in p['sha256'].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest, f'{directory / name}: notice changed'
print(f'{len(inventory)} dependency records: versions, reviewed expressions and notice hashes match')

# Vendored engine remains MIT, with a complete, explicit modified-source manifest.
provenance = json.loads((root / 'vendor/provenance.json').read_text())
source = root / 'vendor/keepass'
assert tomllib.loads((source / 'Cargo.toml').read_text())['package']['license'] == 'MIT'
assert (source / 'LICENSE').read_bytes() == (root / 'licenses/keepass-0.15.0/LICENSE').read_bytes()
actual = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
assert actual == provenance['local_files_sha256'], 'Vendored source changed; review and update provenance explicitly'
print('Vendored keepass: MIT notice, source inventory and local patch hashes match')
