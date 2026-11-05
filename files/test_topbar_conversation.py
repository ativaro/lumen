"""The topbar adapter delegates to the existing engine, including its safeguards."""
import unittest
import test_search_qml as search_tests


class ConversationTest(unittest.TestCase):
    run_qt6=search_tests.Qt6SearchTest.run_qt6

    def test_one_engine_stream_rich_results_and_validation(self):
        self.run_qt6('''
import io,json,tempfile
from unittest.mock import patch
from PySide6.QtGui import QGuiApplication
from search_controller import SearchController
from topbar_conversation import ConversationPipe
app=QGuiApplication([])
with tempfile.TemporaryDirectory() as directory:
 c=SearchController(directory,applications=[]);out=io.StringIO();pipe=ConversationPipe(c,out)
 try:
  with patch.object(c.backend,'send',return_value=True) as send:
   pipe.dispatch(dict(method='submit',args=['Explain $HOME and $(echo test)',{}],id='one'))
   send.assert_called_once();assert send.call_args.args[0]=='Explain $HOME and $(echo test)'
   assert c.conversation and not c.query
  message=[dict(info=dict(id='answer',role='assistant'),parts=[dict(type='text',text='## Workshop\\nA **shared** answer')])]
  c.backend.messages=message;c.backend.messagesChanged.emit(message)
  state=pipe.snapshot();assert state['messages'][-1]['text']=='## Workshop\\nA **shared** answer'
  assert state['messages'][-1]['blocks'] and state['messages'][-1]['key']=='answer'
  with patch.object(c.backend,'permission_reply') as reply:
   pipe.dispatch(dict(method='permission',args=['permission-one',False]));reply.assert_called_once_with('permission-one',False)
  from test_rich_results import sample,message as rich_message
  from rich_result import present
  c.backend.messagesChanged.emit(rich_message(present(sample())))
  assert pipe.snapshot()['rich']['active']
  pipe.dispatch(dict(method='rich.set_value',args=['quality',70]))
  assert c.rich.values['quality']==70
  with patch.object(c.backend,'send') as send:
   for args in (['',{}],['x'*4001,{}],['a\\0b',{}],['x',{'invalid':True}]):
    pipe.dispatch(dict(method='submit',args=args,id='bad'))
   pipe.dispatch(dict(method='permission',args=['permission-one','yes'],id='bad'))
   pipe.dispatch(dict(method='__getattribute__',args=['settings'],id='bad'))
   pipe.dispatch(dict(method='submit',args=['x',{}],file='/a/file',id='bad'))
   send.assert_not_called()
  rows=[json.loads(line) for line in out.getvalue().splitlines()]
  assert next(r for r in rows if r.get('id')=='one')['error']==''
  assert all(r['error'] for r in rows if r.get('id')=='bad')
 finally:c.shutdown()
''')

    def test_busy_and_failed_submission_keep_draft(self):
        self.run_qt6('''
import io,tempfile
from unittest.mock import patch
from PySide6.QtGui import QGuiApplication
from search_controller import SearchController
from topbar_conversation import ConversationPipe
app=QGuiApplication([])
with tempfile.TemporaryDirectory() as directory:
 c=SearchController(directory,applications=[]);pipe=ConversationPipe(c,io.StringIO())
 try:
  c.backend.set_busy(True)
  with patch.object(c.backend,'send') as send:
   pipe.dispatch(dict(method='submit',args=['Keep',{}]));send.assert_not_called()
  c.backend.set_busy(False)
  with patch.object(c.backend,'send',return_value=False):
   pipe.dispatch(dict(method='submit',args=['Keep',{}]));assert c.query=='Keep'
  assert not c.note_context
  with patch.object(c.backend,'new_conversation') as reset,patch.object(c.backend,'send') as send:
   pipe.dispatch(dict(method='reset',args=[]));reset.assert_called_once();send.assert_not_called()
   assert c.query=='Keep'
 finally:c.shutdown()
''')

    def test_notes_reference_reaches_existing_server_context(self):
        self.run_qt6('''
import io,tempfile
from unittest.mock import patch
from PySide6.QtGui import QGuiApplication
from search_controller import SearchController
from topbar_conversation import ConversationPipe
app=QGuiApplication([])
note=dict(reference=dict(version=2,app='note',id='00000000-0000-0000-0000-000000000001',title='Workshop',locator=dict(server='https://synthetic.invalid',account='00000000-0000-0000-0000-000000000002')),revision=3)
with tempfile.TemporaryDirectory() as directory:
 c=SearchController(directory,applications=[]);pipe=ConversationPipe(c,io.StringIO())
 try:
  with patch.object(c.backend,'set_execution',return_value=True) as execution,patch.object(c.backend,'send',return_value=True) as send:
   pipe.dispatch(dict(method='submit',args=['Summarize the selected note',note]))
   execution.assert_called_once_with('server');send.assert_called_once()
   assert send.call_args.kwargs['context_data']=={'note_reference':note['reference']}
   assert not c.note_context
 finally:c.shutdown()
''')

    def test_real_helper_protocol_and_draft_recovery_without_model(self):
        self.run_qt6('''
import json,os,subprocess,sys,lumen_panel
from pathlib import Path
commands=[dict(method='width',args=[640],id='width'),dict(method='draft',args=['Keep my unsent draft',{}],id='draft'),dict(method='close',args=[])]
p=subprocess.run([sys.executable,lumen_panel.__file__,'--conversation'],input=''.join(json.dumps(c)+'\\n' for c in commands),text=True,capture_output=True,timeout=10)
assert p.returncode==0,p.stderr
rows=[json.loads(line) for line in p.stdout.splitlines()]
assert any(row.get('id')=='draft' and not row['error'] for row in rows),rows
saved=json.loads((Path(os.environ['LUMEN_DATA'])/'topbar-conversation.json').read_text())
assert saved['chat']['draft']=='Keep my unsent draft'
assert not saved['chat']['session']
''')


if __name__=='__main__':unittest.main()
