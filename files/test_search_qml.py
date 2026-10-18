"""Production QML search: real keyboard, voice, files and engine contracts."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class Qt6SearchTest(unittest.TestCase):
    def test_fine_window_controls_keep_native_actions_and_accessible_names(self):
        self.run_qt6('''
from PySide6.QtCore import Qt,QPointF,QEvent,QCoreApplication
from PySide6.QtGui import QGuiApplication,QWindow
from PySide6.QtTest import QTest
from search_controller import SearchController
from search_qml import create_window
app=QGuiApplication([]);app.setQuitOnLastWindowClosed(False)
c=SearchController('/profile/search-controls',applications=[]);engine,w=create_window(app,c)
def walk(item):
 yield item
 for child in item.childItems():yield from walk(child)
def click(name):
 item=next(item for item in walk(w.contentItem()) if item.objectName()==name)
 assert item.isVisible() and item.width()>=32 and item.height()>=32,name
 image=next(child for child in walk(item) if child.metaObject().className()=='QQuickIconImage')
 assert image.width()>=20 and image.height()>=20,(name,image.width(),image.height())
 point=item.mapToScene(QPointF(item.width()/2,item.height()/2)).toPoint()
 QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,point);QTest.qWait(60)
try:
 w.resize(960,640);w.show();QTest.qWait(80);c.set_query('Keep this unsent draft')
 click('windowMaximize');assert w.visibility()==QWindow.Visibility.Maximized
 click('windowMaximize');assert w.visibility()==QWindow.Visibility.Windowed
 click('windowMinimize');assert w.visibility()==QWindow.Visibility.Minimized
 w.showNormal();QTest.qWait(60)
 click('windowHide');assert not w.isVisible()
 assert c.query=='Keep this unsent draft'
finally:
 c.shutdown();w.hide();engine.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
''')

    def test_user_turn_starts_visible_without_following_stream(self):
        self.run_qt6("""
import tempfile
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from search_controller import SearchController
from search_qml import create_window
app=QGuiApplication([])
with tempfile.TemporaryDirectory() as tmp:
 c=SearchController(tmp,applications=[]);engine,w=create_window(app,c)
 try:
  w.show();c.show_conversation();QTest.qWait(60)
  def walk(item):
   yield item
   for child in item.childItems():yield from walk(child)
  view=next(i for i in walk(w.contentItem()) if i.objectName()=='conversation')
  flick=next(i for i in walk(view) if i.metaObject().indexOfProperty('contentY') >= 0)
  def msg(role,text,key):return dict(info=dict(role=role,id=key),parts=[dict(type='text',text=text)])
  history=[msg('user','Question','u1'),msg('assistant','Old answer\\n\\n'*80,'a1'),msg('user','Next','u2')]
  c.update_messages(history);QTest.qWait(150)
  assert abs(flick.property('contentY')-view.property('turnY'))<2
  answer=msg('assistant','New answer\\n\\n'*80,'a2')
  c.update_messages(history+[answer]);QTest.qWait(100)
  start=flick.property('contentY');maximum=view.property('contentHeight')-view.property('availableHeight')
  assert start>500 and abs(start-view.property('turnY'))<2,(start,view.property('turnY'))
  answer['parts'][0]['text']+='More text\\n\\n'*30
  c.update_messages(history+[answer]);QTest.qWait(100)
  assert abs(flick.property('contentY')-start)<2,(flick.property('contentY'),start)
  view.setProperty('anchoringTurn',False);flick.setProperty('contentY',120)
  answer['parts'][0]['text']+='Another chunk'
  c.update_messages(history+[answer]);QTest.qWait(100)
  assert abs(flick.property('contentY')-120)<2,flick.property('contentY')
  c.update_messages(history+[answer,msg('user','Again','u3'),msg('assistant','Third answer\\n\\n'*80,'a3')]);QTest.qWait(100)
  assert flick.property('contentY')>start+500
 finally:c.shutdown();w.hide();engine.deleteLater();QTest.qWait(20)
""")

    def test_latest_message_button_mouse_keyboard_and_stream(self):
        self.run_qt6("""
