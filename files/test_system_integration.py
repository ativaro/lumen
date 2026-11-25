"""Retained System sections and compatible native Sound activation."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication
from system_app import SystemController
from system_window import SystemWindow
from lumen_store import Store


class SystemIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.app = QApplication.instance() or create_app()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.poll = patch('tools_sound.Sound.poll'); self.poll.start()
        self.controller = SystemController(start=False)
        self.window = SystemWindow(self.controller, root=self.root/'tools', store=Store(self.root/'state'))
        self.window.show(); self.app.processEvents()

    def tearDown(self):
        self.window.sound.job = None
        self.window.close(); self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.controller.deleteLater(); self.app.processEvents()
        self.poll.stop(); self.temp.cleanup()

    def test_tabs_retain_audio_controls_and_system_navigation(self):
        root = self.window.system.rootObject(); self.assertIsNotNone(root)
        root.setProperty('page', 2)
        self.window.select('sound'); self.window.sound.tabs.setCurrentIndex(1)
        self.window.sound.level.setValue(37); self.window.sound.duck.setChecked(True)
        self.window.select('diagnostics'); self.window.select('system'); self.window.select('sound')
        self.assertEqual(root.property('page'), 2)
        self.assertEqual(self.window.sound.tabs.currentIndex(), 1)
        self.assertEqual(self.window.sound.level.value(), 37)
        self.assertTrue(self.window.sound.duck.isChecked())
        with self.assertRaises(ValueError): self.window.select('invalid')
        self.assertEqual(sum(w.isVisible() for w in self.app.topLevelWidgets()), 1)

    def test_close_waits_for_changes_and_save_errors(self):
        self.window.sound.job = Mock()
        event = QCloseEvent(); self.window.closeEvent(event)
        self.assertFalse(event.isAccepted()); self.assertFalse(self.controller.closing)
        self.window.sound.job = None
        with patch.object(self.window.sound, 'save', side_effect=OSError('disk full')), patch.object(self.window.sound, 'error'):
            event = QCloseEvent(); self.window.closeEvent(event)
            self.assertFalse(event.isAccepted()); self.assertFalse(self.controller.closing)

    def test_legacy_sound_route_and_settings_use_system(self):
        from lumen_apps import catalogue, launch
        from settings_dialog import SettingsDialog
        self.assertNotIn('sound', [item[0] for item in catalogue()])
        with patch('lumen_apps.QProcess.startDetached', return_value=(True, 42)) as start:
            launch('sound'); self.assertTrue(start.call_args.args[0].endswith('lumen-system'))
            self.assertEqual(start.call_args.args[1], ['--page', 'sound'])
            launch('system', page='server'); self.assertEqual(start.call_args.args[1], ['--page', 'server'])
            with self.assertRaises(ValueError): launch('system', page='modes')
        with self.assertRaises(ValueError): launch('files', page='server')
        dialog = SettingsDialog(application='sound', load_system=False)
        self.assertEqual(dialog.stack.currentIndex(), dialog.app_pages['system'])
        self.assertIn('sound', dialog.app_controls); self.assertIn('system', dialog.app_controls)
        dialog.deleteLater()

    def test_real_process_activation_and_sound_endpoint(self):
        code = r'''
import json, os, subprocess, sys, time
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalSocket
from tools_app import server_name
app = QCoreApplication([])
folder = Path(os.environ['TEST_ROOT']); log = folder/'pages'
runner = folder/'runner.py'
runner.write_text("from pathlib import Path\nfrom tools_sound import Sound\nSound.poll=lambda self:None\nfrom system_app import SystemController,main\nSystemController.start=lambda self:None\nfrom system_window import SystemWindow\noriginal=SystemWindow.select\ndef select(self,page):\n original(self,page)\n with open("+repr(str(log))+",'a') as f:f.write(page+'\\n')\nSystemWindow.select=select\nraise SystemExit(main())\n")
with open(folder/'child.log','w') as output:
 proc = subprocess.Popen([sys.executable,str(runner)], stdout=output, stderr=output)
 try:
  deadline=time.monotonic()+12
  while not (folder/'tools/sound/window.lock').exists():
   assert proc.poll() is None
   assert time.monotonic()<deadline
   time.sleep(.05)
  for module,args in [('system_app.py',['--page','diagnostics']),('system_app.py',[]),('tools_app.py',['sound']),('updater_app.py',[]),('system_app.py',['--page','diagnostics']),('system_app.py',['--page','system'])]:
   result=subprocess.run([sys.executable,str(Path(os.environ['TEST_SOURCE'])/module),*args],stdout=output,stderr=output,timeout=12)
   assert result.returncode==0
  deadline=time.monotonic()+3
  while len(log.read_text().splitlines())<6 and time.monotonic()<deadline: time.sleep(.05)
  assert log.read_text().splitlines()==['system','diagnostics','sound','updates','diagnostics','system'],log.read_text()
  assert not (folder/'tools/vault').exists()
  assert int((folder/'tools/sound/window.lock').read_text().splitlines()[0])==proc.pid
  sock=QLocalSocket();sock.connectToServer(server_name(folder/'tools/sound'))
  assert sock.waitForConnected(2000)
  sock.disconnectFromServer()
 finally:
  proc.terminate();proc.wait(timeout=5)
'''
        config = self.root/'config/Lumen'; config.mkdir(parents=True)
        (config/'Assistant.conf').write_text('[General]\ncrashDetection=false\n')
        runtime = self.root/'runtime'; runtime.mkdir(mode=0o700)
        env = dict(os.environ, HOME=str(self.root), XDG_CONFIG_HOME=str(self.root/'config'),
                   XDG_DATA_HOME=str(self.root/'data'), XDG_STATE_HOME=str(self.root/'state'),
                   XDG_CACHE_HOME=str(self.root/'cache'), XDG_RUNTIME_DIR=str(runtime),
                   LUMEN_DATA=str(self.root/'state'), LUMEN_TOOLS_DATA=str(self.root/'tools'),
                   TEST_ROOT=str(self.root), TEST_SOURCE=str(Path(__file__).parent), PYTHONPATH=str(Path(__file__).parent), QT_QUICK_BACKEND='software')
        result = subprocess.run(['dbus-run-session','--',sys.executable,'-c',code], env=env,
                                capture_output=True, text=True, timeout=50)
        self.assertEqual(result.returncode, 0, result.stderr+(self.root/'child.log').read_text())
