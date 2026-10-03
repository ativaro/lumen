"""Production QML search: real keyboard, voice, files and engine contracts."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class Qt6SearchTest(unittest.TestCase):
    def run_qt6(self, script, timeout=25):
        python = Path(os.environ.get('LUMEN_QT6_PYTHON') or sys.executable)
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

    def test_search_fresh_input_and_session_recovery(self):
        self.run_qt6("""
import tempfile, time
from pathlib import Path
from unittest.mock import patch
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from search_controller import SearchController
app = QGuiApplication([])
with tempfile.TemporaryDirectory() as tmp:
    (Path(tmp)/'Holiday A.txt').write_text('a')
    (Path(tmp)/'Holiday B.txt').write_text('b')
    c = SearchController(tmp, applications=[('Holiday planner', 'example.desktop')])
    try:
        c.set_query('Holiday')
        deadline = time.monotonic()+5
        while (c.debounce.isActive() or c.scan_jobs) and time.monotonic()<deadline: QTest.qWait(10)
        assert len(c.results)==4, c.results
        c.move_selection(1)
        selected = c.results[c.selectedIndex]['value']
        with patch('search_controller.QDesktopServices.openUrl', return_value=True) as opened:
            c.submit(False)
            assert opened.call_args.args[0].toLocalFile()==selected
        with patch.object(c.backend, 'send') as send:
            c.set_query('How can I sort my photos?'); c.submit(False)
            assert c.conversation and send.call_args.args[0]=='How can I sort my photos?'
            c.backend.session='existing-session'
            c.set_query('Unsent draft')
            state=c.recovery_state()
            c.restore_recovery(state)
            assert c.query=='Unsent draft' and c.backend.session=='existing-session'
            assert send.call_count==1
    finally: c.shutdown()
""")

    def test_native_qml_keyboard_themes_voice_and_safe_content(self):
        self.run_qt6("""
import sys, tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QObject, Qt, QPointF, QMetaObject, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtTest import QTest
from search_qml import create_window, Activation
from search_controller import SearchController
from search_document import render
app=QGuiApplication([])
warnings=[]
qInstallMessageHandler(lambda kind, context, message: warnings.append(message) if 'file:' in message or 'Binding loop' in message or 'TypeError' in message else None)
with tempfile.TemporaryDirectory() as tmp:
 c=SearchController(tmp,applications=[('Calculator','calculator.desktop')])
 engine,w=create_window(app,c);w.show();w.requestActivate();QTest.qWait(50)
 try:
  composer=w.findChild(QObject,'composer')
  assert composer is not None
  assert not QIcon.fromTheme('audio-input-microphone').pixmap(20,20).isNull()
  with patch.object(c.backend,'send') as send:
   composer.setProperty('text','How can I organize files?')
   QTest.keyClick(w,Qt.Key_Return)
   assert c.conversation and send.call_count==1
   c.backend.session='keep-session'; c.set_query('keep draft')
   for theme in ('glass','graphite','atelier','midnight'):
    c.settings.setValue('appearance',theme);c.settings.sync();c.reload_settings();QTest.qWait(20)
    assert c.theme['name']==theme and composer.property('text')=='keep draft'
    assert c.theme['light']==(theme=='atelier')
    assert c.backend.session=='keep-session'
    assert not w.grabWindow().isNull()
   # Actual keyboard modifiers reach the one composer.
   QTest.keyClick(w,Qt.Key_Return,Qt.ShiftModifier)
   assert send.call_count==1 and chr(10) in c.query
   QTest.keyClick(w,Qt.Key_Return,Qt.ControlModifier)
   assert send.call_count==2
   assert c.backend.session=='keep-session'
  w.setHeight(1050);c.update_messages([])
  c.backend.questions = [dict(id='form', questions=[dict(question='Choose', multiple=True, options=[dict(label='One'),dict(label='Two')]),dict(question='Custom', options=[],custom=True)])]
  c.backend.publish_requests()
  QTest.qWait(40)
  def find(name, item=None):
   item=item or w.contentItem()
   if item.objectName()==name:return item
   for child in item.childItems():
    found=find(name,child)
    if found is not None:return found
   return None
  def click(item):
   assert item is not None,warnings
   point=item.mapToScene(QPointF(item.width()/2,item.height()/2)).toPoint()
   QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,point);QTest.qWait(10)
  click(find('choice-form-0-One'))
  click(find('choice-form-0-Two'))
  first=find('question-form-0');first.setProperty('text','Three');QMetaObject.invokeMethod(first,'textEdited')
  second=find('question-form-1');second.setProperty('text','Here');QMetaObject.invokeMethod(second,'textEdited')
  with patch.object(c.backend,'question_reply') as reply:
   click(find('reply-form'))
   assert reply.call_args.args==('form',[['One','Two','Three'],['Here']]),reply.call_args
  with patch('voice_session.executable',return_value='/local/test'),patch('voice_session.Path.is_file',return_value=True),patch.object(c.voice,'listen') as listen:
   Activation(w,c).Voice();assert c.voice.active;listen.assert_called_once()
   Activation(w,c).Voice();listen.assert_called_once()
   QTest.keyClick(w,Qt.Key_Escape);QTest.qWait(10)
   assert not w.isVisible() and not c.voice.active
  body=render('![remote](https://example.com/image.png) <img src="file:///etc/passwd"> [bad](file:///etc/passwd) [safe](https://example.com)')
  assert '<img' not in body and 'href="file:' not in body and 'href="https://example.com"' in body,body
  assert not any(name.startswith('PyQt5') for name in sys.modules)
  assert not warnings,warnings
 finally:
  c.shutdown();w.hide();engine.deleteLater();QTest.qWait(10)