import tempfile
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from search_controller import SearchController
from search_qml import create_window
app=QGuiApplication([])
with tempfile.TemporaryDirectory() as tmp:
 c=SearchController(tmp,applications=[]);engine,w=create_window(app,c)
 try:
  w.show();c.show_conversation();QTest.qWait(60)
  def walk(item):
   yield item
   for child in item.childItems():yield from walk(child)
  items=list(walk(w.contentItem()))
  view=next(i for i in items if i.objectName()=='conversation')
  button=next(i for i in items if i.objectName()=='latestMessage')
  flick=next(i for i in walk(view) if i.metaObject().indexOfProperty('contentY')>=0)
  assert not button.isVisible()
  def answer(text):return dict(info=dict(role='assistant',id='answer'),parts=[dict(type='text',text=text)])
  text='A paragraph of the answer.\\n\\n'*80
  c.update_messages([answer(text)]);QTest.qWait(100)
  assert button.isVisible() and button.property('text')=='Jump to latest message'
  point=button.mapToScene(QPointF(button.width()/2,button.height()/2)).toPoint()
  QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,point);QTest.qWait(50)
  assert not button.isVisible()
  assert abs(flick.property('contentY')-max(0,view.property('messageEnd')-view.property('availableHeight')+12))<2
  text+='A streamed paragraph.\\n\\n'*30
  c.update_messages([answer(text)]);QTest.qWait(100)
  assert button.isVisible(), 'More streamed content must remain reachable'
  flick.setProperty('contentY',0);button.forceActiveFocus();QTest.keyClick(w,Qt.Key_Space);QTest.qWait(50)
  assert not button.isVisible()
  w.setWidth(620);w.setHeight(560);QTest.qWait(80);flick.setProperty('contentY',0);QTest.qWait(30)
  assert button.isVisible() and button.width()<w.width()-48
  c.update_messages([answer('Short answer')]);QTest.qWait(100)
  assert not button.isVisible(), 'No jump button for non-scrollable content'
 finally:c.shutdown();w.hide();engine.deleteLater();QTest.qWait(20)
""")

    def test_voice_without_setup_stays_visible_and_offers_setup(self):
        self.run_qt6('''
import tempfile
from unittest.mock import patch
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from search_controller import SearchController
from search_qml import create_window, Activation
app=QGuiApplication([]); app.setQuitOnLastWindowClosed(False)
with tempfile.TemporaryDirectory() as tmp:
 c=SearchController(tmp,applications=[]);engine,w=create_window(app,c)
 try:
  with patch('voice_session.executable',return_value=None),patch('search_controller.subprocess.Popen') as launch:
   Activation(w,c).Voice();QTest.qWait(60)
   launch.assert_not_called()
   assert w.isVisible() and not c.voice.active
   assert c.voiceSetupRequired and c.error
  with patch('search_controller.subprocess.Popen') as launch:
   c.open_voice_setup()
   assert launch.call_args.args[0][-1]=='--speech'
 finally:c.shutdown();w.hide();engine.deleteLater();QTest.qWait(20)
''')

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

    def test_search_dismisses_on_outside_focus_and_reopens_with_draft(self):
        self.run_qt6('''
import tempfile
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from search_controller import SearchController
from search_qml import create_window, Activation
app=QGuiApplication([]);app.setQuitOnLastWindowClosed(False)
with tempfile.TemporaryDirectory() as tmp:
 c=SearchController(tmp,applications=[]);engine,w=create_window(app,c);activation=Activation(w,c)
 c.restore_recovery({'conversation':True,'chat':{'session':'preserved','draft':'Keep this draft'}})
 other=QQuickWindow();child=QQuickWindow();child.setTransientParent(w);child.setFlags(Qt.Dialog)
 for surface in (other,child):surface.resize(300,200)
 try:
  activation.Activate();QTest.qWait(50);assert w.isVisible() and w.isActive()
  child.show();child.requestActivate();QTest.qWait(50)
  assert child.isActive() and w.isVisible(), 'A search-owned dialog must not dismiss the search'
  child.hide();w.requestActivate();QTest.qWait(30)
  other.show();other.requestActivate();QTest.qWait(50)
  assert other.isActive() and not w.isVisible(), 'Clicking another window must dismiss the search'
  activation.Activate();QTest.qWait(50);assert w.isVisible() and w.isActive()
  activation.Activate();QTest.qWait(30);assert w.isVisible(), 'Repeated opening must not toggle the search away'
  assert c.query=='Keep this draft' and c.backend.session=='preserved'
  w.close();QTest.qWait(20);assert not w.isVisible()
  other.requestActivate();QTest.qWait(20)
  activation.Activate();QTest.qWait(50);assert w.isVisible() and w.isActive()
  QTest.keyClick(w,Qt.Key_Escape);QTest.qWait(20);assert not w.isVisible()
  other.requestActivate();QTest.qWait(20)
  activation.Activate();QTest.qWait(50);assert w.isVisible() and w.isActive()
  other.show();other.requestActivate();QTest.qWait(50)
  assert not w.isVisible(), 'Outside focus must still dismiss after reopening'
  assert c.query=='Keep this draft' and c.backend.session=='preserved'
 finally:
  child.hide();other.hide();c.shutdown();w.hide();engine.deleteLater();QTest.qWait(20)
''')

    def test_answer_actions_belong_to_latest_answer_card(self):
        self.run_qt6("""
