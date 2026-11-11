#!/usr/bin/env python3
"""Fail when a dependency's licence is not one that can be used freely without buying or separately licensing it."""
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent
# Permissive licences only (user decision of 11.11.2026). Copyleft and commercial licences are not accepted;
# a part without a permissive building block is written in this crate instead.
allowed = {'MIT', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause', 'Zlib', 'ISC', '0BSD', 'Unicode-3.0', 'Unlicense', 'CC0-1.0', 'MIT-0'}
packages = json.loads(subprocess.check_output(['cargo', 'metadata', '--format-version', '1', '--locked'], cwd=root))['packages']
for package in packages:
    if package['source'] is None: continue
    expression = (package['license'] or '').replace('/', ' OR ')
    # One freely usable alternative of an OR expression is enough; every part of an AND expression must be.
    choices = [[part.strip(' ()') for part in choice.split(' AND ')] for choice in expression.split(' OR ')]
    assert any(all(part.split(' WITH ')[0] in allowed for part in choice) for choice in choices), f"Licence not accepted: {package['name']} {package['version']}: {package['license']!r}"
print(f'{sum(p["source"] is not None for p in packages)} dependencies, all under accepted licences')
