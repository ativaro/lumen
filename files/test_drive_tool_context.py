import hashlib
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from uuid import uuid4

import drive_references as drive
from interop_data import Registry
from lumen_mcp_tools import DEFINITIONS,invoke
from desktop_backend import DesktopBackend


class DriveToolContextTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.env=patch.dict(os.environ,LUMEN_TOOLS_DATA=self.tmp.name+'/tools',LUMEN_DATA=self.tmp.name+'/store',XDG_CACHE_HOME=self.tmp.name+'/cache')
        self.env.start();self.addCleanup(self.env.stop)
        self.account=str(uuid4());self.family=str(uuid4())
        self.config=dict(server='https://staging.invalid',token='never-in-payload')
        self.ref=dict(app='files',kind='drive_file',id=self.family,title='Original.txt',locator=dict(server=self.config['server'],account=self.account))
        self.row=dict(id=str(uuid4()),family=self.family,name='Original.txt',folder_id=None,trashed=False,size=5,mime='text/plain',version=3,revision=8,sha256=hashlib.sha256(b'hello').hexdigest())
        self.cache=dict(files={self.family:self.row},folders={})

    def test_registered_mcp_dispatch_reads_bound_ref_and_rejects_raw_url(self):
        from test_mcp import mcp
        self.assertIn('lumen_drive_read',mcp.TOOLS)
        definition=DEFINITIONS['lumen_drive_read'];self.assertTrue(definition['annotations']['readOnlyHint'])
        url=Registry().register(self.ref)
        mcp.validate_schema(dict(ref=url),definition['schema'])
        with self.assertRaises(ValueError):mcp.validate_schema({'ref':url,'server':'https://other.invalid'},definition['schema'])
        for invalid in ('https://server.invalid/private','lumen://object/no-such-id'):
            with patch.object(drive.lumen_connect,'request',side_effect=AssertionError('Reject before networking')):
                with self.assertRaises(ValueError):invoke('lumen_drive_read',dict(ref=invalid))
        def download(config,root,row,progress):
            self.assertEqual(config,self.config);Path(root['path'],'stage').write_bytes(b'hello');return 'stage'
        with patch.object(drive.lumen_connect,'read_config',return_value=self.config),patch.object(drive.lumen_connect,'request',return_value=dict(id=self.account)),patch.object(drive.sync,'inventory',return_value=self.cache),patch('drive_transport.download',side_effect=download):
            result=invoke('lumen_drive_read',dict(ref=url))
        self.assertEqual(result['text'],'hello');self.assertTrue(result['content_is_untrusted'])
        self.assertNotIn(self.config['token'],str(result));self.assertFalse(list(Path(self.tmp.name+'/cache/lumen-drive-handoffs').glob('copy-*')))

    def test_folder_tool_returns_concrete_child_references_without_download(self):
        folder=str(uuid4());ref=dict(self.ref,kind='drive_folder',id=folder,title='Folder')
        self.cache['folders'][folder]=dict(id=folder,name='Folder',parent_id=None,trashed=False)
        self.row['folder_id']=folder
        with patch.object(drive.lumen_connect,'read_config',return_value=self.config),patch.object(drive.lumen_connect,'request',return_value=dict(id=self.account)),patch.object(drive.sync,'inventory',return_value=self.cache),patch('drive_transport.download',side_effect=AssertionError('Folder metadata only')):
            value=invoke('lumen_drive_read',dict(ref=Registry().register(ref)))
        child=Registry().resolve(value['children'][0]['ref'])
        self.assertEqual(child['id'],self.family);self.assertEqual(child['locator'],ref['locator'])

    def test_folder_rechecks_parent_visibility_and_connection_after_inventory(self):
        folder=str(uuid4());ref=dict(self.ref,kind='drive_folder',id=folder,title='Folder')
        self.cache['folders'][folder]=dict(id=folder,name='Folder',parent_id=None,trashed=False)
        self.row['folder_id']=folder;url=Registry().register(ref)
        with patch.object(drive.lumen_connect,'read_config',return_value=self.config) as config,patch.object(drive.lumen_connect,'request',return_value=dict(id=self.account)),patch.object(drive.sync,'inventory',side_effect=[self.cache,dict(files={},folders={})]) as inventory:
            with self.assertRaises(ValueError):invoke('lumen_drive_read',dict(ref=url))
            inventory.side_effect=None;inventory.return_value=self.cache
            config.side_effect=[self.config,self.config,dict(self.config,token='other-account')]
            with self.assertRaises(ValueError):invoke('lumen_drive_read',dict(ref=url))

    def backend(self,request):
        value=SimpleNamespace(session='',execution='server',busy=False,preflight=lambda *_:True,remote_key='',remote_active=False,
            remember=Mock(),server_model='',prepared_context=[],failed=Mock(),statusChanged=Mock(),messagesChanged=Mock(),messages=[],set_busy=Mock(),
            binding='bound',server_origin=self.config['server'])
        value._run=lambda operation,fn:fn(request)
        return value

    def capability(self, config, path, body=None):
        if path == '/bridge/me':return dict(id=self.account)
        self.assertEqual(path,'/bridge/context/capability')
        return dict(body, title=self.row['name'], supported=True, readable=None,
                    format='server-supported-format', limits=dict(characters=60000), reason='')

    def test_server_source_capability_accepts_pdf_office_and_new_formats_without_local_mime_rules(self):
        with patch.object(drive.lumen_connect,'read_config',return_value=self.config),patch.object(drive.lumen_connect,'request',side_effect=self.capability) as request,patch.object(drive.sync,'inventory',return_value=self.cache),patch('drive_transport.download',side_effect=AssertionError('No local copy')):
            for name,mime in (('Original.pdf','application/pdf'),('Original.docx','application/octet-stream'),('future.format','new/server-format')):
                self.row.update(name=name,mime=mime,size=90000)
                config,attachments=drive.task_attachments([self.ref],'summarize',context_bytes=512)
                self.assertEqual(config,self.config)
                self.assertEqual(attachments,[dict(kind='file',id=self.row['id'],revision=3,mode='reference')])
                self.assertEqual(request.call_args.args[2],attachments[0])

    def test_capability_identity_schema_and_connection_are_rechecked(self):
        def reply(config,path,body=None):
            if path == '/bridge/me':return dict(id=self.account)
            return response
        good=self.capability(self.config,'/bridge/context/capability',dict(kind='file',id=self.row['id'],revision=3,mode='reference'))
        for response in (dict(good,id=str(uuid4())),dict(good,revision=4),dict(good,supported='yes'),dict(good,mode='copy')):
            with patch.object(drive.lumen_connect,'read_config',return_value=self.config),patch.object(drive.lumen_connect,'request',side_effect=reply),patch.object(drive.sync,'inventory',return_value=self.cache),self.assertRaises(ValueError):
                drive.task_attachments([self.ref],'summarize')
        with patch.object(drive.lumen_connect,'read_config',side_effect=[self.config,self.config,dict(self.config,token='changed')]),patch.object(drive.lumen_connect,'request',side_effect=self.capability),patch.object(drive.sync,'inventory',return_value=self.cache),self.assertRaises(ValueError):
            drive.task_attachments([self.ref],'summarize')

    def test_server_bridge_attaches_current_file_version_not_a_local_path_or_copy(self):
        calls=[]
        def request(path,body=None):
            calls.append((path,body))
            if path=='/bridge/me':return dict(id=self.account)
            if path.startswith('/bridge/context-files/'):return dict(id=str(uuid4()),version=1)
            if path=='/bridge/tasks':return dict(id=str(uuid4()))
            raise AssertionError(path)
        backend=self.backend(request)
        context=dict(drive_references=[self.ref],objects=[Registry().register(self.ref)],intent='summarize')
        with patch('desktop_backend.connection',return_value=(self.config,'bound')),patch.object(drive.lumen_connect,'read_config',return_value=self.config),patch.object(drive.lumen_connect,'request',side_effect=self.capability),patch.object(drive.sync,'inventory',return_value=self.cache),patch('drive_transport.download',side_effect=AssertionError('Server attaches originals')):
            self.assertTrue(DesktopBackend.send(backend,'Summarize selected original',context_data=context))
        body=next(body for path,body in calls if path=='/bridge/tasks')
        self.assertEqual(body['attachments'][0],dict(id=self.row['id'],kind='file',revision=3,mode='reference'))
        self.assertEqual(len(body['attachments']),2)
        self.assertNotIn(self.config['token'],str(calls));self.assertNotIn('hello',str(calls))

    def test_server_context_refuses_revocation_and_oversized_attachment_count(self):
        request=Mock(return_value=dict(id=self.account));context=dict(drive_references=[self.ref],intent='summarize')
        backend=self.backend(request)
        with patch('desktop_backend.connection',return_value=(self.config,'bound')),patch.object(drive.lumen_connect,'read_config',return_value=self.config),patch.object(drive.lumen_connect,'request',return_value=dict(id=self.account)),patch.object(drive.sync,'inventory',return_value=dict(files={},folders={})):
            with self.assertRaises(ValueError):DesktopBackend.send(backend,'Summarize',context_data=context)
        self.assertFalse(any(call.args[0]=='/bridge/tasks' for call in request.call_args_list))
        request.reset_mock();backend=self.backend(request)
        self.assertFalse(DesktopBackend.send(backend,'Discuss',context_data=dict(drive_references=[self.ref]*20)))
        request.assert_not_called();backend.failed.emit.assert_called_once()

    def test_parse_account_change_revocation_and_revision_return_no_text(self):
        self.row.update(name='Original.pdf',mime='application/pdf');self.ref['title']='Original.pdf'
        url=Registry().register(self.ref)
        def download(config,root,row,progress):
            Path(root['path'],'stage').write_bytes(b'hello');return 'stage'
        for change in ('account','revoked','version'):
            config=dict(self.config);cache=dict(files={self.family:dict(self.row)},folders={})
            def parse(path,job):
                if change=='account':config['token']='different-account'
                elif change=='revoked':cache['files']={}
                else:cache['files'][self.family]['revision']+=1
                return 'MUST NOT ESCAPE'
            with patch.object(drive.lumen_connect,'read_config',side_effect=lambda:dict(config)),patch.object(drive.lumen_connect,'request',return_value=dict(id=self.account)),patch.object(drive.sync,'inventory',side_effect=lambda _,*,job=None:dict(files={k:dict(v) for k,v in cache['files'].items()},folders={})),patch('drive_transport.download',side_effect=download),patch('tools_data.document_text',side_effect=parse):
                with self.assertRaises(ValueError):invoke('lumen_drive_read',dict(ref=url))
            self.assertFalse(list(Path(self.tmp.name+'/cache/lumen-drive-handoffs').glob('copy-*')))

    def test_server_source_limit_is_actionable_and_clears_pending_key(self):
        for sizes in ((35000,35000),(60000,)):
            refs=[];rows={}
            for size in sizes:
                family=str(uuid4());refs.append(dict(self.ref,id=family));rows[family]=dict(self.row,family=family,size=size)
            request=Mock(return_value=dict(id=self.account));backend=self.backend(request)
            backend.generation=1;backend.timer=Mock()
            def run(operation,fn):DesktopBackend._apply_response(backend,(1,operation,fn(request),False))
            backend._run=run
            def limited(config,path,body=None):
                if path=='/bridge/me':return dict(id=self.account)
                return dict(body,supported=False,reason='Die Datei überschreitet die zentrale Lesegrenze.')
            with patch('desktop_backend.connection',return_value=(self.config,'bound')),patch.object(drive.lumen_connect,'read_config',return_value=self.config),patch.object(drive.lumen_connect,'request',side_effect=limited),patch.object(drive.sync,'inventory',return_value=dict(files=rows,folders={})):
                self.assertTrue(DesktopBackend.send(backend,'Summarize',context_data=dict(drive_references=refs,intent='summarize')))
            self.assertEqual([call.args[0] for call in request.call_args_list],['/bridge/me'])
            self.assertEqual(backend.remote_key,'');self.assertFalse(backend.remote_active)
            backend.failed.emit.assert_called_once();self.assertIn('zentrale Lesegrenze',backend.failed.emit.call_args.args[0])
            backend.remember.assert_any_call(unittest.mock.ANY,remove=True)

    def test_actual_native_worker_deadline_kills_parser_and_removes_copy(self):
        import sys,time
        from test_mcp import mcp
        import lumen_mcp_tools
        self.row.update(name='Original.pdf',mime='application/pdf');self.ref['title']='Original.pdf'
        url=Registry().register(self.ref);pidfile=Path(self.tmp.name)/'parser.pid'
        child="import os,signal,time;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path("+repr(str(pidfile))+").write_text(str(os.getpid()));time.sleep(90)"
        worker=Path(self.tmp.name)/'worker.py';actual=lumen_mcp_tools.__file__
        worker.write_text("import sys,runpy\nfrom pathlib import Path\nsys.path[:0]="+repr([str(Path(actual).parent)])+"\nimport drive_references as d,drive_transport,tools_data\nd.READ_TIMEOUT=.4\nconfig="+repr(self.config)+"\nref="+repr(self.ref)+"\nrow="+repr(self.row)+"\nd.lumen_connect.read_config=lambda:config\nd.lumen_connect.request=lambda *_:dict(id=ref['locator']['account'])\nd.sync.inventory=lambda _:dict(files={ref['id']:row},folders={})\ndef download(c,root,row,progress):\n Path(root['path'],'stage').write_bytes(b'hello');return 'stage'\ndrive_transport.download=download\ntools_data.document_text=lambda path,job:job.command([sys.executable,'-c',"+repr(child)+"],timeout=90).decode()\nrunpy.run_path("+repr(actual)+",run_name='__main__')\n")
        started=time.monotonic()
        with patch.object(lumen_mcp_tools,'__file__',str(worker)):
            with self.assertRaisesRegex(ValueError,'Drive'):mcp.tool_native('lumen_drive_read',dict(ref=url))
        self.assertLess(time.monotonic()-started,8);self.assertTrue(pidfile.exists())
        with self.assertRaises(ProcessLookupError):os.kill(int(pidfile.read_text()),0)
        self.assertFalse(list(Path(self.tmp.name+'/cache/lumen-drive-handoffs').glob('copy-*')))
        # The same deadline must also interrupt a blocked download before materialization yields.
        worker.write_text(worker.read_text().replace("Path(root['path'],'stage').write_bytes(b'hello');return 'stage'","Path(root['path'],'stage').write_bytes(b'he');__import__('time').sleep(90);return 'stage'"))
        started=time.monotonic()
        with patch.object(lumen_mcp_tools,'__file__',str(worker)):
            with self.assertRaisesRegex(ValueError,'Drive'):mcp.tool_native('lumen_drive_read',dict(ref=url))
        self.assertLess(time.monotonic()-started,5)
        self.assertFalse(list(Path(self.tmp.name+'/cache/lumen-drive-handoffs').glob('copy-*')))


if __name__=='__main__':unittest.main()