import tempfile
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from search_controller import SearchController
from search_qml import create_window
app=QGuiApplication([])
with tempfile.TemporaryDirectory() as tmp:
 c=SearchController(tmp,applications=[]);engine,w=create_window(app,c);w.show();c.show_conversation()
 def walk(item):
  yield item
  for child in item.childItems():yield from walk(child)
 def visible(name):return [i for i in walk(w.contentItem()) if i.objectName()==name and i.isVisible()]
 try:
  c.backend.messages=[dict(info=dict(role=role),parts=[dict(type='text',text=text)]) for role,text in [('assistant','Old answer'),('user','Follow-up'),('assistant','Current answer')]]
  c.backend.messagesChanged.emit(c.backend.messages);QTest.qWait(60)
  assert [row['actions'] for row in c.messages]==[False,False,True]
  actions=visible('answerActions');assert len(actions)==1
  ancestor=actions[0].parentItem()
  while ancestor and ancestor.objectName()!='messageBubble':ancestor=ancestor.parentItem()
  assert ancestor and not ancestor.property('userMessage')
  copy=visible('copyAnswer')[0];point=copy.mapToScene(QPointF(copy.width()/2,copy.height()/2)).toPoint()
  QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,point);QTest.qWait(10)
  assert app.clipboard().text()=='Current answer' and copy.property('copied')
  c.backend.busy=True;c.backend.busyChanged.emit(True);QTest.qWait(10);assert not visible('answerActions')
  c.backend.busy=False;c.backend.busyChanged.emit(False)
  for theme in ('atelier','glass','graphite','midnight'):
   c.settings.setValue('appearance',theme);c.reload_settings();w.setWidth(620);QTest.qWait(30)
   for button in visible('copyAnswer')+visible('saveAnswer')+visible('rememberAnswer'):
    right=button.mapToScene(QPointF(button.width(),0)).x();assert 0<right<w.width()
 finally:c.shutdown();w.hide();engine.deleteLater();QTest.qWait(20)
""")

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
  persona=w.findChild(QObject,'personaChoice'); assert persona is not None
  c.set_persona('challenger');QTest.qWait(10)
  assert persona.property('currentIndex')==4
  saved=c.recovery_state();c.reset();assert c.persona==''
  c.restore_recovery(saved);assert c.persona=='challenger'
  c.reset()
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
   from test_rich_results import sample,message
   from rich_result import present
   c.backend.messagesChanged.emit(message(present(sample())));QTest.qWait(30)
   assert c.rich.active and c.rich.values['quality']==85
   c.rich.set_value('quality',70);c.rich.submit();assert send.call_count==2
   assert c.query=='keep draft'
   c.settings.setValue('textSize',20);c.reload_settings();QTest.qWait(20)
   assert c.theme['fontSize']==20
   assert not w.grabWindow().isNull()
   # Actual keyboard modifiers reach the one composer.
   QTest.keyClick(w,Qt.Key_Return,Qt.ShiftModifier)
   assert send.call_count==2 and chr(10) in c.query
   QTest.keyClick(w,Qt.Key_Return)
   assert send.call_count==3
   assert c.backend.session=='keep-session'
  w.setHeight(1050);c.backend.messagesChanged.emit([])
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
  with patch('lumen_tts.available',return_value=True),patch('voice_session.executable',return_value='/local/test'),patch('voice_session.Path.is_file',return_value=True),patch.object(c.voice,'listen') as listen:
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
from desktop_backend import DesktopBackend as OpenCodeBackend
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
  if path=='/config':data={'model':'test/model'}
  elif path=='/session' and method=='POST':data={'id':'ses_test'}
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
