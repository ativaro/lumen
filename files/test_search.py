"""Production search entry point, external themes and checkpoint migration."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class SearchTest(unittest.TestCase):
    def run_search(self, script):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(['dbus-run-session', '--', sys.executable, '-c', script],
                cwd=Path(__file__).parent, timeout=15, capture_output=True, text=True,
                env=os.environ | {'HOME':tmp, 'XDG_CONFIG_HOME':tmp+'/config',
                    'LUMEN_DATA':tmp+'/state', 'LUMEN_TOOLS_DATA':tmp+'/tools',
                    'QT_QPA_PLATFORM':'offscreen', 'QT_QUICK_BACKEND':'software', 'LUMEN_CRASH_CHILD':'1'})
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_resident_search_tracks_external_themes_and_refreshes_on_activation(self):
        self.run_search('''
import subprocess,sys,time
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from search_controller import SearchController
from search_qml import create_window, Activation
app=QGuiApplication([]);c=SearchController(applications=[])
engine,w=create_window(app,c);activation=Activation(w,c)
c.restore_recovery({'conversation':True,'chat':{'session':'preserved','draft':'keep draft'}})
def save(theme):
 subprocess.run([sys.executable,'-c',"from PySide6.QtCore import QSettings;s=QSettings('Lumen','Assistant');s.setValue('appearance',"+repr(theme)+");s.sync()"],check=True)
try:
 for name in ('glass','graphite','atelier','midnight'):
  save(name);deadline=time.monotonic()+2
  while c.theme['name']!=name and time.monotonic()<deadline:QTest.qWait(10)
  assert c.theme['name']==name,name
  assert c.query=='keep draft' and c.backend.session=='preserved'
 c.watcher.blockSignals(True);save('atelier');activation.Activate()
 assert c.theme['name']=='atelier' and c.query=='keep draft'
finally:c.shutdown();w.hide();engine.deleteLater();QTest.qWait(10)
''')


if __name__ == '__main__': unittest.main()
