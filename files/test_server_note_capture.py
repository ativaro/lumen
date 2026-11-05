"""Reviewed Server Notes capture: durable intent, private defaults, explicit replay."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

import lumen_connect
from interop_data import Registry, validate_ref
from server_app_session import AppSession, Binding
import server_note_capture as capture
import interop_targets


class NotesCaptureTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.registry=Registry(self.root/'tools')
        self.config=dict(server='https://synthetic.invalid',device_id=str(uuid4()),token='private-pairing-token')
        self.binding=Binding(self.config['server'],str(uuid4()),self.config['device_id'],'notes')
        self.revision=4;self.job=SimpleNamespace(check=lambda:None)
        source=dict(app='files',kind='file',id='/synthetic/source.txt',title='Local source',path='/synthetic/source.txt')
        self.payload=dict(title='Selected text',text='test\n\n\n\n\ntest1',paths=[],source=source,source_url=self.registry.register(source))
        self.token=self.registry.enqueue('wissen',capture.ACTION,self.payload)
        self.choice=dict(id='',title='Captured note',mode='copy',due='',token=self.token)
        self.rows={};self.operations={};self.wire=[];self.lose=False;self.after_post=lambda:None
        self.session=self.new_session()
        for active in (patch.object(lumen_connect,'read_config',side_effect=lambda:dict(self.config)),patch.object(lumen_connect,'request',side_effect=self.profile)):
            active.start();self.addCleanup(active.stop)

    def new_session(self):
        session=AppSession(self.config,self.binding);session._cookie=b'x'*43;session._deadline=session._clock()+600
        session.state='ready';session.access='read_write';session.request=self.request
        return session

    def profile(self,config,path,body=None,**kwargs):
        self.assertEqual(path,'/bridge/me')
        return dict(id=self.binding.account,device_id=self.binding.device,permissions_revision=self.revision,capabilities=['notes','drive'])

    def request(self,path,body=None,**kwargs):
        self.wire.append((path,body));self.assertEqual(kwargs.get('max_bytes'),1024**2)
        if path=='/api/note-collections':return [dict(name='Work',can_write=True,count=0),dict(name='Read only',can_write=False,count=1)]
        if body is not None:
            self.assertEqual(path,'/api/documents')
            request=self.registry.request(self.token)
            self.assertEqual(request['state'],'applying');self.assertTrue(request['choice']['note_capture']['attempted'])
            self.assertEqual(request['choice']['note_capture']['document_hash'],capture._digest(body))
            self.assertFalse(body['ai_allowed']);self.assertFalse(body['ai_override'])
            previous=self.operations.get(body['operation_id'])
            if previous:
                self.assertEqual(previous[0],body);row=self.rows[previous[1]]
            else:
                row=dict(body,id=str(uuid4()),kind='note',revision=1,deleted=False,can_write=True)
                self.rows[row['id']]=row;self.operations[body['operation_id']]=(deepcopy(body),row['id'])
            self.after_post()
            if self.lose:self.lose=False;raise TimeoutError('Lost after commit')
            return deepcopy(row)
        return deepcopy(self.rows[path.rsplit('/',1)[-1]])

    def apply(self,**kwargs):
        return capture.capture(self.token,self.choice,self.session,self.revision,self.job,root=self.root/'tools',**kwargs)

    def test_text_saved_once_private_with_blank_lines_and_durable_return_path(self):
        ref=self.apply();self.assertEqual(ref['app'],'note');self.assertEqual(ref['version'],2)
        self.assertEqual(ref['locator'],dict(server=self.binding.origin,account=self.binding.account))
        row=self.rows[ref['id']];self.assertTrue(row['body'].startswith(self.payload['text']))
        self.assertIn(self.payload['source_url'],row['body']);self.assertFalse(row['ai_allowed'])
        request=self.registry.request(self.token);self.assertEqual(request['state'],'done');self.assertEqual(self.registry.resolve(request['result']),ref)
        self.assertEqual(self.apply(),ref);self.assertEqual(len(self.operations),1)
        self.assertEqual(sum(body is not None for _,body in self.wire),1)
        self.assertNotIn(self.config['token'],self.registry.library.db.read_bytes().decode(errors='ignore'))
        self.assertEqual(self.registry.related(request['result'])[0]['id'],self.payload['source']['id'])

    def test_writable_collections_come_from_server_without_local_notebook(self):
        with patch('wissen_data.Notebook',side_effect=AssertionError('must not read local Notes')):
            rows=interop_targets.choices('wissen.import',session=self.session,permissions_revision=self.revision,job=self.job)
        self.assertEqual([r['id'] for r in rows],['','Work'])
        with self.assertRaises(ValueError):interop_targets.choices('wissen.import')

    def test_timeout_never_repeats_automatically_but_explicit_same_uuid_replay_is_safe(self):
        self.lose=True
        with self.assertRaises(TimeoutError):self.apply()
        self.assertEqual(len(self.rows),1);self.assertEqual(self.registry.request(self.token)['state'],'pending')
        with self.assertRaisesRegex(ValueError,'unklar'):self.apply()
        self.assertEqual(sum(body is not None for _,body in self.wire),1)
        ref=self.apply(retry=True);self.assertEqual(len(self.rows),1);self.assertEqual(ref['id'],next(iter(self.rows)))
        posts=[body for _,body in self.wire if body is not None];self.assertEqual(posts[0],posts[1])

    def test_lost_registry_finish_recovers_by_confirmed_id_without_another_post(self):
        finish=Registry.finish
        with patch.object(Registry,'finish',side_effect=OSError('local fs interruption')):
            with self.assertRaises(OSError):self.apply()
        self.assertEqual(len(self.rows),1)
        result=self.apply();self.assertEqual(result['id'],next(iter(self.rows)))
        self.assertEqual(sum(body is not None for _,body in self.wire),1)

    def test_pairing_change_after_server_commit_never_finishes_or_exposes_old_result(self):
        self.after_post=lambda:self.config.update(token='new-token')
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(len(self.rows),1);self.assertEqual(self.registry.request(self.token)['state'],'pending')
        self.session=self.new_session();self.after_post=lambda:None
        with self.assertRaises(ValueError):self.apply(retry=True)
        self.assertEqual(sum(body is not None for _,body in self.wire),1)

    def test_permissions_change_after_commit_blocks_result_and_replay(self):
        self.after_post=lambda:setattr(self,'revision',5)
        with self.assertRaises(ValueError):self.apply()
        with self.assertRaises(ValueError):self.apply(retry=True)
        self.assertEqual(sum(body is not None for _,body in self.wire),1)

    def test_changed_confirmed_choice_is_refused_even_if_generated_text_matches(self):
        self.lose=True
        with self.assertRaises(TimeoutError):self.apply()
        self.choice['mode']='link'
        with self.assertRaises(ValueError):self.apply(retry=True)
        self.assertEqual(sum(body is not None for _,body in self.wire),1)

    def test_local_files_and_legacy_writer_are_refused_before_network(self):
        path=self.root/'local.txt';path.write_text('Original')
        payload=dict(self.payload,paths=[str(path)])
        self.token=self.registry.enqueue('wissen',capture.ACTION,payload);self.choice['token']=self.token
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.wire,[]);self.assertEqual(path.read_text(),'Original')
        self.assertFalse(hasattr(interop_targets,'_wissen'))
        with self.assertRaises(ValueError):interop_targets.apply('wissen.import',self.payload,self.choice,self.job,self.root/'tools')

    def test_cancel_or_readonly_session_cannot_start_write(self):
        for control in ('cancel','readonly','revision'):
            with self.subTest(control=control):
                self.job=SimpleNamespace(check=lambda:None);self.session.access='read_write'
                if control=='cancel':self.job=SimpleNamespace(check=lambda:(_ for _ in ()).throw(ValueError('cancelled')))
                if control=='readonly':self.session.access='read'
                with self.assertRaises(ValueError):capture.capture(self.token,self.choice,self.session,99 if control=='revision' else self.revision,self.job,root=self.root/'tools')
        self.assertEqual(self.rows,{})

    def test_existing_drive_ref_is_a_server_link_not_a_download_or_file_copy(self):
        ref=dict(app='files',kind='drive_file',id=str(uuid4()),title='Report.pdf',locator=dict(server=self.binding.origin,account=self.binding.account))
        payload=dict(self.payload,text='',source=ref,source_url=self.registry.register(ref),references=[ref]);self.token=self.registry.enqueue('wissen',capture.ACTION,payload)
        self.choice.update(token=self.token,mode='link')
        resolved=dict(id=str(uuid4()),version=2,revision=7)
        nav=dict(resolved=resolved,route='/?app=files&file='+resolved['id'])
        with patch('server_app_links.drive_navigation',return_value=nav) as navigation,patch('drive_transport.download',side_effect=AssertionError('no download')):
            result=self.apply();navigation.assert_called_once_with(ref,self.job)
        row=self.rows[result['id']];self.assertIn(self.binding.origin+nav['route'],row['body'])
        self.assertNotIn('lumen:',row['body']);self.assertNotIn('file://',row['body']);self.assertEqual(self.registry.request(self.token)['choice']['note_capture']['references'],[dict(reference=ref,resolved=resolved)])

    def test_foreign_drive_selection_is_refused_without_a_write_or_download(self):
        ref=dict(app='files',kind='drive_file',id=str(uuid4()),title='Private.pdf',locator=dict(server=self.binding.origin,account=str(uuid4())))
        self.token=self.registry.enqueue('wissen',capture.ACTION,dict(self.payload,references=[ref]));self.choice.update(token=self.token,mode='link')
        with patch('server_app_links.drive_navigation',side_effect=AssertionError('foreign binding must fail before resolution')):
            with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.rows,{})

    def test_mismatched_server_receipt_never_finishes_and_blocks_automatic_retry(self):
        self.after_post=lambda:self.rows[next(iter(self.rows))].update(ai_allowed=True)
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.registry.request(self.token)['state'],'pending')
        self.assertNotIn('receipt',self.registry.request(self.token)['choice']['note_capture'])
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(sum(body is not None for _,body in self.wire),1)

    def test_v2_registry_separates_server_account_app_and_keeps_legacy_refs(self):
        ref=dict(version=2,app='note',id=str(uuid4()),title='Server note',locator=dict(server=self.binding.origin,account=self.binding.account))
        url=self.registry.register(ref);self.assertEqual(self.registry.resolve(url),ref)
        self.assertEqual(self.registry.register(dict(ref,title='Renamed')),url)
        self.assertNotEqual(self.registry.register(dict(ref,locator=dict(ref['locator'],account=str(uuid4())))),url)
        with self.assertRaises(ValueError):self.registry.resolve(url+'?page=1')
        self.assertEqual(validate_ref(self.payload['source']),self.payload['source'])
