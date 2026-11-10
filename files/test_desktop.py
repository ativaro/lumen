import sys
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
                               HOME=tmp, LUMEN_CRASH_CHILD='1', LUMEN_TOOLS_DATA=tmp+'/tools',
                               LUMEN_DATA=tmp + '/state', LUMEN_OPENCODE_BIN='/nonexistent/lumen-test-engine')
            environment.pop('LUMEN_ASK_PROMPT', None)
            program = str(Path(__file__).resolve().parents[1] / 'agent-app/main.py')
            script = r'''
import importlib.util
import sys
from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QApplication
spec = importlib.util.spec_from_file_location('desktop', sys.argv[1])
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)
program, directory = sys.argv[1:]
sys.argv = [program]
import setup_dialog
setup_dialog.offer_setup = lambda *_: None
from desktop_backend import DesktopBackend
DesktopBackend.refresh_sessions = lambda *_: None

class Probe(desktop.LumenWindow):
    def __init__(self, path):
        super().__init__(path)
        from system_app import SystemController, Activation
        from system_window import SystemWindow
        from tools_sound import Sound
        from PySide6.QtDBus import QDBusConnection
        Sound.poll = lambda *_: None
        self.system = SystemWindow(SystemController(start=False))
        self.system_activation = Activation(self.system)
        bus = QDBusConnection.sessionBus()
        assert bus.registerObject('/System',self.system_activation,QDBusConnection.ExportAllSlots)
        assert bus.registerService('org.lumen.System')
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
        self.system.close(); self.close()
        QApplication.exit(0 if okay else 1)

    def probe(self):
        self.task = self.work_pages.store.create_task('Auftrag aus dem Panel', directory=directory,
                                                      status='completed')
        self.work_pages.store.update_task(self.task, result='Konkretes Ergebnis')
        self.chat.composer.setPlainText('Entwurf bleibt erhalten')
        self.chat.backend.session = 'test-existing-conversation'
        self.chat.backend.busy = True
        self.show_page(9)
        self.showMinimized()
        self.child.finished.connect(self.relaunched)
        self.child.start(sys.executable, [program])
        self.deadline.start(5000)

    def relaunched(self, code, status):
        okay = (code == 0 and self.search_window.isVisible() and not self.isVisible()
                and self.pages.currentIndex() == 0
                and self.chat.composer.toPlainText() == 'Entwurf bleibt erhalten'
                and self.chat.backend.session == 'test-existing-conversation'
                and self.chat.backend.busy)
        if not okay:
            print('compact relaunch', code, self.search_window.isVisible(), self.isVisible(), self.pages.currentIndex(), bytes(self.child.readAllStandardError()).decode(), flush=True)
            self.finish(False)
            return
        self.child.finished.disconnect(self.relaunched)
        self.child.finished.connect(self.task_opened)
        self.child.start(sys.executable, [program, '--task', self.task])

    def task_opened(self, code, status):
        QTimer.singleShot(300, lambda: self.verify_task(code))

    def verify_task(self, code):
        okay = (code == 0 and self.pages.currentIndex() == 0
                and self.system.diagnostics.views.currentIndex() == 1
                and 'Konkretes Ergebnis' in self.system.diagnostics.work_pages.detail.toPlainText()
                and self.chat.composer.toPlainText() == 'Entwurf bleibt erhalten'
                and self.chat.backend.busy)
        if not okay:
            print('task relaunch', code, self.pages.currentIndex(), self.work_pages.detail.toPlainText(), bytes(self.child.readAllStandardError()).decode(), flush=True)
            self.finish(False)
            return
        # An explicit working directory must still receive its own context window.
        self.child.finished.disconnect(self.task_opened)
        self.child.start(sys.executable, [program, '--directory', directory])
        QTimer.singleShot(500, lambda: self.finish(self.child.state() == QProcess.Running))

desktop.LumenWindow = Probe
sys.exit(desktop.main())
'''
            result = subprocess.run(['dbus-run-session', '--', sys.executable, '-c', script, program, tmp],
                                    env=environment, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
