#!/usr/bin/env python3
"""Compare rendered PDF pages between this crate and the Python engine.

usage: compare-render.py <lumen-document> <files dir> <pages per file> <pdf file>...
Both draw the page at the same size. The pictures are reduced to 160 x 200 grey values; a page
is equal when the mean difference is below 1.5 % and fewer than 1 % of the values differ strongly.
Prints counts, the reasons the Rust reader gives for not drawing a page yet, and run times."""
import collections
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

binary, files, limit = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, files)
import lumen_pdf  # noqa: E402
from lumen_pdf_page import Page  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColorSpace, QImage  # noqa: E402


def grey(image):
    # A PNG carries a colour space, and Qt then weighs grey in linear light; both pictures are compared as plain values.
    image = image.convertToFormat(QImage.Format.Format_RGB888); image.setColorSpace(QColorSpace())
    small = image.scaled(160, 200, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_Grayscale8)
    raw = bytes(small.constBits())
    return b''.join(raw[y * small.bytesPerLine():y * small.bytesPerLine() + 160] for y in range(200))


tally = collections.Counter(); reasons = collections.Counter(); worst = []; ours = theirs = 0.0
with tempfile.TemporaryDirectory() as folder:
    target = str(Path(folder) / 'page.png')
    for number, name in enumerate(sys.argv[4:]):
        try: document = lumen_pdf.Document(Path(name))
        except lumen_pdf.PDFError: continue
        for index in range(min(len(document), limit)):
            start = time.perf_counter()
            try: expected = Page(document, index).render(1)
            except lumen_pdf.PDFError: expected = None
            middle = time.perf_counter()
            result = subprocess.run([binary, 'pdf-render', name, str(index), '1', target], capture_output=True, text=True, timeout=300)
            end = time.perf_counter()
            if expected is None:
                tally['python refuses'] += 1; continue
            if result.returncode:
                tally['rust does not draw yet' if 'noch nicht' in result.stderr else 'rust refuses'] += 1; reasons[result.stderr.strip()[:70]] += 1; continue
            theirs += middle - start; ours += end - middle
            actual = QImage(target)
            if actual.size() != expected.size():
                tally['size differs'] += 1; continue
            a, b = grey(actual), grey(expected)
            mean = sum(abs(x - y) for x, y in zip(a, b)) / len(a) / 255
            strong = sum(abs(x - y) > 64 for x, y in zip(a, b)) / len(a)
            if mean < .015 and strong < .01: tally['equal'] += 1
            else: tally['differs'] += 1; worst.append((round(mean, 3), round(strong, 3), number, index))
print(dict(tally))
for reason, count in reasons.most_common(12): print(count, reason)
print('largest differences (mean, strong, file, page):', sorted(worst, reverse=True)[:10])
print(f'pages drawn by both: python {theirs:.1f} s, rust {ours:.1f} s including a process start per page')
