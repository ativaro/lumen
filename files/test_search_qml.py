"""Qt 6 pilot runs in its own process: never combine Qt bindings in one app."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class Qt6PilotTest(unittest.TestCase):
    def run_qt6(self, script, timeout=25):
        python = Path.home() / '.local/share/lumen/qt6-env/bin/python'
        if not python.exists(): self.skipTest('Optional Qt 6 pilot runtime is not installed')
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software',
                       XDG_CONFIG_HOME=tmp+'/config', LUMEN_DATA=tmp+'/data',
                       LUMEN_TOOLS_DATA=tmp+'/tools', LUMEN_LANGUAGE='en', LUMEN_CRASH_CHILD='1')
            result = subprocess.run([str(python), '-c', script], cwd=Path(__file__).parent,
                                    env=env, capture_output=True, text=True, timeout=timeout)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            return result

    def test_shared_backend_and_memory_do_not_load_qt5(self):
        self.run_qt6('''
import sys
from PySide6.QtCore import QCoreApplication
app = QCoreApplication([])
from assistant_backend import OpenCodeBackend
from memory_bridge import MemoryBridge
from lumen_jobs import Job
from lumen_tracking import TaskTracker
backend = OpenCodeBackend('/tmp')
bridge = MemoryBridge(backend)
tracker = TaskTracker(backend)
assert not any(k.startswith('PyQt5') for k in sys.modules), [k for k in sys.modules if k.startswith('PyQt5')]
assert backend.new_conversation()
bridge.shutdown(); backend.shutdown()
''')


if __name__ == '__main__': unittest.main()
