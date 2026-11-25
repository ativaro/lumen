import sys
"""Launch two actual app processes on a private D-Bus, without a real AI backend."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest


def started_with(home):
    """The processes that carry this HOME, by pid and command: all the test started, detached ones included."""
    found = {}
    for entry in Path('/proc').iterdir():
        try:
            if entry.name.isdigit() and f'HOME={home}'.encode() in (entry/'environ').read_bytes().split(b'\0'):
                found[int(entry.name)] = (entry/'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
        except OSError:
            pass
    return found


class DesktopTest(unittest.TestCase):
    def test_relaunch_restores_window_and_preserves_busy_chat_and_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            # A runtime folder of its own: the Lumen service the app starts there ends when it goes.
            os.mkdir(tmp+'/runtime', 0o700)
            environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', XDG_CONFIG_HOME=tmp, XDG_RUNTIME_DIR=tmp+'/runtime',
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
        self.task = self.task_controller.store.create_task('Auftrag aus dem Panel', directory=directory,
                                                      status='completed')
        self.task_controller.store.update_task(self.task, result='Konkretes Ergebnis')
        self.chat.composer.setPlainText('Entwurf bleibt erhalten')
        self.chat.backend.session = 'test-existing-conversation'
        self.chat.backend.busy = True
        self.show_page(9)
        self.showMinimized()
        self.child.finished.connect(self.relaunched)
        self.child.start(sys.executable, [program])
        # Only a bound for a hang: each step goes on as soon as the previous one has happened.
        self.deadline.start(60000)

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
        # The task opens in Lumen System, started detached: it hands the task to this window when it is up.
        self.task_code, self.task_wait = code, QTimer(self)
        self.task_wait.timeout.connect(self.verify_task)
        self.task_wait.start(50)

    def verify_task(self):
        code = self.task_code
        okay = (code == 0 and self.pages.currentIndex() == 0
                and self.system.diagnostics.views.currentIndex() == 1
                and 'Konkretes Ergebnis' in self.system.diagnostics.task_controller.detail.toPlainText()
                and self.chat.composer.toPlainText() == 'Entwurf bleibt erhalten'
                and self.chat.backend.busy)
        if not okay and self.deadline.remainingTime() > 5000: return
        self.task_wait.stop()
        if not okay:
            print('task relaunch', code, self.pages.currentIndex(), self.task_controller.detail.toPlainText(), bytes(self.child.readAllStandardError()).decode(), flush=True)
            self.finish(False)
            return
        # An explicit working directory must still receive its own context window.
        self.child.finished.disconnect(self.task_opened)
        self.child.start(sys.executable, [program, '--directory', directory])
        QTimer.singleShot(500, lambda: self.finish(self.child.state() == QProcess.Running))

desktop.LumenWindow = Probe
sys.exit(desktop.main())
'''
            process = subprocess.Popen(['dbus-run-session', '--', sys.executable, '-c', script, program, tmp],
                                       env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                       start_new_session=True)
            try:
                out, err = process.communicate(timeout=120)
            finally:
                # Each app process runs under its crash supervisor (lumen_crash.supervise), and the probe's kill
                # reaches only the supervisor: end every process this test started.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                # The session ends: its runtime folder goes and with it the Lumen service. Lumen System is
                # started detached, outside that group; having handed over its task it ends by itself. One that
                # stays (it came up after the bus had gone) is ended here and fails the test.
                shutil.rmtree(tmp+'/runtime')
                deadline = time.monotonic() + 10
                while (left := started_with(tmp)) and time.monotonic() < deadline:
                    time.sleep(.1)
                for pid in left:
                    try: os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError: pass
            self.assertEqual(process.returncode, 0, out + err)
            self.assertEqual(left, {}, 'still running after the test')
