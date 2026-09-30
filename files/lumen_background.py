"""Read-only CLI analysis using the same privacy, resource and task policies as Lumen."""
import argparse
from pathlib import Path
import sys
from PyQt5.QtCore import QCoreApplication
from assistant_backend import OpenCodeBackend
from lumen_store import Store
from lumen_tasks import defer_background
from lumen_tracking import TaskTracker


def main():
    parser = argparse.ArgumentParser(description='Lumen-Hintergrundanalyse')
    parser.add_argument('-m', '--model', default='')
    parser.add_argument('--foreground', action='store_true')
    parser.add_argument('prompt')
    args = parser.parse_args(); app = QCoreApplication([]); store = Store()
    reason = '' if args.foreground else defer_background(store)
    if reason: print('Lumen: ' + reason); return 1
    backend = OpenCodeBackend(str(Path.cwd()), project_config=False)
    tracker = TaskTracker(backend, store=store)
    backend.background_task = not args.foreground
    backend.selected_model = args.model
    backend.read_only = True
    def done(success, result):
        print(result if success else 'Lumen: ' + result)
        backend.shutdown(); app.exit(0 if success else 1)
    backend.completed.connect(done)
    # Enter the event loop before a synchronous validation failure may occur.
    from PyQt5.QtCore import QTimer
    QTimer.singleShot(0, lambda: backend.send(args.prompt, agent='plan'))
    result = app.exec_(); tracker.interrupt(); backend.shutdown(); return result


if __name__ == '__main__': sys.exit(main())
