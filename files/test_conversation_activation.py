"""Compact entry reaches the same desktop process and expands without submitting."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class ActivationTest(unittest.TestCase):
    def test_compact_then_full_relaunch_keeps_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            program=Path(__file__).resolve().parents[1]/'agent-app/main.py'
            env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software',XDG_CONFIG_HOME=tmp,
                     LUMEN_DATA=tmp+'/state',LUMEN_TOOLS_DATA=tmp+'/tools',LUMEN_OPENCODE_BIN='/nonexistent/lumen-test-engine',LUMEN_CRASH_CHILD='1')
            script=r'''
import importlib.util,sys
from unittest.mock import patch
from PySide6.QtCore import QTimer,QProcess
from PySide6.QtWidgets import QApplication
from PySide6.QtQuickControls2 import QQuickStyle
spec=importlib.util.spec_from_file_location('desktop',sys.argv[1]);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
QQuickStyle.setStyle('Basic')
from app import create_app
app=create_app();app.setQuitOnLastWindowClosed(False)
from PySide6.QtDBus import QDBusConnection
with patch('desktop_backend.DesktopBackend.refresh_sessions'):
 w=d.LumenWindow(sys.argv[2]);activation=d.DesktopActivation();activation.window=w
 bus=QDBusConnection.sessionBus();assert bus.registerService('org.lumen.Desktop');assert bus.registerObject('/Lumen',activation,QDBusConnection.ExportAllSlots)
 w.chat.composer.setPlainText('Persistent draft');w.chat.backend.session='single';w.chat.backend.busy=True
 with patch('lumen_detail_routes.launch') as launch:
  w.show_page(11);assert launch.call_args.args==('lumen-companion',[])
  assert activation.ActivateHousehold('{}')
  assert launch.call_args.args==('lumen-workbench',['--section','household'])
  from interop_data import Registry
  from tools_data import Library
  import json
  library=Library('household');key=library.create('Preserved contract',kind='Vertrag',attachments=[],notes='')
  ref=Registry(library.root.parent).register(dict(app='household',kind='record',id=key,title='Preserved contract'))
  assert activation.ActivateHousehold(json.dumps({'ref':ref}))
  assert launch.call_args.args==('lumen-workbench',['--section','household','--ref',ref])
  assert not activation.ActivateHousehold('{"path":"invalid"}')
 assert w.chat.backend.busy and w.chat.composer.toPlainText()=='Persistent draft'
 w.show_page(0)
 w.open_search();assert w.search_controller.backend is w.chat.backend
 w.search_controller.expand();assert w.isVisible() and not w.search_window.isVisible()
 child=QProcess();failures=[]
 def done(code,*args):
  try:
   assert code==0,bytes(child.readAllStandardError()).decode()
   assert w.search_window.isVisible() and w.chat.backend.busy
   assert w.search_controller.query=='Persistent draft' and w.chat.backend.session=='single'
   w.search_controller.expand();assert not w.search_window.isVisible()
  except Exception as e:failures.append(repr(e))
  w.chat.backend.busy=False;w.close();app.exit(1 if failures else 0)
 child.finished.connect(done);child.start(sys.executable,[sys.argv[1],'--search'])
 QTimer.singleShot(8000,lambda:app.exit(2));result=app.exec();print(failures);sys.exit(result)
'''
            result=subprocess.run(['dbus-run-session','--','python','-c',script,str(program),tmp],env=env,capture_output=True,text=True,timeout=12)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
