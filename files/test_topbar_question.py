"""Topbar questions cross stdin intact and never become shell arguments."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class TopbarQuestionTest(unittest.TestCase):
    def test_real_search_startup_submits_once_without_an_engine(self):
        program=Path(__file__).resolve().parents[1]/'agent-app/main.py'
        self.check_search_startup(program)

    def check_search_startup(self,program):
        script=r'''
import importlib.util,sys,os
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
spec=importlib.util.spec_from_file_location('desktop',sys.argv[1]);desktop=importlib.util.module_from_spec(spec);spec.loader.exec_module(desktop)
import setup_dialog
setup_dialog.offer_setup=lambda *_:None
from desktop_backend import DesktopBackend
DesktopBackend.refresh_sessions=lambda *_:None
DesktopBackend._run=lambda *_:None
import desktop_backend
desktop_backend.connection=lambda:({'server':'https://synthetic.invalid','token':'synthetic'},'test')
received=[]
def close():
    for window in QApplication.topLevelWidgets():
        if isinstance(window,desktop.LumenWindow): window.close()
    QApplication.instance().quit()
def send(self,text,files,*args,**options):
    expected=os.environ.get('EXPECTED_FILE','')
    assert (text.startswith(os.environ['EXPECTED_QUESTION']) and expected in text) if expected else text==os.environ['EXPECTED_QUESTION']
    assert [path for path,mime in files]==([expected] if expected else []),files
    note=os.environ.get('EXPECTED_NOTE','')
    if note:
        import json
        assert self.execution=='server' and options['context_data']['note_reference']==json.loads(note)
    received.append(text)
    QTimer.singleShot(100,close)
    return True
DesktopBackend.send=send
sys.argv=[str(desktop.ROOT/'agent-app/main.py'),'--search']
original_exec=QApplication.exec
def bounded_exec(self):
    QTimer.singleShot(8000,lambda:self.exit(2))
    return original_exec()
QApplication.exec=bounded_exec
result=desktop.main()
assert result==0 and len(received)==1,(result,received)
assert 'LUMEN_ASK_PROMPT' not in os.environ
assert 'LUMEN_ASK_FILE' not in os.environ
assert 'LUMEN_ASK_NOTE' not in os.environ
'''
        with tempfile.TemporaryDirectory() as tmp:
            question='Erkläre $HOME und $(echo test).'
            env=dict(os.environ,HOME=tmp,XDG_CONFIG_HOME=tmp+'/config',XDG_DATA_HOME=tmp+'/data',
                XDG_STATE_HOME=tmp+'/state',XDG_CACHE_HOME=tmp+'/cache',LUMEN_DATA=tmp+'/lumen',LUMEN_TOOLS_DATA=tmp+'/tools',
                QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software',LUMEN_CRASH_CHILD='1',
                LUMEN_OPENCODE_BIN='/nonexistent/test-engine',LUMEN_ASK_PROMPT=question,EXPECTED_QUESTION=question)
            attachment=Path(tmp)/'note.pdf';attachment.write_text('synthetic attachment')
            for mode in ('plain','file','note'):
                with self.subTest(mode=mode):
                    current=dict(env)
                    if mode=='file':current.update(LUMEN_ASK_FILE=str(attachment),EXPECTED_FILE=str(attachment))
                    if mode=='note':
                        note=json.dumps(dict(reference=dict(version=2,app='note',id='00000000-0000-0000-0000-000000000001',title='Workshop',locator=dict(server='https://synthetic.invalid',account='00000000-0000-0000-0000-000000000002')),revision=3))
                        current.update(LUMEN_ASK_NOTE=note,EXPECTED_NOTE=note)
                    try:
                        result=subprocess.run(['dbus-run-session','--',sys.executable,'-u','-c',script,str(program)],env=current,capture_output=True,text=True,timeout=15)
                    except subprocess.TimeoutExpired as error:self.fail(str(error.stdout)+str(error.stderr))
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    self.assertNotIn('Traceback (most recent call last)',result.stderr)

if __name__=='__main__':unittest.main()
