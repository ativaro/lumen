"""Reviewed native project capture: source, exact account and explicit retry."""
from copy import deepcopy
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
from interop_data import Registry
from server_app_session import AppSession,Binding
import lumen_connect
import server_project_capture as capture


class CaptureTest(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory()));self.registry=Registry(self.root/'tools')
        self.config=dict(server='https://fixture.invalid',device_id=str(uuid4()),token='private-synthetic')
        self.binding=Binding(self.config['server'],str(uuid4()),self.config['device_id'],'projects');self.revision=6
        self.job=SimpleNamespace(check=lambda:None);self.session=AppSession(self.config,self.binding)
        self.session._cookie=b'x'*43;self.session._deadline=self.session._clock()+600;self.session.state='ready';self.session.access='read_write';self.session.request=self.request
        self.project=dict(id=str(uuid4()),title='Serverprojekt',notes='Original',revision=1,role='manager',archived=False)
        source=dict(app='files',kind='file',id='/fixture/source.txt',title='Selected original',path='/fixture/source.txt')
        self.payload=dict(title='Selected text',text='test\n\n\n\ntest1',paths=[],source=source,source_url=self.registry.register(source))
        self.token=self.registry.enqueue('workbench','workbench.add',self.payload)
        self.choice=dict(id=self.project['id'],title='Übernommene Auswahl',token=self.token,mode='copy',due='')
        self.posts=[];self.operations={};self.lose=False;self.after_post=lambda:None
        self.enterContext(patch.object(lumen_connect,'read_config',side_effect=lambda:dict(self.config)))
        self.enterContext(patch.object(lumen_connect,'request',side_effect=lambda *args,**kwargs:dict(id=self.binding.account,device_id=self.binding.device,permissions_revision=self.revision,capabilities=['projects','tasks','drive'])))

    def request(self,path,body=None,**kwargs):
        if path.startswith('/api/project-collections?'):return dict(items=[self.project],next_offset=None)
        if body is None:return dict(project=deepcopy(self.project),links=[],next_offset=None)
        self.posts.append((path,deepcopy(body)))
        key=body.get('operation_id') or body.get('request_id')
        if key not in self.operations:
            if path.endswith('/capture'):
                self.project=dict(self.project,notes=self.project['notes']+'\n\n'+body['text']+'\n'+body['source_url'],revision=self.project['revision']+1)
                result=dict(project=deepcopy(self.project),operation_id=key)
            else:result=dict(task=dict(id=str(uuid4()),prompt=body['question'].strip(),project_context=dict(id=self.project['id'])))
            self.operations[key]=result
        self.after_post()
        if self.lose:self.lose=False;raise TimeoutError('Committed, reply lost')
        return deepcopy(self.operations[key])

    def apply(self,**kwargs):return capture.capture(self.token,self.choice,self.session,self.revision,self.job,root=self.root/'tools',**kwargs)

    def test_text_blank_lines_and_source_are_saved_once_with_a_native_return_path(self):
        result=self.apply();self.assertEqual(result['app'],'projects');self.assertEqual(result['id'],self.project['id'])
        self.assertIn(self.payload['text'],self.project['notes']);self.assertIn(self.payload['source_url'],self.project['notes'])
        self.assertEqual(self.apply(),result);self.assertEqual(len(self.posts),1)
        self.assertEqual(self.registry.request(self.token)['state'],'done');self.assertEqual(self.registry.related(self.registry.request(self.token)['result'])[0]['id'],self.payload['source']['id'])
        self.assertNotIn(self.config['token'],self.registry.library.db.read_bytes().decode(errors='ignore'))

    def test_lost_reply_requires_explicit_retry_with_original_uuid_and_cas(self):
        self.lose=True
        with self.assertRaises(TimeoutError):self.apply()
        with self.assertRaisesRegex(ValueError,'unklar'):self.apply()
        self.assertEqual(len(self.posts),1)
        self.apply(retry=True);self.assertEqual(len(self.operations),1);self.assertEqual(self.posts[0],self.posts[1])

    def test_account_change_after_commit_never_publishes_a_foreign_receipt(self):
        self.after_post=lambda:self.config.update(token='different')
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.registry.request(self.token)['state'],'pending')
        self.assertEqual(len(self.operations),1)

    def test_sources_are_loaded_from_current_server_not_local_project_library(self):
        with patch('tools_data.Library',side_effect=AssertionError('old project read')):
            self.assertEqual(capture.projects(self.session,self.revision,self.job),[dict(id=self.project['id'],title=self.project['title'])])

    def test_selected_question_uses_project_chat_with_no_other_app_sources(self):
        self.token=self.registry.enqueue('workbench','workbench.question',self.payload);self.choice=dict(self.choice,token=self.token)
        result=self.apply();self.assertEqual(result['id'],self.project['id'])
        path,body=self.posts[0];self.assertTrue(path.endswith('/questions'));self.assertTrue(body['project_chat']);self.assertEqual(body['sources'],[]);self.assertIn(self.payload['source_url'],body['question'])
        self.assertEqual(self.registry.request(self.token)['choice']['project_capture']['receipt']['task'],self.operations[body['request_id']]['task']['id'])

    def test_existing_interop_choices_and_apply_never_fall_back_to_native_projects(self):
        import interop_targets
        with patch.object(interop_targets,'Library',side_effect=AssertionError('retired project writer')):
            rows=interop_targets.choices('workbench.add',session=self.session,permissions_revision=self.revision,job=self.job)
            self.assertEqual(rows,[dict(id=self.project['id'],title=self.project['title'])])
            result=interop_targets.apply('workbench.add',self.payload,self.choice,self.job,root=self.root/'tools',session=self.session,permissions_revision=self.revision)
            self.assertEqual(result['app'],'projects')

    def test_project_action_menu_only_offers_implemented_server_capture_modes(self):
        import interop_targets
        self.assertEqual(interop_targets.ACTIONS['workbench.add']['modes'],['copy','link'])
        self.assertIn('workbench.question',interop_targets.available(self.payload))
        mixed=dict(self.payload,paths=['/fixture/document.pdf'])
        self.assertNotIn('workbench.question',interop_targets.available(mixed))
        self.assertIn('workbench.add',interop_targets.available(mixed))

    def test_local_files_cannot_be_silently_copied_without_drive_confirmation(self):
        changed=dict(self.payload,paths=['/fixture/private.pdf']);token=self.registry.enqueue('workbench','workbench.add',changed)
        with self.assertRaisesRegex(ValueError,'Drive'):
            capture.capture(token,dict(self.choice,token=token),self.session,self.revision,self.job,root=self.root/'tools')
        self.assertEqual(self.posts,[])

    def test_local_files_require_completed_individual_drive_receipts_and_keep_originals(self):
        from interop_sources import from_paths
        path=self.root/'original.pdf';path.write_bytes(b'Original synthetic document');before=path.read_bytes()
        payload=from_paths([str(path)]);payload['source_url']=self.registry.register(payload['source'])
        token=self.registry.enqueue('workbench','workbench.add',payload)
        with patch('server_file_import.apply',side_effect=AssertionError('No automatic uploads')):
            plan=capture.begin_files(token,self.session,self.revision,self.job,root=self.root/'tools')
        child=plan['children'][0]['token']
        choice=dict(self.choice,token=token,mode='link')
        with self.assertRaisesRegex(ValueError,'Dateikopie'):
            capture.capture(token,choice,self.session,self.revision,self.job,root=self.root/'tools')
        ref=dict(app='files',kind='drive_file',id=str(uuid4()),title='original.pdf',locator=dict(server=self.binding.origin,account=self.binding.account))
        with self.registry.library.connect() as db:db.execute("UPDATE handoffs SET state='done',result=? WHERE id=?",(self.registry.register(ref),child))
        with patch('server_file_import.apply',return_value=dict(reference=ref)),patch('drive_references.resolve',return_value=(self.config,[dict(id=ref['id'],version=1)])):
            capture.capture(token,choice,self.session,self.revision,self.job,root=self.root/'tools')
        self.assertEqual(self.posts[-1][1]['files'],[dict(id=ref['id'],kind='file',revision=1)])
        self.assertEqual(path.read_bytes(),before)
