"""Server Notes context follows the pairing and live AI consent, not old replicas."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lumen_store import Store
from lumen_memory import Memory
import knowledge_context


class KnowledgeContextTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'state');self.memory=Memory(self.store)
        self.memory.configure(True,False)
        self.config=dict(server='https://synthetic.invalid',token='synthetic',device_id='device')

    def request(self,config,path,body=None,**kwargs):
        self.assertEqual(config,self.config)
        if path=='/bridge/me':return dict(capabilities=['notes','memory'],sync_features=['knowledge_context_v1'])
        if path.endswith('/validate'):return dict(valid=True)
        self.assertTrue(path.startswith('/bridge/knowledge-context?q='))
        return [dict(id='n',path='old-local-name.md',title='One',text='Server context',revision=1)]

    def test_paired_server_without_local_notebook_or_sync_is_authoritative(self):
        with patch('lumen_connect.read_config',return_value=self.config),patch('lumen_connect.request',side_effect=self.request):
            notes,bound=knowledge_context.fetch(self.memory,'Context')
            self.assertEqual([n['text'] for n in notes],['Server context'])
            self.assertFalse(self.store.setting('knowledge/notebook',''))
            self.assertTrue(knowledge_context.valid(self.store,bound,notes))
        self.assertEqual(self.memory.scan()['notes'],[])

    def test_server_revocation_and_revision_change_are_rechecked(self):
        with patch('lumen_connect.read_config',return_value=self.config),patch('lumen_connect.request',side_effect=self.request):
            notes,bound=knowledge_context.fetch(self.memory,'Context')
            with patch('lumen_connect.request',return_value=dict(valid=False)) as request:
                self.assertFalse(knowledge_context.valid(self.store,bound,notes))
                self.assertEqual(request.call_args.args[2],dict(notes=[dict(id='n',revision=1)]))

    def test_pairing_change_or_disconnect_rejects_old_context_without_network(self):
        with patch('lumen_connect.read_config',return_value=self.config),patch('lumen_connect.request',side_effect=self.request):
            notes,bound=knowledge_context.fetch(self.memory,'Context')
        for key in ('server','token','device_id'):
            with self.subTest(key=key),patch('lumen_connect.read_config',return_value=dict(self.config,**{key:'different'})),patch('lumen_connect.request') as network:
                self.assertFalse(knowledge_context.valid(self.store,bound,notes));network.assert_not_called()
        with patch('lumen_connect.read_config',side_effect=FileNotFoundError),patch('lumen_connect.request') as network:
            self.assertFalse(knowledge_context.valid(self.store,bound,notes));network.assert_not_called()

    def test_no_capability_or_old_server_does_not_fetch_notes(self):
        for user in (dict(capabilities=['notes'],sync_features=['knowledge_context_v1']),dict(capabilities=['notes','memory'],sync_features=[])):
            with patch('lumen_connect.read_config',return_value=self.config),patch('lumen_connect.request',return_value=user) as network:
                self.assertEqual(knowledge_context.fetch(self.memory,'Context'),([],None));self.assertEqual(network.call_count,1)

    def test_context_pipeline_rechecks_before_rendering(self):
        note=dict(id='server-note:synthetic',path='server-note:synthetic',remote_id='synthetic',title='Galaxy',text='Galaxy knowledge',revision=1,source='https://synthetic.invalid',source_kind='server_note')
        with patch('knowledge_context.fetch',return_value=([note],('bound',))),patch('lumen_connect.shared_memories',return_value=[]),patch('memory_local.retrieve',side_effect=lambda *args,**kwargs:dict(mode='text',scores={})):
            with patch('knowledge_context.valid',return_value=True):
                prepared=self.memory.prepare('Galaxy','');self.assertIn('Galaxy knowledge',prepared['context']);self.assertEqual(prepared['notes'][0]['source_kind'],'server_note')
            with patch('knowledge_context.valid',return_value=False):self.assertNotIn('Galaxy knowledge',self.memory.prepare('Galaxy','')['context'])

    def test_oversized_server_context_is_refused(self):
        with patch('lumen_connect.read_config',return_value=self.config),patch('lumen_connect.request',side_effect=[self.request(self.config,'/bridge/me'),[dict(id='n',path='',title='One',text='x'*1801,revision=1)]]):
            with self.assertRaises(ValueError):knowledge_context.fetch(self.memory,'Context')
