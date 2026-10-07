#!/usr/bin/env python3
"""Measure production QML search renders using synthetic local files."""
import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--samples', type=int, default=5)
parser.add_argument('--child', choices=('qt6',))
args = parser.parse_args()

if not args.child:
    outcomes = {}
    for kind in ('qt6',):
        python = sys.executable
        samples = []
        for _ in range(args.samples):
            result = subprocess.run([python, __file__, '--child', kind], capture_output=True, text=True,
                env=dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', LUMEN_LANGUAGE='en'), timeout=20)
            if result.returncode: raise SystemExit(result.stderr)
            samples.append(json.loads(result.stdout.strip().splitlines()[-1]))
        outcomes[kind] = dict(median={key:round(statistics.median(s[key] for s in samples), 1) for key in samples[0]}, samples=samples)
    print(json.dumps(dict(method='Warm filesystem caches; offscreen software rendering; time from Python imports to first captured frame, RSS after frame, query-to-completed-file-results including 220 ms debounce; 2,000 synthetic files; no LLM request.', results=outcomes), indent=2))
    raise SystemExit()

import time
start = time.perf_counter()
sys.path.insert(0, str(ROOT/'files'))
with tempfile.TemporaryDirectory() as tmp:
    os.environ.update(XDG_CONFIG_HOME=tmp+'/config', LUMEN_DATA=tmp+'/data', LUMEN_TOOLS_DATA=tmp+'/tools')
    directory = Path(tmp)/'documents'; directory.mkdir()
    for index in range(2000): (directory/f'report-{index:04}.txt').touch()
    # Exclude fixture preparation from startup.
    start = time.perf_counter()
    if args.child == 'qt6':
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtTest import QTest
        from search_qml import create_window
        from search_controller import SearchController
        app = QGuiApplication([]); controller = SearchController(directory, applications=[])
        engine, window = create_window(app, controller); window.show(); QTest.qWaitForWindowExposed(window)
        frame = window.grabWindow()
        for _ in range(50):
            if not frame.isNull(): break
            QTest.qWait(1); frame=window.grabWindow()
    if frame.isNull(): raise RuntimeError('No rendered frame')
    rendered = (time.perf_counter()-start)*1000
    rss = int(next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmRSS:')))/1024
    start = time.perf_counter()
    controller.set_query('report-199')
    deadline=time.monotonic()+10
    while (controller.debounce.isActive() or controller.scan_jobs) and time.monotonic()<deadline: QTest.qWait(2)
    if controller.debounce.isActive() or controller.scan_jobs: raise RuntimeError('Search timed out')
    rows = controller.results
    if len(rows) != 11: raise RuntimeError('Expected 10 files and one conversation result')
    search = (time.perf_counter()-start)*1000
    controller.shutdown(); window.hide()
    if args.child == 'qt6': engine.deleteLater()
    QTest.qWait(10)
    print(json.dumps(dict(first_render_ms=round(rendered,1), rss_mib=round(rss,1), search_ms=round(search,1))))
