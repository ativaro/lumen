"""One backend/tracker across compact and full conversation surfaces."""
from test_search_qml import Qt6SearchTest
import unittest


class ConversationSurfaceTests(unittest.TestCase):
    run_qt6 = Qt6SearchTest.run_qt6
    # Reuse only the isolated process harness, not its inherited test cases.
    def test_shared_turns_draft_permissions(self):
        self.run_qt6('''
from unittest.mock import patch
from pathlib import Path
import tempfile,json
from studio_results import present
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from studio_chat import StudioChat
from studio_preview import StudioSurface
from search_controller import SearchController
from search_qml import create_window, Activation
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
with tempfile.TemporaryDirectory() as tmp, patch('desktop_backend.DesktopBackend.refresh_sessions'):
 panel=StudioChat(tmp);surface=StudioSurface(panel);surface.resize(1480,900);surface.show();QTest.qWait(20);c=SearchController(tmp,panel=panel,applications=[])
 engine,w=create_window(app,c);activation=Activation(w,c);backend=panel.backend
 try:
  assert c.backend is backend and c.tracker is panel.tracker and c.voice is panel.context_tools.conversation
  panel.composer.setPlainText('Draft in full view');assert c.query=='Draft in full view'
  c.set_query('Draft in search');assert panel.composer.toPlainText()=='Draft in search'
  backend.session='shared';backend.permissions=[dict(id='approval',permission='read',patterns=['example'])]
  backend.requestsChanged.emit(backend.permissions,[]);assert c.permissions[0]['id']=='approval'
  calls=[]
  def send(text,files,agent='build',**kwargs):
   calls.append((text,files));backend.started.emit(text,files,agent);backend.message_id='u'+str(len(calls))
   backend.messages.append(dict(info=dict(id=backend.message_id,role='user'),parts=[dict(type='text',text=text)]))
   backend.set_busy(True);backend.messagesChanged.emit(backend.messages);return True
  with patch.object(backend,'send',side_effect=send),patch.object(backend,'shutdown') as shutdown:
   for i in range(3):
    c.show_conversation();c.set_query('Turn '+str(i));c.submit(True)
    assert len(calls)==i+1 and c.query=='' and panel.composer.toPlainText()==''
    for _ in range(3):
     activation.Activate();QTest.qWait(20);w.hide();c.sync_panel()
     assert backend.busy and backend.session=='shared'
    answer=dict(info=dict(id='a'+str(i),parentID=backend.message_id,role='assistant'),parts=[dict(type='text',text='Answer '+str(i))])
    if i==1:
     result=Path(tmp)/'result.txt';result.write_text('Synthetic file result')
     answer['parts'].append(dict(type='tool',tool='cachyos_lumen_present_files',state=dict(status='completed',output=json.dumps(present([str(result)])))))
    backend.messages.append(answer);backend.messagesChanged.emit(backend.messages)
    backend.set_busy(False);backend.completed.emit(True,'Answer '+str(i))
    assert len(c.messages)==2*(i+1),c.messages
    assert panel.last_answer=='Answer '+str(i)
    if i==1: assert panel.presentation['paths']==[str(result)]
    if i==2: assert surface.choice.currentData() is None and surface.answer.isVisible() and not surface.preview.isVisible(), (surface.choice.currentData(), surface.answer.isVisible(), surface.preview.isVisible(), surface.pane.isVisible())
   assert len(panel.tracker.store.rows('SELECT id FROM tasks'))==3
   c.set_query('Unsent follow-up');c.shutdown()
   shutdown.assert_not_called();assert c.query=='Unsent follow-up'
  rows=[dict(id=str(i),title='Conversation '+str(i),time=dict(updated=i)) for i in range(8)]
  backend.sessionsChanged.emit(rows);assert len(c.sessions)==10 # new + eight + active
  c.set_auto_approve(False);assert not panel.dont_ask.isChecked()
  c.set_mode('plan');assert panel.mode.currentData()=='plan'
  c.set_learn(True);assert panel.context_tools.learn.isChecked()
 finally:
  backend.busy=False;c.shutdown();w.hide();engine.deleteLater();QTest.qWait(20)
  surface.preview.shutdown();surface.close();panel.context_tools.close();backend.shutdown();panel.deleteLater();QTest.qWait(20)
''')