""")

    def test_qt6_http_permissions_questions_and_stop(self):
        self.run_qt6("""
import json, threading, time, tempfile
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from assistant_backend import OpenCodeBackend
from search_controller import SearchController
app=QGuiApplication([])
from lumen_store import Store
Store().set_setting('memory/options', {'enabled': True, 'learn': False})
state=dict(messages=[],permissions=True,questions=True,calls=[])
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):self.handle_request('GET')
 def do_POST(self):self.handle_request('POST')
 def handle_request(self,method):
  path=self.path.split('?')[0];body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or 'null')
  state['calls'].append((method,path,body,self.headers.get('Authorization')));data={}
  if path=='/session' and method=='POST':data={'id':'ses_test'}
  elif path.endswith('/prompt_async'):
   state['messages']=[dict(info=dict(role='assistant',id='answer',parentID=body['messageID'],time={}),parts=[dict(type='text',text='Verified response')])]
  elif path.endswith('/message'):data=state['messages']
  elif path=='/session/status':data={'ses_test':{'type':'busy'}}
  elif path=='/permission':data=[dict(id='per_test',sessionID='ses_test',permission='read',patterns=['test.txt'])] if state['permissions'] else []
  elif path=='/question':data=[dict(id='que_test',sessionID='ses_test',questions=[dict(question='Which?',options=[dict(label='One')]),dict(question='Where?',options=[],custom=True)])] if state['questions'] else []
  elif path.startswith('/permission/'):state['permissions']=False
  elif path.startswith('/question/'):state['questions']=False
  raw=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
def wait(condition):
 deadline=time.monotonic()+6
 while not condition() and time.monotonic()<deadline:QTest.qWait(10)
 assert condition(),state
with tempfile.TemporaryDirectory() as tmp:
 backend=OpenCodeBackend(tmp,server_url='http://127.0.0.1:'+str(server.server_port),password='test-only')
 c=SearchController(tmp,backend=backend,applications=[])
 try:
  c.set_query('Explain this');c.submit(True)
  wait(lambda:bool(c.permissions and c.questions and c.messages))
  assert c.messages[-1]['text']=='Verified response'
  c.permission_reply('foreign-request',True)
  c.permission_reply('per_test',False)
  c.question_reply('que_test',[['One'],[]]);assert c.error
  assert state['questions']
  c.question_reply('que_test',[['One'],['Here']])
  wait(lambda:not state['permissions'] and not state['questions'])
  assert not any(path.startswith('/permission/foreign') for _,path,_,_ in state['calls'])
  assert any(path=='/question/que_test/reply' and body=={'answers':[['One'],['Here']]} for _,path,body,_ in state['calls'])
  assert all(auth and auth.startswith('Basic ') for _,_,_,auth in state['calls'])
  c.stop();wait(lambda:not c.busy)
  assert c.tracker.store.task(c.tracker.task_id)['status']=='cancelled'
 finally:c.shutdown();server.shutdown();server.server_close()
""")


if __name__ == '__main__': unittest.main()
