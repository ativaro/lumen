"""Super toggle preserves drafts/work and ignores games, on a private session bus."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class SuperToggleTest(unittest.TestCase):
    def test_cold_warm_game_and_dialog_paths(self):
        program=Path(os.environ.get('LUMEN_TEST_PROGRAM',str(Path(__file__).resolve().parents[1]/'agent-app/main.py')))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'runtime').mkdir(mode=0o700)
            env=dict(os.environ, HOME=tmp, XDG_RUNTIME_DIR=str(root/'runtime'),
                XDG_CONFIG_HOME=str(root/'config'), XDG_DATA_HOME=str(root/'data'),
                XDG_CACHE_HOME=str(root/'cache'), XDG_STATE_HOME=str(root/'state'),
                LUMEN_DATA=str(root/'state'), LUMEN_TOOLS_DATA=str(root/'tools'),
                LUMEN_CRASH_CHILD='1', LUMEN_ASK_PROMPT='Never send this inherited prompt', LUMEN_OPENCODE_BIN='/nonexistent/test-engine',
                QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software')
            result=subprocess.run(['dbus-run-session','--',sys.executable,'-c',PROBE,str(program)],
                env=env,capture_output=True,text=True,timeout=45)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)


PROBE=r'''
import importlib.util,sys,traceback
from unittest.mock import patch
from PySide6.QtCore import QTimer,QProcess
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialog
program=sys.argv[1]
spec=importlib.util.spec_from_file_location('desktop',program);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
sys.argv=[program,'--toggle']
with patch('lumen_hardware.activity',return_value=['Steam-Spiel']),patch.object(d,'create_app') as create:
 assert d.main()==0
 create.assert_not_called()
with patch('lumen_hardware.activity',return_value=[]):
 pending=d.DesktopActivation();pending.Toggle();assert pending.pending_toggle
 pending.Toggle();assert not pending.pending_toggle
 pending.window=object();pending.starting=True;pending.Toggle();assert pending.pending_toggle
Original=d.LumenWindow
class Probe(Original):
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs);QTimer.singleShot(200,self.check)
 def check(self):
  status=0
  try:
   assert self.search_window.isVisible() and not self.isVisible()
   self.chat.composer.setPlainText('Unsent draft');backend=self.chat.backend
   backend.session='keep-session';backend.busy=True
   activation=d.DesktopActivation();activation.window=self
   for activity in ['Steam-Spiel','GameMode-Spiel','Gamescope-Sitzung']:
    with patch('lumen_hardware.activity',return_value=[activity]):activation.Toggle()
    assert self.search_window.isVisible()
   activation.Toggle();assert not self.search_window.isVisible()
   with patch('lumen_hardware.activity',return_value=['Steam-Spiel']):activation.Toggle()
   assert not self.search_window.isVisible()
   activation.Toggle();assert self.search_window.isVisible()
   for visible in [False,True]:
    child_code="import importlib.util,sys;from unittest.mock import patch;s=importlib.util.spec_from_file_location('d',sys.argv[1]);d=importlib.util.module_from_spec(s);s.loader.exec_module(d);sys.argv=[sys.argv[1],'--toggle'];p=patch('lumen_hardware.activity',return_value=[]);p.start();sys.exit(d.main())"
    child=QProcess();child.start(sys.executable,['-c',child_code,program])
    for _ in range(300):
     QTest.qWait(20)
     if child.state()==QProcess.NotRunning:break
    assert child.state()==QProcess.NotRunning,'secondary launch timed out'
    assert child.exitCode()==0,bytes(child.readAllStandardError()).decode()
    assert self.search_window.isVisible()==visible
    assert backend.session=='keep-session' and backend.busy
    assert self.chat.composer.toPlainText()=='Unsent draft'
   self.search_controller.expand();assert self.isVisible()
   dialog=QDialog(self);dialog.setModal(True);dialog.show();QTest.qWait(30)
   activation.Toggle();assert dialog.isVisible() and self.isVisible()
   dialog.reject();QTest.qWait(20)
   activation.Toggle();assert not self.isVisible()
   activation.Toggle();assert self.search_window.isVisible()
   assert backend.busy and self.chat.composer.toPlainText()=='Unsent draft'
  except BaseException:traceback.print_exc();status=1
  self.chat.backend.busy=False;self.chat.composer.clear();self.close();QApplication.instance().exit(status)
d.LumenWindow=Probe
with patch('lumen_hardware.activity',return_value=[]),patch('setup_dialog.offer_setup'),patch('lumen_crash.attach'),patch('desktop_backend.DesktopBackend.refresh_sessions'):
 sys.exit(d.main())
'''
