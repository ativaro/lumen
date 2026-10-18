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
    def close():
        for window in self.topLevelWidgets():
            window.close()
        QTimer.singleShot(200, self.quit)
    def ready():
        windows = [w for w in self.topLevelWidgets() if w.isVisible() and w.windowTitle().startswith('Lumen')]
        if not windows:
            self.exit(7)
            return
        window = windows[0]
        if os.environ['LUMEN_START_TEST'] == 'notes':
            def rendered(value):
                if value:
                    print('LUMEN_START_READY', flush=True)
                    close()
                else:
                    self.exit(8)
            window.notes_web.page().runJavaScript("!!document.querySelector('.desktop-app-header')", rendered)
        else:
            window.select('backups')
            assert window.tabs.currentWidget() is window.backups
            print('LUMEN_START_READY', flush=True)
            close()
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
            proc = subprocess.Popen(['dbus-run-session','--',str(root/'bin'/name)], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                out, error = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                out, error = proc.communicate(timeout=5)
                self.fail('Launcher did not finish: '+error.decode(errors='replace')[-1500:])
            self.assertEqual(proc.returncode, 0, error.decode(errors='replace')[-3000:])
            self.assertIn(b'LUMEN_START_READY', out)

    def test_notes_launcher_renders_web_editor_and_closes(self):
        self.launch('lumen-wissen','notes')

    def test_system_launcher_opens_backup_page_and_closes(self):
        self.launch('lumen-system','system')


if __name__ == '__main__':
    unittest.main()
