"""Launch two actual app processes on a private D-Bus, without a real AI backend."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class DesktopTest(unittest.TestCase):
    def test_relaunch_restores_window_and_preserves_busy_chat_and_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', XDG_CONFIG_HOME=tmp,
                               LUMEN_OPENCODE_BIN='/nonexistent/lumen-test-engine')
            environment.pop('LUMEN_ASK_PROMPT', None)
            program = str(Path(__file__).resolve().parents[1] / 'agent-app/main.py')
            script = r'''
import importlib.util
import sys
from PyQt5.QtCore import QProcess, QTimer
from PyQt5.QtWidgets import QApplication
spec = importlib.util.spec_from_file_location('desktop', sys.argv[1])
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)
program, directory = sys.argv[1:]
sys.argv = [program]

class Probe(desktop.LumenWindow):
    def __init__(self, path):
        super().__init__(path)
        self.child = QProcess(self)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(lambda: self.finish(False))
        QTimer.singleShot(100, self.probe)

    def finish(self, okay):
        self.deadline.stop()
        self.child.blockSignals(True)
        if self.child.state() != QProcess.NotRunning:
            self.child.kill()
            self.child.waitForFinished(1000)
        self.chat.backend.busy = False
        self.close()
        QApplication.exit(0 if okay else 1)

    def probe(self):
        self.chat.composer.setPlainText('Entwurf bleibt erhalten')
        self.chat.backend.session = 'test-existing-conversation'
        self.chat.backend.busy = True
        self.showMinimized()
        self.child.finished.connect(self.relaunched)
        self.child.start(sys.executable, [program])
        self.deadline.start(5000)

    def relaunched(self, code, status):
        okay = (code == 0 and not self.isMinimized() and self.isVisible()
                and self.chat.composer.toPlainText() == 'Entwurf bleibt erhalten'
                and self.chat.backend.session == 'test-existing-conversation'
                and self.chat.backend.busy)
        if not okay:
            self.finish(False)
            return
        # An explicit working directory must still receive its own context window.
        self.child.finished.disconnect(self.relaunched)
        self.child.start(sys.executable, [program, '--directory', directory])
        QTimer.singleShot(500, lambda: self.finish(self.child.state() == QProcess.Running))

desktop.LumenWindow = Probe
sys.exit(desktop.main())
'''
            result = subprocess.run(['dbus-run-session', '--', '/usr/bin/python3', '-c', script, program, tmp],
                                    env=environment, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
