"""One reviewed local original, using the existing durable handoff and upload wire."""
import hashlib
import os
from pathlib import Path
import tempfile
import json
import ssl
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

import drive_references as drive
import drive_transport as transport
from interop_data import Registry
from interop_sources import from_paths
import server_file_import as imports
import lumen_service

NATIVE_REQUEST = drive.lumen_connect.request


class FileImportTest(unittest.TestCase):
    def setUp(self):
        # A runtime folder of its own: the test never reaches or replaces the user's running service, and the
        # service it starts ends itself once the folder is removed.
        runtime = self.enterContext(tempfile.TemporaryDirectory(prefix='lumen-run-'))
        self.enterContext(patch.dict(os.environ, XDG_RUNTIME_DIR=runtime))
        self.enterContext(patch.object(lumen_service, '_checked', None))
        self.temp=tempfile.TemporaryDirectory(dir=os.environ['LUMEN_IMPORT_FIXTURES'])
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.path=self.base/'Selected.pdf'
        self.original=b'One explicitly selected original\n';self.path.write_bytes(self.original)
        self.registry=Registry(self.base/'tools')
        payload=from_paths([str(self.path)])
        payload['source_url']=self.registry.register(payload['source'])
        self.token=self.registry.enqueue('files','files.drive_import',payload)
        self.account=str(uuid4());self.device=str(uuid4());self.folder=str(uuid4())
        self.config=dict(server='https://synthetic.invalid',token='never-persist-this-bearer')
        self.destination=dict(app='files',kind='drive_folder',id=self.folder,title='Chosen folder',
                              locator=dict(server=self.config['server'],account=self.account))
        self.choice=dict(id=self.folder,title='Selected.pdf',mode='copy',due='',token=self.token)
        self.folder_row=dict(id=self.folder,name='Chosen folder',revision=4,trashed=False,can_write=True)
        self.cache=dict(files={},folders={self.folder:self.folder_row})
        self.sessions={};self.calls=[];self.lost_finish=False;self.after_finish=lambda:None
        self.after_begin=lambda:None;self.after_chunk=lambda:None
        self.job=SimpleNamespace(check=lambda:None)
        patches=[patch.object(drive.lumen_connect,'read_config',side_effect=lambda:dict(self.config)),
                 patch.object(drive.lumen_connect,'request',side_effect=self.profile),
                 patch.object(drive.sync,'inventory',side_effect=lambda _,*,job=None:self.cache),
                 patch.object(transport,'request',side_effect=self.wire)]
        for active in patches:active.start();self.addCleanup(active.stop)

    def profile(self,config,path,body=None):
        self.assertEqual(path,'/bridge/me')
        return dict(id=self.account,device_id=self.device)

    def wire(self,config,path,body=None,method='POST',content_type='application/json'):
        self.calls.append((path,method,body))
        parts=path.split('?')[0].strip('/').split('/')
        if len(parts)==2 and method=='POST':
            key=parts[1]
            if key not in self.sessions:
                self.sessions[key]=dict(id=str(uuid4()),body=dict(body),data=b'',finished=False)
            session=self.sessions[key]
            if session['body']!=body:raise ValueError('Request payload changed')
            self.after_begin()
            return dict(id=session['id'],size=body['size'],offset=len(session['data']),completed=session['finished'])
        session=next(value for value in self.sessions.values() if value['id']==parts[1])
        if method=='PUT':
            session['data']+=body
            self.after_chunk()
            return dict(offset=len(session['data']))
        self.assertEqual(parts[2],'finish')
        if not session['finished']:
            self.assertEqual(hashlib.sha256(session['data']).hexdigest(),session['body']['sha256'])
            row=dict(id=session['id'],family=str(uuid4()),version=1,revision=1,
                     name=session['body']['name'],folder_id=self.folder,size=len(session['data']),
                     sha256=hashlib.sha256(session['data']).hexdigest(),current=True,trashed=False,purpose='user')
            session.update(finished=True,row=row);self.cache['files'][row['family']]=row
            self.after_finish()
            if self.lost_finish:
                self.lost_finish=False
                raise OSError('Acknowledgement lost after commit')
        return dict(session['row'])

    def prepare(self):
        return imports.prepare(self.token,self.choice,self.destination,self.job,root=self.base/'tools')

    def apply(self):
        return imports.apply(self.token,self.job,root=self.base/'tools')

    def test_cancel_during_https_target_resolution_or_device_response_stops_followup(self):
        from lumen_jobs import Job
        from tools_data import Cancelled
        # A throwaway CA and the server certificate it signed: rustls, like browsers, refuses a CA certificate
        # as the server's own.
        cert=self.base/'target-ca.pem';key=self.base/'target-key.pem';leaf=self.base/'target-leaf.pem'
        (self.base/'target.ext').write_text('basicConstraints=critical,CA:FALSE\nsubjectAltName=IP:127.0.0.1\n'
                                            'extendedKeyUsage=serverAuth\nauthorityKeyIdentifier=keyid\n')
        for command in (['req','-x509','-newkey','rsa:2048','-nodes','-subj','/CN=Fixture CA','-days','1',
                         '-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign',
                         '-out',str(cert),'-keyout',str(self.base/'target-ca.key')],
                        ['req','-new','-newkey','rsa:2048','-nodes','-subj','/CN=127.0.0.1',
                         '-out',str(self.base/'target.csr'),'-keyout',str(key)],
                        ['x509','-req','-days','1','-in',str(self.base/'target.csr'),'-CA',str(cert),
                         '-CAkey',str(self.base/'target-ca.key'),'-set_serial','2','-extfile',str(self.base/'target.ext'),
                         '-out',str(leaf)]):
            subprocess.run(['openssl',*command],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        entered=threading.Event();release=threading.Event();calls=[];gate=[1];owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                calls.append(dict(path=self.path,bearer=bool(self.headers.get('Authorization')),
                                  cookie=bool(self.headers.get('Cookie'))))
                held=len(calls)==gate[0]
                if held:entered.set();release.wait(timeout=5)
                device='invalid-after-cancel' if held and gate[0]==2 else owner.device
                raw=json.dumps(dict(id=owner.account,device_id=device)).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(raw)))
                self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(raw)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(leaf,key)
        server.socket=context.wrap_socket(server.socket,server_side=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            self.config.update(server='https://127.0.0.1:'+str(server.server_port),ca_file=str(cert))
            self.destination['locator']['server']=self.config['server'];self.prepare()
            saved=dict(self.registry.request(self.token)['choice'])
            for step in (1,2):
                with self.subTest(blocked_native_response=step):
                    gate[0]=step;calls.clear();entered.clear();release.clear();self.job=Job(lambda _:None)
                    with patch.object(drive.lumen_connect,'request',side_effect=NATIVE_REQUEST),ThreadPoolExecutor(max_workers=1) as pool:
                        future=pool.submit(self.apply)
                        try:
                            self.assertTrue(entered.wait(timeout=5));self.job.cancelled.set()
                        finally:release.set()
                        with self.assertRaises(Cancelled):future.result(timeout=5)
                    self.assertEqual([c['path'] for c in calls],['/bridge/me']*step)
                    self.assertTrue(all(c['bearer'] and not c['cookie'] for c in calls))
                    self.assertEqual(self.calls,[]);self.assertEqual(self.registry.request(self.token)['state'],'pending')
                    self.assertEqual(self.registry.request(self.token)['choice'],saved)
                    self.assertEqual(len(self.registry.history()),1);self.assertEqual(self.path.read_bytes(),self.original)
        finally:
            release.set();server.shutdown();server.server_close();thread.join(timeout=5)

    def test_capture_open_and_cancel_do_not_upload(self):
        self.registry.resolve(self.registry.request(self.token)['payload']['source_url'])
        self.assertIsNone(imports.prepare(self.token,None,self.destination,self.job,root=self.base/'tools'))
        self.assertEqual(self.calls,[])
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.calls,[]);self.assertEqual(self.path.read_bytes(),self.original)

    def test_reviewed_copy_preserves_family_version_provenance_and_original(self):
        self.prepare()
        self.assertEqual(self.calls,[])
        request=self.registry.request(self.token)
        self.assertNotIn(self.config['token'],str(request))
        self.assertIn('drive_import',request['choice'])
        result=self.apply()
        row=next(iter(self.cache['files'].values()))
        self.assertEqual(result['action'],'upload')
        self.assertEqual(result['request_id'],str(UUID(self.token)))
        self.assertEqual(result['reference']['id'],row['family'])
        self.assertEqual(result['resolved'],{key:row[key] for key in ('id','version','revision')})
        self.assertNotEqual(row['family'],row['id'])
        self.assertEqual(self.registry.resolve(result['return_to'])['path'],str(self.path))
        self.assertEqual(result['source'],request['payload']['source'])
        self.assertEqual(self.registry.request(self.token)['state'],'done')
        self.assertEqual(self.path.read_bytes(),self.original)
        bodies=[body for path,method,body in self.calls if method=='POST' and path.count('/')==2]
        self.assertEqual(len(bodies),1)
        self.assertFalse(any(str(self.base) in str(body) for body in bodies))
        self.assertEqual(self.registry.related(result['return_to'])[0]['url'],self.registry.request(self.token)['result'])

    def test_retry_after_lost_ack_reuses_request_and_creates_no_second_file(self):
        self.prepare();self.lost_finish=True
        with self.assertRaises(OSError):self.apply()
        self.assertEqual(self.registry.request(self.token)['state'],'pending')
        self.assertEqual(len(self.sessions),1)
        first=dict(self.registry.request(self.token)['choice'])
        result=self.apply()
        choice=self.registry.request(self.token)['choice']
        self.assertEqual({key:value for key,value in choice.items() if key!='drive_import_receipt'},first)
        row=next(iter(self.cache['files'].values()))
        self.assertEqual(choice['drive_import_receipt'],{key:row[key] for key in
                         ('id','family','version','revision','sha256','size','name','folder_id')})
        self.assertEqual(len(self.sessions),1);self.assertEqual(len(self.cache['files']),1)
        self.assertEqual(sum(method=='PUT' for _,method,_ in self.calls),1)
        calls=len(self.calls);again=self.apply()
        self.assertEqual(again,result);self.assertEqual(len(self.calls),calls)

    def test_wrong_choice_source_or_target_cannot_start_transfer(self):
        for change in (dict(mode='link'),dict(mode='live'),dict(token=uuid4().hex),dict(id=str(uuid4()))):
            with self.subTest(change=change),self.assertRaises(ValueError):
                imports.prepare(self.token,dict(self.choice,**change),self.destination,self.job,root=self.base/'tools')
        wrong=dict(self.destination,locator=dict(self.destination['locator'],server='https://other.invalid'))
        with self.assertRaises(ValueError):imports.prepare(self.token,self.choice,wrong,self.job,root=self.base/'tools')
        self.assertEqual(self.calls,[])

    def test_prepared_intent_cannot_be_redirected_or_reapproved_with_same_key(self):
        self.prepare()
        target=dict(self.destination,id=str(uuid4()))
        with self.assertRaises(ValueError):imports.prepare(self.token,dict(self.choice,id=target['id']),target,self.job,root=self.base/'tools')
        self.assertEqual(self.calls,[])
        self.path.write_bytes(b'changed after review')
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.calls,[])
        self.assertEqual(self.path.read_bytes(),b'changed after review')

    def test_account_device_connection_target_and_grant_changes_fail_closed(self):
        self.prepare()
        for field,value in (('account',str(uuid4())),('device',str(uuid4()))):
            old=getattr(self,field);setattr(self,field,value)
            with self.subTest(field=field),self.assertRaises(ValueError):self.apply()
            setattr(self,field,old)
        self.config['server']='https://other.invalid'
        with self.assertRaises(ValueError):self.apply()
        self.config['server']=self.destination['locator']['server']
        for change in (dict(can_write=False),dict(trashed=True),dict(revision=5)):
            old=dict(self.folder_row);self.folder_row.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):self.apply()
            self.folder_row.clear();self.folder_row.update(old)
        self.assertEqual(self.calls,[])

    def test_same_device_token_rotation_before_retry_keeps_the_same_intent(self):
        self.prepare();self.config['token']='rotated-before-transfer'
        self.assertEqual(self.apply()['request_id'],str(UUID(self.token)))
        self.assertEqual(len(self.sessions),1)

    def test_completed_replay_cannot_claim_a_changed_remote_version_name_or_folder(self):
        self.prepare();result=self.apply()
        row=next(iter(self.cache['files'].values()));original=dict(row);calls=len(self.calls)
        for change in (dict(id=str(uuid4()),version=2),dict(sha256='0'*64),dict(size=row['size']+1),
                       dict(name='renamed.pdf'),dict(folder_id=str(uuid4())),dict(revision=2)):
            row.clear();row.update(original);row.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):self.apply()
            self.assertEqual(len(self.calls),calls)
            self.assertEqual(self.registry.request(self.token)['state'],'done')
        row.clear();row.update(original)
        self.assertEqual(self.apply(),result)

    def test_retry_after_local_finish_failure_keeps_the_persisted_exact_receipt(self):
        plan=self.prepare()
        with patch.object(Registry,'finish',side_effect=OSError('Local finish interrupted')),self.assertRaises(OSError):self.apply()
        pending=self.registry.request(self.token)
        self.assertEqual(pending['state'],'pending')
        self.assertEqual(pending['choice']['drive_import'],plan)
        self.assertIn('drive_import_receipt',pending['choice'])
        result=self.apply()
        self.assertEqual(self.registry.request(self.token)['choice'],pending['choice'])
        self.assertEqual(len(self.sessions),1);self.assertEqual(len(self.cache['files']),1)
        self.assertEqual(sum(method=='PUT' for _,method,_ in self.calls),1)
        self.assertEqual(self.prepare(),plan)
        self.path.unlink()
        self.assertEqual(self.apply(),result)

    def test_completed_replay_requires_its_receipt_and_current_authorization(self):
        self.prepare();self.apply();calls=len(self.calls)
        row=next(iter(self.cache['files'].values()))
        row['trashed']=True
        with self.assertRaises(ValueError):self.apply()
        row['trashed']=False
        account=self.account;self.account=str(uuid4())
        with self.assertRaises(ValueError):self.apply()
        self.account=account
        saved=dict(self.cache['files']);self.cache['files'].clear()
        with self.assertRaises(ValueError):self.apply()
        self.cache['files'].update(saved)
        choice=self.registry.request(self.token)['choice'];del choice['drive_import_receipt']
        import json
        with self.registry.library.connect() as db:
            db.execute('UPDATE handoffs SET choice=? WHERE id=?',(json.dumps(choice),self.token))
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(len(self.calls),calls)
        self.assertEqual(self.path.read_bytes(),self.original)

    def test_native_source_names_do_not_need_to_match_the_reviewed_drive_name(self):
        for index,name in enumerate((' original\\draft.pdf','a'*201+'.pdf'),1):
            with self.subTest(name=name):
                target=self.base/name;self.path.rename(target);self.path=target
                payload=from_paths([str(target)])
                payload['source_url']=self.registry.register(payload['source'])
                self.token=self.registry.enqueue('files','files.drive_import',payload)
                self.choice.update(token=self.token,title=f'Portable copy {index}.pdf')
                self.prepare();result=self.apply()
                self.assertEqual(result['reference']['title'],f'Portable copy {index}.pdf')
                self.assertEqual(target.read_bytes(),self.original)
                self.assertEqual(self.registry.resolve(result['return_to'])['path'],str(target))

    def test_concurrent_reviews_cannot_redirect_the_same_durable_intent(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier=Barrier(2)
        original=imports.checksum
        second=dict(self.destination,id=str(uuid4()),title='Other folder')
        self.cache['folders'][second['id']]=dict(self.folder_row,id=second['id'],name=second['title'])
        def hashed(*args):
            value=original(*args);barrier.wait(timeout=3);return value
        def reviewed(destination):
            try:
                return imports.prepare(self.token,dict(self.choice,id=destination['id']),destination,self.job,root=self.base/'tools')
            except ValueError as error:return error
        with patch.object(imports,'checksum',side_effect=hashed),ThreadPoolExecutor(max_workers=2) as workers:
            values=list(workers.map(reviewed,[self.destination,second]))
        self.assertEqual(sum(isinstance(value,dict) for value in values),1)
        self.assertEqual(sum(isinstance(value,ValueError) for value in values),1)
        selected=next(value for value in values if isinstance(value,dict))
        self.assertEqual(self.registry.request(self.token)['choice']['drive_import'],selected)
        self.assertEqual(self.calls,[])

    def test_changed_source_after_finish_is_not_reported_as_success(self):
        self.prepare()
        self.after_finish=lambda:self.path.write_bytes(b'Changed while transfer finished')
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.registry.request(self.token)['state'],'pending')
        self.assertEqual(len(self.sessions),1)
        self.assertEqual(self.path.read_bytes(),b'Changed while transfer finished')

    def test_replacement_between_source_check_and_transport_open_sends_no_requests(self):
        self.prepare();upload=transport.upload
        replacement=b'X'*len(self.original)
        def replace_then_upload(*args,**kwargs):
            other=self.base/'replacement.pdf';other.write_bytes(replacement);other.replace(self.path)
            return upload(*args,**kwargs)
        def reject_unconfirmed_finish(*args,**kwargs):
            if args[1].endswith('/finish'):raise ValueError('Synthetic digest mismatch')
            return self.wire(*args,**kwargs)
        with patch.object(transport,'upload',side_effect=replace_then_upload), \
             patch.object(transport,'request',side_effect=reject_unconfirmed_finish),self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.calls,[])
        self.assertEqual(self.sessions,{})
        self.assertEqual(self.registry.request(self.token)['state'],'pending')
        self.assertEqual(self.path.read_bytes(),replacement)

    def test_changed_destination_after_finish_is_not_reported_as_success(self):
        self.prepare();self.after_finish=lambda:self.folder_row.update(revision=5)
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.registry.request(self.token)['state'],'pending')
        self.assertEqual(self.path.read_bytes(),self.original)

    def test_selected_output_name_is_used_without_renaming_original(self):
        self.choice['title']='Reviewed copy.pdf'
        self.prepare();result=self.apply()
        self.assertEqual(result['reference']['title'],'Reviewed copy.pdf')
        self.assertTrue(self.path.is_file());self.assertFalse((self.base/'Reviewed copy.pdf').exists())

    def test_cancel_after_chunk_preserves_original_and_resumes_same_upload(self):
        self.prepare()
        cancelled=[False]
        self.job.check=lambda:(_ for _ in ()).throw(ValueError('Cancelled')) if cancelled[0] else None
        self.after_chunk=lambda:cancelled.__setitem__(0,True)
        with self.assertRaisesRegex(ValueError,'Cancelled'):self.apply()
        self.assertFalse(next(iter(self.sessions.values()))['finished'])
        self.assertEqual(self.registry.request(self.token)['state'],'pending')
        self.assertEqual(self.path.read_bytes(),self.original)
        cancelled[0]=False;self.after_chunk=lambda:None
        self.apply()
        self.assertEqual(len(self.sessions),1)
        self.assertEqual(sum(method=='PUT' for _,method,_ in self.calls),1)

    def test_connection_change_after_begin_sends_no_file_bytes(self):
        self.prepare();self.after_begin=lambda:self.config.update(token='changed-before-first-chunk')
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(sum(method=='PUT' for _,method,_ in self.calls),0)
        self.assertEqual(self.registry.request(self.token)['state'],'pending')

    def test_wrong_upload_session_result_cannot_be_reported_as_success(self):
        self.prepare()
        original=self.wire
        def wrong(*args,**kwargs):
            value=original(*args,**kwargs)
            return dict(value,id=str(uuid4())) if args[1].endswith('/finish') else value
        with patch.object(transport,'request',side_effect=wrong),self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.registry.request(self.token)['state'],'pending')

    def test_cancel_and_post_transfer_changes_preserve_original_and_pending_receipt(self):
        self.prepare()
        self.job.check=lambda:(_ for _ in ()).throw(ValueError('Cancelled'))
        with self.assertRaisesRegex(ValueError,'Cancelled'):self.apply()
        self.assertEqual(self.calls,[])
        self.job.check=lambda:None
        self.after_finish=lambda:self.config.update(token='changed-during-transfer')
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.registry.request(self.token)['state'],'pending')
        self.assertEqual(self.path.read_bytes(),self.original)
        self.assertEqual(len(self.sessions),1)

    def test_symlink_and_non_file_sources_are_rejected(self):
        self.path.unlink();self.path.symlink_to(self.base/'elsewhere')
        (self.base/'elsewhere').write_bytes(b'not selected')
        with self.assertRaises((OSError,ValueError)):self.prepare()
        self.path.unlink();self.path.mkdir()
        with self.assertRaises((OSError,ValueError)):self.prepare()
        self.assertEqual(self.calls,[])


if __name__=='__main__':unittest.main()
