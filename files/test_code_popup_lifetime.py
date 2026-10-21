"""Real popup mouse selection runs in children so a native crash fails the test."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class PopupLifetimeTest(unittest.TestCase):
    def check(self,scenario):
        with tempfile.TemporaryDirectory(prefix='lumen-popup-test-') as root:
            env=dict(os.environ,HOME=root,QT_QPA_PLATFORM='offscreen',LUMEN_LANGUAGE='de',LUMEN_OPENCODE_BIN='/nonexistent/test-engine',LUMEN_CRASH_CHILD='1')
            for name,folder in [('LUMEN_DATA','state'),('LUMEN_TOOLS_DATA','tools'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('XDG_STATE_HOME','xdg-state'),('XDG_RUNTIME_DIR','runtime')]:
                env[name]=str(Path(root)/folder);Path(env[name]).mkdir(mode=0o700)
            result=subprocess.run([sys.executable,'-B','-X','faulthandler',str(Path(__file__).resolve()),'--child',scenario],env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
            self.assertIn('popup-survived',result.stdout)

    def test_creation_time_popup_save_reopen_and_cancel(self):self.check('creation')
    def test_creation_source_popup_preserves_time(self):self.check('source')
    def test_routine_trigger_popup(self):self.check('routine-trigger')
    def test_routine_add_action_popup(self):self.check('routine-action')
    def test_native_start_popup_keeps_controls_alive(self):self.check('native')
    def test_retired_widget_lives_until_deferred_delete(self):self.check('lifetime')




if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--child':
        import resource
        resource.setrlimit(resource.RLIMIT_CORE,(0,0));child(sys.argv[2])
    else:unittest.main()
