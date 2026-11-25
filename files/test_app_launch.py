"""Real shell launchers must map Notes/System and close with disposable data."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest

# Test-only observer: use the real startup path, event loop, rendering and shutdown.
OBSERVER = '''
import os
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
original = QApplication.exec

def observed_exec(self):
    def ready():
        windows = [w for w in self.topLevelWidgets() if w.isVisible() and w.windowTitle().startswith('Lumen')]
        assert windows
        window = windows[0]
        if getattr(window,'job',None) or getattr(window,'poller',None):
            QTimer.singleShot(30,ready)
            return
        if os.environ['LUMEN_START_TEST'] == 'memory':
            assert window.memory_only and window.area == 'lumen' and window.book
        else:
            window.select('updates')
            assert window.tabs.currentWidget() is window.updates
        print('LUMEN_START_READY', flush=True)
        def finish():
            window.close()
            if window.isVisible():QTimer.singleShot(50,finish)
            else:self.quit()
        finish()
    QTimer.singleShot(1500, ready)
    return original()

QApplication.exec = observed_exec
'''


class AppLaunchTest(unittest.TestCase):
    def launch(self, name, kind):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='lumen-app-start-') as tmp:
            path = Path(tmp)
            (path/'sitecustomize.py').write_text(OBSERVER)
            env = {**os.environ, 'QT_QPA_PLATFORM':'offscreen', 'QTWEBENGINE_DISABLE_SANDBOX':'1',
                   'LUMEN_DATA':str(path/'state'), 'LUMEN_TOOLS_DATA':str(path/'tools'),
                   'XDG_CONFIG_HOME':str(path/'config'), 'XDG_CACHE_HOME':str(path/'cache'),
                   'XDG_DATA_HOME':str(path/'data'), 'PYTHONPATH':str(path),
                   'PYTHONFAULTHANDLER':'1', 'LUMEN_LANGUAGE':'de', 'LUMEN_START_TEST':kind}
            proc = subprocess.Popen(['dbus-run-session','--',str(root/'bin'/name),*(['--area','lumen'] if kind=='memory' else [])], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                out, error = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                out, error = proc.communicate(timeout=5)
                self.fail('Launcher did not finish: '+error.decode(errors='replace')[-1500:])
            self.assertEqual(proc.returncode, 0, (out+error).decode(errors='replace')[-4000:])
            self.assertIn(b'LUMEN_START_READY', out)

    def test_memory_launcher_opens_retained_native_memory_and_closes(self):
        self.launch('lumen-wissen','memory')

    def test_system_launcher_opens_updates_page_and_closes(self):
        self.launch('lumen-system','system')


if __name__ == '__main__':
    unittest.main()
