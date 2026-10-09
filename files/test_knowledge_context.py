import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lumen_store import Store
from wissen_data import activate, Notebook
from lumen_memory import Memory
import wissen_sync
import knowledge_context


class KnowledgeContextTest(unittest.TestCase):
    def test_context_pipeline_rechecks_before_rendering(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'state');activate(store);memory=Memory(store);memory.configure(True,False)
            note=dict(id='server-note:synthetic',path='server-note:synthetic',remote_id='synthetic',title='Galaxy',text='Galaxy knowledge',revision=1,source='https://synthetic.invalid',source_kind='server_note')
            with patch('knowledge_context.fetch',return_value=([note],('bound',))), patch('lumen_connect.shared_memories',return_value=[]), patch('memory_local.retrieve',return_value=dict(mode='text',scores={})), patch('knowledge_context.valid',return_value=True):
                prepared=memory.prepare('Galaxy','')
                self.assertIn('Galaxy knowledge',prepared['context'])
                self.assertEqual(prepared['notes'][0]['source_kind'],'server_note')
            with patch('knowledge_context.fetch',return_value=([note],('bound',))), patch('lumen_connect.shared_memories',return_value=[]), patch('memory_local.retrieve',return_value=dict(mode='text',scores={})), patch('knowledge_context.valid',return_value=False):
                self.assertNotIn('Galaxy knowledge',memory.prepare('Galaxy','')['context'])

    def test_explicit_connection_consent_and_live_revocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'state');activate(store);book=Notebook(store);memory=Memory(store)
            config=dict(server='https://synthetic.invalid',token='synthetic')
            with patch('lumen_connect.read_config',return_value=config):
                key,state=wissen_sync.settings(book,config)
                self.assertIsNone(knowledge_context.active(store))
                state.update(enabled=True,server_context=True);store.set_setting(key,state)
                def request(config,path,body=None,**kwargs):
                    if path=='/bridge/me':return dict(capabilities=['notes','memory'],sync_features=['knowledge_context_v1'])
                    if '/validate' in path:return dict(valid=False)
                    return [dict(id='n',path='One.md',title='One',text='Context',revision=1)]
                with patch('lumen_connect.request',side_effect=request):
                    notes,bound=knowledge_context.fetch(memory,'Context')
                    self.assertEqual(len(notes),1)
                    self.assertFalse(knowledge_context.valid(store,bound,notes))
                    state['server_context']=False;store.set_setting(key,state)
                    self.assertFalse(knowledge_context.valid(store,bound,notes))
                    self.assertEqual(knowledge_context.fetch(memory,'Context'),([],None))

    def test_local_denial_wins_and_new_account_has_no_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'state');activate(store);book=Notebook(store);memory=Memory(store)
            note=book.create('Private')
            memory.share(note['path'],False)
            config=dict(server='https://synthetic.invalid',token='synthetic')
            with patch('lumen_connect.read_config',return_value=config):
                key,state=wissen_sync.settings(book,config);state.update(enabled=True,server_context=True);store.set_setting(key,state)
                def request(config,path,body=None,**kwargs):
                    if path=='/bridge/me':return dict(capabilities=['notes','memory'],sync_features=['knowledge_context_v1'])
                    return [dict(id='n',path=note['path'],title='Private',text='Hidden',revision=1)]
                with patch('lumen_connect.request',side_effect=request):
                    self.assertEqual(knowledge_context.fetch(memory,'Hidden')[0],[])
                with patch('lumen_connect.read_config',return_value=dict(config,token='another-account')):
                    self.assertIsNone(knowledge_context.active(store))
