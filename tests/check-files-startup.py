#!/usr/bin/env python3
"""Time the real Files launcher through the first populated paint, in a disposable profile."""
import argparse
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import tempfile
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, default=Path(__file__).resolve().parents[1]/'bin/lumen-files')
parser.add_argument('--platform', default='offscreen')
parser.add_argument('--samples', type=int, default=7)
parser.add_argument('--budget-ms', type=float, default=1000)
args = parser.parse_args()
assert args.samples > 0

# Test-only instrumentation: leave the production launcher, interpreter choice,
# crash supervisor and app entry point in the measured path. No production hooks.
probe = '''
import os, sys
if sys.argv[0].endswith('/app.py') and os.environ.get('LUMEN_GUARD_PID'):
    import json, time
    from PySide6.QtCore import QObject, QEvent, QTimer
    from PySide6.QtWidgets import QApplication, QTreeView
    original = QApplication.exec
    def measured_exec(app):
        class Observe(QObject):
            ready = False
            def eventFilter(self, obj, event):
                if self.ready or event.type() != QEvent.Paint:
                    return False
                view = obj.parent()
                if (isinstance(view, QTreeView) and view.objectName() == 'files'
                        and view.model().rowCount(view.rootIndex()) == 250):
                    self.ready = True
                    def finish():
                        elapsed = (time.perf_counter_ns() - int(os.environ['LUMEN_BENCH_START_NS'])) / 1e6
                        print(json.dumps(dict(ready_ms=round(elapsed, 2))), flush=True)
                        app.quit()
                    # Measure after the paint and another GUI event, not window.show().
                    QTimer.singleShot(0, finish)
                return False
        observer = Observe()
        app.installEventFilter(observer)
        QTimer.singleShot(10000, app.quit)
        return original()
    QApplication.exec = measured_exec
'''

with tempfile.TemporaryDirectory(prefix='lumen-files-startup-') as tmp:
    root = Path(tmp)
    config = root/'config/Lumen'
    config.mkdir(parents=True)
    (config/'Assistant.conf').write_text('[General]\nsetupSeen=true\nuiLanguage=de\ncrashDetection=true\n')
    folder = root/'listing'
    folder.mkdir()
    for index in range(250):
        (folder/f'document-{index:03}.txt').write_text('Startup fixture\n')
    (root/'sitecustomize.py').write_text(probe)
    env = dict(os.environ, QT_QPA_PLATFORM=args.platform, QT_QUICK_BACKEND='software',
               XDG_CONFIG_HOME=str(root/'config'), XDG_DATA_HOME=str(root/'data'),
               XDG_STATE_HOME=str(root/'state'), XDG_CACHE_HOME=str(root/'cache'),
               LUMEN_DATA=str(root/'state/lumen'), LUMEN_TOOLS_DATA=str(root/'tools'),
               PYTHONPATH=str(root))
    for key in ('LUMEN_LANGUAGE', 'LUMEN_PYTHON', 'LUMEN_CRASH_RUN', 'LUMEN_GUARD_PID',
                'LUMEN_CRASH_LOCK', 'LUMEN_HEARTBEAT_FD'):
        env.pop(key, None)
    samples = []
    for index in range(args.samples + 1):
        env['LUMEN_BENCH_START_NS'] = str(time.perf_counter_ns())
        process = subprocess.Popen([str(args.binary.resolve()), str(folder)], env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, start_new_session=True)
        try:
            output, _ = process.communicate(timeout=15)
            assert process.returncode == 0, output
            result = next((json.loads(line) for line in output.splitlines()
                           if line.startswith('{"ready_ms":')), None)
            assert result, 'No populated paint: ' + output
            if index: samples.append(result['ready_ms'])
        except BaseException:
            for log in (root/'state/lumen/crashes').glob('*/stderr.log'):
                print(log.read_text(errors='replace')[-4000:])
            raise
        finally:
            # Only this benchmark's process group, including a failed crash notice.
            try: os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    median = statistics.median(samples)
    print(json.dumps(dict(binary=str(args.binary), platform=args.platform,
                          samples_ms=samples, median_ms=median, maximum_ms=max(samples))))
    assert max(samples) <= args.budget_ms, f'Startup exceeded {args.budget_ms:g} ms'
