#!/usr/bin/env python3
"""Compare this crate's PDF structure reading with the Python engine, file by file.

usage: compare-pdf.py <lumen-document> <files dir with lumen_pdf.py> <pdf file>...
Equal means: same page count, title, outline, page boxes and decoded page content (length and
checksum), or both readers refuse the file with the same message. Prints outcomes and run times only."""
import json
import subprocess
import sys
import time
import zlib
from pathlib import Path

binary, files = sys.argv[1], sys.argv[2]
sys.path.insert(0, files)
import lumen_pdf  # noqa: E402

different = 0
for name in sys.argv[3:]:
    start = time.perf_counter()
    try:
        document = lumen_pdf.Document(Path(name))
        content = []
        for index, page in enumerate(document.pages):
            data = document.contents(index)
            content.append(dict(box=[float(v) for v in page['MediaBox']], length=len(data), print=zlib.crc32(data)))
        expected = dict(pages=len(document), title=document.metadata.get('title') or '', toc=document.toc(), content=content)
    except lumen_pdf.PDFError as error: expected = dict(error=str(error))
    middle = time.perf_counter()
    result = subprocess.run([binary, 'pdf-info', name], capture_output=True, text=True, timeout=300)
    actual = json.loads(result.stdout) if result.returncode == 0 else dict(error=result.stderr.strip())
    end = time.perf_counter()
    same = actual == expected
    different += not same
    where = ''
    if not same:
        if 'error' in actual or 'error' in expected: where = f' rust {str(actual.get("error", "ok"))[:70]!r} python {str(expected.get("error", "ok"))[:70]!r}'
        else:
            keys = [key for key in ('pages', 'title', 'toc') if actual[key] != expected[key]]
            page = next((i for i, (a, b) in enumerate(zip(actual['content'], expected['content'])) if a != b), None)
            where = f' differs in {keys} first page {page}' + (f' rust {actual["content"][page]} python {expected["content"][page]}' if page is not None else '')
    print('same' if same else 'DIFFERENT', f'pages {expected.get("pages", "-")}', f'python {round((middle - start) * 1000)} ms', f'rust {round((end - middle) * 1000)} ms', where)
print(f'{len(sys.argv) - 3 - different} of {len(sys.argv) - 3} equal')
sys.exit(1 if different else 0)
