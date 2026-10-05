"""Cancellable background jobs shared by Qt 5 widgets and Qt 6 controllers."""
from lumen_i18n import worker_environment, tr
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time
from lumen_qt import QThread, Signal
from tools_data import Cancelled


class Job(QThread):
    result = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent); self.function = function; self.cancelled = threading.Event()

    def check(self):
        if self.cancelled.is_set(): raise Cancelled('Abgebrochen')

    def command(self, args, data=None, timeout=300, max_output=2*1024**2):
        self.check()
        # Files prevent large decoder/model stderr output from filling RAM or a pipe.
        # Password-bearing stdin must not become a disk-backed temporary file.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr, os.fdopen(os.memfd_create('lumen-job-input', os.MFD_CLOEXEC), 'w+b') as stdin:
            if data: stdin.write(data); stdin.seek(0)
            proc = subprocess.Popen(args, env=worker_environment(), stdin=stdin, stdout=stdout, stderr=stderr, start_new_session=True)
            started = time.monotonic()
            try:
                while proc.poll() is None:
                    self.check()
                    if time.monotonic()-started > timeout: raise ValueError(tr('Die Verarbeitung hat zu lange gedauert.'))
                    self.cancelled.wait(.1)
                self.check()
                if proc.returncode:
                    stderr.seek(max(0, stderr.tell()-3000))
                    raise ValueError(f'{Path(args[0]).name}: ' + stderr.read(3000).decode(errors='replace').strip())
                stdout.seek(0); output = stdout.read(max_output+1)
                if len(output) > max_output: raise ValueError(tr('Verarbeitungsergebnis zu groß.'))
                return output
            finally:
                if proc.poll() is None:
                    try: os.killpg(proc.pid, signal.SIGTERM)
                    except ProcessLookupError: pass
                    try: proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        try: os.killpg(proc.pid, signal.SIGKILL)
                        except ProcessLookupError: pass
                        proc.wait()

    def run(self):
        try: self.result.emit(self.function(self))
        except Exception as error: self.failed.emit(str(error) or type(error).__name__)

