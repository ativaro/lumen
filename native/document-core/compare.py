#!/usr/bin/env python3
"""Compare this crate's Office reading with the Python reader, file by file: title and every section must be equal.

usage: compare.py <lumen-document> <files dir with lumen_office.py> <office file>...
Prints one line per file with the outcome and both run times; no document content."""
import json
import subprocess
import sys
import time
from pathlib import Path

binary, files = sys.argv[1], sys.argv[2]
sys.path.insert(0, files)
import lumen_office  # noqa: E402
from lumen_pdf import PDFError  # noqa: E402

different = 0
for name in sys.argv[3:]:
    path = Path(name); kind = path.suffix.lower()
    start = time.perf_counter()
    try:
        archive = lumen_office.open_archive(path)
        with archive: expected = dict(zip(('title', 'sections'), lumen_office.sections(kind, archive)))
    except PDFError as error: expected = dict(error=str(error))
    middle = time.perf_counter()
    result = subprocess.run([binary, 'office', str(path)], capture_output=True, text=True, timeout=120)
    actual = json.loads(result.stdout) if result.returncode == 0 else dict(error=result.stderr.strip())
    end = time.perf_counter()
    same = actual == expected or 'error' in actual and 'error' in expected
    different += not same
    where = ''
    if not same and 'sections' in actual and 'sections' in expected:
        pair = next(((i, a, b) for i, (a, b) in enumerate(zip(actual['sections'], expected['sections'])) if a != b), None)
        if pair:
            i, a, b = pair; at = next((n for n, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            where = f' section {i} at {at}: rust {a[max(0, at - 12):at + 28]!r} python {b[max(0, at - 12):at + 28]!r}'
        else: where = f' sections {len(actual["sections"])} vs {len(expected["sections"])} title {actual["title"] == expected["title"]}'
    elif not same: where = f' rust {str(actual)[:80]!r} python {str(expected)[:80]!r}'
    print(('same' if same else 'DIFFERENT'), kind, f'python {round((middle - start) * 1000)} ms', f'rust {round((end - middle) * 1000)} ms', where if '--show' in sys.argv or not same else '')
print(f'{len(sys.argv) - 3 - different} of {len(sys.argv) - 3} equal')
sys.exit(1 if different else 0)
