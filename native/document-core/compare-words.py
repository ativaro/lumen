#!/usr/bin/env python3
"""Compare the words of PDF pages between this crate and the Python engine.

usage: compare-words.py <lumen-document> <files dir> <pages per file> <pdf file>...
A page is equal when both give the same words in the same order and lines, with positions within
half a pixel. Pages the Python engine refuses are counted apart: the text pass here does not check
drawing. Prints counts and the kind of each difference, no document content."""
import collections
import json
import os
import subprocess
import sys
from pathlib import Path

binary, files, limit = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, files)
import lumen_pdf  # noqa: E402
from lumen_pdf_page import Page  # noqa: E402

tally = collections.Counter(); kinds = collections.Counter(); where = []
for number, name in enumerate(sys.argv[4:]):
    try: document = lumen_pdf.Document(Path(name))
    except lumen_pdf.PDFError: continue
    result = subprocess.run([binary, 'pdf-words', name, '0', str(limit)], capture_output=True, text=True, timeout=600)
    if result.returncode: tally['rust could not open'] += 1; continue
    pages = json.loads(result.stdout)
    for index, actual in enumerate(pages):
        try: expected = Page(document, index); words = expected.words
        except lumen_pdf.PDFError as error:
            tally['python refuses, rust reads' if 'words' in actual else 'both refuse'] += 1; continue
        if 'error' in actual:
            tally['rust refuses']+=1; kinds[actual['error'][:60]] += 1; where.append((number, index)); continue
        ours = actual['words']
        if [w[4] for w in ours] != [w[4] for w in words]:
            tally['text differs'] += 1; kinds[f'text: {len(ours)} vs {len(words)} words' if len(ours) != len(words) else 'text: same count, other words or order'] += 1; where.append((number, index)); continue
        if [w[5] for w in ours] != [w[6] for w in words]:
            tally['lines differ'] += 1; where.append((number, index)); continue
        worst = max((abs(a - b) for w, v in zip(ours, words) for a, b in zip(w[:4], v[:4])), default=0)
        size = max(abs(actual['width'] - expected.width), abs(actual['height'] - expected.height))
        if worst > .5 or size > 1e-6:
            tally['positions differ'] += 1; kinds[f'position off by up to {worst:.1f} px'] += 1; where.append((number, index)); continue
        tally['equal'] += 1
print(dict(tally))
for kind, count in kinds.most_common(12): print(count, kind)
print('first differing (file, page):', where[:12])
sys.exit(0 if set(tally) <= {'equal', 'python refuses, rust reads', 'both refuse'} else 1)
