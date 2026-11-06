"""Live paired memory replaces retrieval from replicas without editing local data."""
import tempfile
import os
import copy
import unittest
from uuid import uuid4
from unittest.mock import patch
from lumen_memory import Memory
from lumen_store import Store
import knowledge_context


class AccountMemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.memory=Memory(self.store);self.memory.configure(True,True)
        self.local=self.memory.remember('Answer length','OLD LOCAL CONTENT',kind='preference')
        self.config=dict(server='https://synthetic.invalid',token='synthetic',device_id=str(uuid4()))
        self.identity=str(uuid4());self.revision=1;self.body='CURRENT ACCOUNT CONTENT';self.version='a'*64

    def request(self,config,path,body=None,**kwargs):
        self.assertEqual(config,self.config)
        if path=='/bridge/me':return dict(capabilities=['memory'],sync_features=['memory_context_v1'])
        if path.endswith('/validate'):return dict(valid=body['stamp']==self.version)
        self.assertTrue(path.startswith('/bridge/memories/context?q='))
        return dict(stamp=self.version,items=[dict(id=self.identity,title='Answer length',text=self.body,revision=self.revision)])

    def test_correction_same_id_no_replica_or_local_learning_and_explicit_offline(self):
        with patch('lumen_connect.read_config',return_value=self.config),patch('lumen_connect.request',side_effect=self.request):
            first=self.memory.prepare('Answer length','')
            self.assertIn(self.body,first['context']);self.assertNotIn('OLD LOCAL',first['context'])
            self.assertEqual(first['revision'],-1);self.assertEqual(first['candidates'],[])
            self.assertEqual(first['notes'][0]['id'],'server:'+self.identity)
            self.assertTrue(self.memory.valid_prepared(first))
            self.body='CORRECTED ACCOUNT CONTENT';self.version='b'*64;self.revision+=1
            self.assertFalse(self.memory.valid_prepared(first))
            second=self.memory.prepare('Answer length','')
            self.assertIn(self.body,second['context']);self.assertNotIn('CURRENT ACCOUNT',second['context'])
            self.assertEqual(second['notes'][0]['id'],first['notes'][0]['id'])
            self.assertEqual(second['notes'][0]['revision'],2)
            self.assertEqual(self.memory.scan()['notes'][0]['hash'],self.local['hash'])
            with patch('lumen_connect.read_config',return_value=dict(self.config,token='other')):
                self.assertFalse(self.memory.valid_prepared(second))
        with patch('lumen_connect.read_config',side_effect=FileNotFoundError):
            self.assertIn('OLD LOCAL',self.memory.prepare('Answer length','')['context'])

    def test_unavailable_account_never_falls_back_to_local_memory(self):
        with patch('lumen_connect.read_config',return_value=self.config),patch('lumen_connect.request',side_effect=OSError):
            with self.assertRaises(OSError):self.memory.prepare('Answer length','')
        self.assertEqual(self.memory.scan()['notes'][0]['hash'],self.local['hash'])

    def test_new_statement_uses_shared_learning_without_uploading_local_memory(self):
        from lumen_memory import stamp
        import lumen_connect
        remote=dict(connection=lumen_connect.connection_scope(self.config),stamp=self.version,
                    preferences=dict(enabled=True,learn=True,solutions=True,automatic=False,revision=3))
        prepared=dict(stamp=stamp(self.store),revision=-1,remote=remote,candidates=[dict(text='PRIVATE LOCAL CONTENT')])
        receipt=dict(task_id=str(uuid4()),state='queued',saved=0,pending=0)
        payloads=[]
        def request(config,path,body=None,**kwargs):
            if path=='/bridge/me':return dict(capabilities=['tasks','memory'],sync_features=['memory_learning_v1'])
            payloads.append((path,body));return receipt
        event_id='msg_'+uuid4().hex
        with patch('lumen_connect.read_config',return_value=self.config),patch('lumen_connect.request',side_effect=request):
            prepared['stamp']=stamp(self.store)
            self.assertEqual(self.memory.learn_account('Remember concise answers.',prepared,event_id),receipt)
            self.assertEqual(set(payloads[0][1]),{'text','event_id','preferences_revision'})
            self.assertEqual(payloads[0][1]['text'],'Remember concise answers.')
            self.assertNotIn('PRIVATE',str(payloads))
            self.assertEqual(self.memory.account_learning_status(remote,receipt['task_id']),receipt)
            count=len(payloads)
            remote['preferences']['learn']=False
            self.assertEqual(self.memory.learn_account('New',prepared,event_id)['state'],'disabled')
            remote['preferences']['learn']=True
            self.store.set_setting('modelPolicy',dict(privacy='local'))
            self.assertEqual(self.memory.learn_account('New',prepared,event_id)['state'],'local')
            self.assertEqual(len(payloads),count)
            self.store.set_setting('modelPolicy',{})
            with patch('lumen_connect.read_config',return_value=dict(self.config,token='other')):
                with self.assertRaises(ValueError):self.memory.account_learning_status(remote,receipt['task_id'])
            self.memory.configure(True,False)
            self.assertEqual(self.memory.learn_account('New',prepared,event_id)['state'],'stopped')
        self.assertEqual(self.memory.book.read(self.local['path'])['hash'],self.local['hash'])

    def test_bad_data_disabled_consent_and_existing_hidden_entries(self):
        with patch('lumen_connect.read_config',return_value=self.config),patch('lumen_connect.request',side_effect=self.request):
            self.store.set_setting('memory/server_hidden',[self.config['server']+'#'+self.identity])
            self.assertEqual(self.memory.prepare('Answer length','')['notes'],[])
            self.body='x'*1801
            with self.assertRaises(ValueError):self.memory.prepare('Answer length','')
            self.memory.configure(False,False)
            self.assertEqual(self.memory.prepare('Answer length','')['context'],'')


class ConversationMemoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_current_context_keeps_session_correction_resets_and_cancel_cannot_submit(self):
        from assistant_backend import OpenCodeBackend
        from memory_bridge import MemoryBridge
        from lumen_memory import stamp
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,LUMEN_DATA=tmp):
            store=Store();Memory(store).configure(True,False)
            backend=OpenCodeBackend(tmp);backend.selected_model='test/model'
            backend.ensure_server=lambda callback:callback()
            backend.check_server_mcp_binding=lambda:True
            calls=[];sessions=[];version=['a'];pending=[]
            def request(method,path,body=None,callback=None,error=None,**kwargs):
                if method=='POST' and path=='/session':
                    sessions.append('s'+str(len(sessions)+1));callback(dict(id=sessions[-1]))
                elif path.endswith('/prompt_async'):
                    calls.append((path,copy.deepcopy(body)));backend.set_busy(False)
                elif callback:callback([])
            backend.request=request
            bridge=MemoryBridge(backend);backend.memory=bridge
            bridge.prepare=lambda text,directory,done:done(dict(stamp=stamp(store),revision=-1,candidates=[],notes=[],
                context='VERSION '+version[0],remote=dict(stamp=version[0],connection='synthetic')))
            bridge.job=lambda action,done,failed,**kwargs:done(True)
            try:
                backend.send('First');backend.send('Again')
                self.assertEqual(len(calls),2);self.assertEqual(calls[0][0],calls[1][0])
                version[0]='b';backend.send('After correction')
                self.assertNotEqual(calls[1][0],calls[2][0])
                self.assertIn('VERSION b',calls[2][1]['system']);self.assertNotIn('VERSION a',calls[2][1]['system'])
                bridge.job=lambda action,done,failed,**kwargs:pending.append(done)
                backend.send('Cancel during revalidation');self.assertEqual(len(pending),1)
                backend.stop();pending[0](True)
                self.assertEqual(len(calls),3)
            finally:backend.shutdown();backend.deleteLater()
