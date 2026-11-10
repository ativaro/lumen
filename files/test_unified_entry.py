"""One public Lumen entry, with retained state across real activation routes."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class UnifiedEntryTest(unittest.TestCase):
    def test_cold_start_and_legacy_routes_share_one_conversation(self):
        program = Path(__file__).resolve().parents[1] / 'agent-app/main.py'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'runtime').mkdir(mode=0o700)
            env = dict(os.environ, HOME=tmp, XDG_RUNTIME_DIR=str(root/'runtime'),
                       XDG_CONFIG_HOME=str(root/'config'), XDG_DATA_HOME=str(root/'data'),
                       XDG_CACHE_HOME=str(root/'cache'), XDG_STATE_HOME=str(root/'state'),
                       LUMEN_DATA=str(root/'state'), LUMEN_TOOLS_DATA=str(root/'tools'),
                       LUMEN_LANGUAGE='de', LUMEN_CRASH_CHILD='1',
                       LUMEN_OPENCODE_BIN='/nonexistent/test-engine',
                       QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software')
            script = r'''
import importlib.util, sys, traceback
from unittest.mock import patch
from PySide6.QtCore import QProcess, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
spec=importlib.util.spec_from_file_location('desktop',sys.argv[1]);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
program=sys.argv[1];sys.argv=[program]
Original=d.LumenWindow
class Probe(Original):
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs);QTimer.singleShot(150,self.check)
 def check(self):
  status=0
  try:
   assert self.search_window.isVisible() and not self.isVisible()
   assert self.search_window.title()=='Lumen'
   self.chat.composer.setPlainText('Keep this unsent draft')
   backend=self.chat.backend;backend.session='same-conversation';backend.busy=True
   backend.permissions=[dict(id='approval',permission='read',patterns=['fixture'])]
   backend.requestsChanged.emit(backend.permissions,[])
   self.search_controller.expand()
   assert self.isVisible() and not self.search_window.isVisible()
   assert self.windowTitle()=='Lumen · Detailansicht'
   QTest.mouseClick(self.context_compact,d.Qt.LeftButton)
   assert self.search_window.isVisible() and not self.isVisible()
   for args,compact in [(['--details'],False),([],True),(['--page','apps'],True),(['--search'],True)]:
    child=QProcess();child.start(sys.executable,[program,*args])
    for _ in range(200):
     QTest.qWait(25)
     if child.state()==QProcess.NotRunning:break
    assert child.state()==QProcess.NotRunning,'activation timed out'
    assert child.exitCode()==0,bytes(child.readAllStandardError()).decode()
    assert self.search_window.isVisible()==compact and self.isVisible()!=compact,args
    assert backend.session=='same-conversation' and backend.busy
    assert self.chat.composer.toPlainText()=='Keep this unsent draft'
    assert self.search_controller.permissions[0]['id']=='approval'
   QTest.keyClick(self.search_window,d.Qt.Key_Escape)
   assert not self.search_window.isVisible() and backend.busy
   self.open_search();assert self.search_window.isVisible()
   from lumen_apps import catalogue
   from lumen_panel import applications
   assert len(catalogue())==8 and 'search' not in [row[0] for row in catalogue()]
   assert 'search' not in [row['id'] for row in applications()]
  except Exception:
   traceback.print_exc();status=1
  finally:
   self.chat.backend.busy=False;self.close();QApplication.instance().exit(status)
d.LumenWindow=Probe
with patch('desktop_backend.DesktopBackend.refresh_sessions'),patch('setup_dialog.offer_setup'):
 sys.exit(d.main())
'''
            result = subprocess.run(['dbus-run-session', '--', sys.executable, '-c', script, str(program)],
                                    env=env, capture_output=True, text=True, timeout=35)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
