"""Topbar questions cross stdin intact and never become shell arguments."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import lumen_panel


class TopbarQuestionTest(unittest.TestCase):
    def test_real_search_startup_submits_once_without_an_engine(self):
        program=Path(__file__).resolve().parents[1]/'agent-app/main.py'
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
def send(self,text,files,*args,**options):
    expected=os.environ.get('EXPECTED_FILE','')
    assert (text.startswith(os.environ['EXPECTED_QUESTION']) and expected in text) if expected else text==os.environ['EXPECTED_QUESTION']
    assert [path for path,mime in files]==([expected] if expected else []),files
    note=os.environ.get('EXPECTED_NOTE','')
    if note:
        import json
        assert self.execution=='server' and options['context_data']['note_reference']==json.loads(note)
    received.append(text)
    QTimer.singleShot(100,QApplication.instance().quit)
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

    def request(self, payload):
        output=io.StringIO()
        with patch('sys.argv',['lumen-panel','--ask']),patch('sys.stdin',io.TextIOWrapper(io.BytesIO(payload))),contextlib.redirect_stdout(output):
            lumen_panel.main()
        return json.loads(output.getvalue())

    def test_question_is_preserved_without_shell_or_command_line_text(self):
        question='Was bedeutet "$(echo test)" und $HOME? Ändere nichts.'
        with patch('lumen_launch.executable',return_value='/native/lumen-agent-app'),patch.object(lumen_panel.subprocess,'Popen') as launch:
            self.assertEqual(self.request(json.dumps({'prompt':question}).encode()),{'error':''})
        self.assertEqual(launch.call_args.args[0],['/native/lumen-agent-app','--search'])
        self.assertEqual(launch.call_args.kwargs['env']['LUMEN_ASK_PROMPT'],question)
        self.assertNotIn('shell',launch.call_args.kwargs)

    def test_malformed_or_oversized_requests_do_not_launch(self):
        payloads=[b'not json',b'[]',b'{"prompt":true}',b'{"prompt":"   "}',b'{"prompt":"x","extra":1}',
                  json.dumps({'prompt':'x'*4001}).encode(),json.dumps({'prompt':'a\0b'}).encode(),b'{"prompt":"x"}'+b' '*65536]
        with patch.object(lumen_panel.subprocess,'Popen') as launch:
            for payload in payloads:
                with self.subTest(size=len(payload)):self.assertTrue(self.request(payload)['error'])
            launch.assert_not_called()

    def test_removed_topbar_file_selection_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(lumen_panel.subprocess,'Popen') as launch:
            path=Path(tmp)/'Notiz $HOME.txt';path.write_text('synthetic')
            for value in (str(path),True,'relative.txt',tmp,'/does-not-exist',str(path)+'\0'):
                with self.subTest(value=value):
                    result=self.request(json.dumps(dict(prompt='Zusammenfassen',file=value)).encode())
                    self.assertTrue(result['error'])
            launch.assert_not_called()


if __name__=='__main__':unittest.main()
