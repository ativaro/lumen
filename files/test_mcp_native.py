"""Native MCP contracts with isolated data; no real mail, backups or desktop writes."""
import json
import os
from pathlib import Path
import subprocess
import socket
import threading
import sys
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings
from lumen_store import Store
from lumen_mcp_tools import invoke, DEFINITIONS
from test_mcp import mcp


class NativeMCPTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = str(self.root/'config')
        self.old_config = os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config'))
        self.env = patch.dict(os.environ, {'LUMEN_DATA':str(self.root/'state'),
            'LUMEN_TOOLS_DATA':str(self.root/'tools'), 'XDG_CONFIG_HOME':self.config})
        self.env.start(); self.addCleanup(self.env.stop)
        QSettings.setPath(QSettings.NativeFormat,QSettings.UserScope,self.config)
        self.addCleanup(QSettings.setPath,QSettings.NativeFormat,QSettings.UserScope,self.old_config)
        self.store = Store()
        cwd=patch('lumen_mcp_tools.os.getcwd',return_value=str(self.root));cwd.start();self.addCleanup(cwd.stop)

    def test_notification_options_share_ui_settings_and_validate_before_changes(self):
        settings = QSettings('Lumen', 'Assistant')
        settings.setValue('untouched', 'keep'); settings.sync()
        self.assertEqual(invoke('lumen_notification_settings', {}), dict(native_popups=True, quiet_games=True))
        with patch('lumen_notifications.configure_popups') as configure:
            result = invoke('lumen_notification_configure', dict(quiet_games=False))
            configure.assert_not_called()
            self.assertEqual(result, dict(native_popups=True, quiet_games=False))
            self.assertFalse(QSettings('Lumen', 'Assistant').value('notifications/quietGames', True, type=bool))
            for args in ({}, {'quiet_games':'false'}, {'native_popups':False, 'unknown':True}):
                with self.assertRaises(ValueError): invoke('lumen_notification_configure', args)
            configure.assert_not_called()
            self.assertEqual(settings.value('untouched'), 'keep')
        with patch('lumen_notifications.configure_popups', side_effect=ValueError('tray unavailable')) as configure:
            with self.assertRaises(ValueError):
                invoke('lumen_notification_configure', dict(native_popups=False, quiet_games=True))
            configure.assert_called_once_with(False)
        self.assertEqual(invoke('lumen_notification_settings', {}), dict(native_popups=True, quiet_games=False))

    def test_library_search_has_origin_and_does_not_traverse_symlink(self):
        from file_spaces import Catalog
        source = self.root/'documents'; source.mkdir()
        (source/'Workshop.pdf').write_text('public')
        private = self.root/'private'; private.mkdir(); (private/'Workshop-secret.pdf').write_text('secret')
        (source/'linked').symlink_to(private, target_is_directory=True)
        library = Catalog(self.store).save_library(None,'Workshop',[dict(label='NAS mirror',location=str(source))])
        listing = invoke('lumen_files_locations', {'limit':100})
        self.assertIn(library, listing['items'])
        result = invoke('lumen_files_search',dict(library=library['id'],source=0,query='Workshop'))
        self.assertEqual(result['source']['label'],'NAS mirror')
        self.assertEqual([i['name'] for i in result['items']],['Workshop.pdf'])
        with self.assertRaises(ValueError):invoke('lumen_files_search',dict(library=library['id'],source=9,query=''))
        with patch('lumen_mcp_tools.network_folder',side_effect=ValueError('offline')):
            network = Catalog(self.store).save_library(None,'NAS',[dict(label='NAS',location='smb://example.invalid/share')])
            with self.assertRaisesRegex(ValueError,'offline'):invoke('lumen_files_search',dict(library=network['id'],source=0,query='a'))

    def test_saved_network_places_are_discoverable_without_credentials(self):
        settings = QSettings('Lumen','Files')
        settings.setValue('network_servers',['smb://nas/share','smb://user:secret@nas/private'])
        settings.sync()
        network = next(r for r in invoke('lumen_files_locations',{})['items'] if r['id']=='network')
        self.assertEqual(len(network['sources']),1)
        self.assertEqual(network['sources'][0]['location'],'smb://nas/share')
        with patch('lumen_mcp_tools.network_folder',return_value=str(self.root)) as mount:
            result=invoke('lumen_files_search',dict(library='network',source=0,query='absent'))
            mount.assert_called_once_with('smb://nas/share')
            self.assertEqual(result['source']['location'],'smb://nas/share')

    def test_setup_preserves_existing_mcp_options(self):
        config = self.root/'opencode';config.mkdir()
        before={'provider':{'example':{'apiKey':'PRIVATE'}},'instructions':['private.md'],
                'mcp':{'cachyos':{'type':'local','command':['python3','/usr/bin/lumen_mcp.py'],
                                  'enabled':False,'environment':{'LUMEN_MCP_ACTIONS':'1'},'timeout':60000}}}
        custom = config/'skills/lumen-service-access/SKILL.md'
        custom.parent.mkdir(parents=True)
        custom.write_text('My own replacement skill')
        (config/'opencode.jsonc').write_text(json.dumps(before))
        repo=Path(mcp.__file__).resolve().parent.parent
        result=subprocess.run([str(repo/'bin/lumen-setup')],env=dict(os.environ,OPENCODE_HOME=str(config)),capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        after=json.loads((config/'opencode.jsonc').read_text())
        self.assertEqual(after['mcp']['cachyos']['command'],[str(repo/'bin/lumen-mcp')])
        before['mcp']['cachyos']['command']=after['mcp']['cachyos']['command']
        before['$schema']='https://opencode.ai/config.json'
        self.assertEqual(after,before)
        self.assertEqual(custom.read_text(), 'My own replacement skill')
        self.assertTrue((config/'skills/lumen-vault-http/SKILL.md').is_file())

    def test_setup_replaces_only_retired_stock_skill(self):
        repo=Path(mcp.__file__).resolve().parent.parent
        config=self.root/'stock'
        retired=config/'skills/lumen-service-access/SKILL.md'
        retired.parent.mkdir(parents=True)
        old=(repo/'files/fixtures/retired-service-skill.md').read_bytes()
        retired.write_bytes(old)
        result=subprocess.run([str(repo/'bin/lumen-setup')],env=dict(os.environ,OPENCODE_HOME=str(config)),
            capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(retired.exists())
        self.assertTrue((config/'skills/lumen-vault-http/SKILL.md').is_file())

    def test_shared_notes_links_revocation_and_memory_scope(self):
        from wissen_data import activate, Notebook
        from lumen_memory import Memory
        activate(self.store)
        book = Notebook(self.store)
        visible = book.create('Workshop','Shared material [[Private]] [[Related]]')
        related = book.create('Related','Workshop related')
        private = book.create('Private','Workshop PRIVATE_SECRET')
        memory = Memory(self.store)
        memory.configure(True,False)
        memory.share(visible['path'],True); memory.share(related['path'],True)
        before={n['path']:n['hash'] for n in book.scan()['notes']}
        for name in ('lumen_notes_search','lumen_notes_read','lumen_notes_propose_edit','lumen_notes_propose_connections'):
            self.assertNotIn(name,DEFINITIONS)
            with self.assertRaisesRegex(ValueError,'paired Server tools'):
                invoke(name,dict(path=visible['path'],query='Workshop'))
        self.assertEqual(before,{n['path']:n['hash'] for n in book.scan()['notes']})
        memory.share(visible['path'],False)
        memory.remember('Project fact','Scoped to project',scope=str(self.root/'project'))
        self.assertNotIn('Scoped to project',invoke('lumen_memory_context',dict(query='Project',directory=str(self.root)))['context'])
        with self.assertRaises(ValueError):invoke('lumen_memory_context',dict(query='Project',directory=str(self.root/'project')))
        with patch('lumen_mcp_tools.os.getcwd',return_value=str(self.root/'project')):
            self.assertIn('Scoped to project',invoke('lumen_memory_context',dict(query='Project'))['context'])
        memory.configure(False,False)
        self.assertEqual(invoke('lumen_memory_context',dict(query='Project',directory=str(self.root)))['context'],'')
        with self.assertRaises(ValueError):invoke('lumen_notes_search',dict(query='Workshop'))

    def test_tasks_are_paginated_visible_and_never_approved(self):
        ids = [self.store.create_task('Task '+str(i),directory=str(self.root),roots=[str(self.root)],steps=[dict(action='diagnose')]) for i in range(4)]
        self.store.update_task(ids[0],status='completed'); self.store.dismiss_task(ids[0])
        self.store.event(ids[1],'proposal','Visible draft')
        first = invoke('lumen_tasks_list',dict(limit=2))
        second = invoke('lumen_tasks_list',dict(limit=2,offset=first['next_offset']))
        self.assertEqual(len(first['items'])+len(second['items']),3)
        self.assertEqual(len({r['id'] for r in first['items']+second['items']}),3)
        result = invoke('lumen_task_get',dict(id=ids[1]))
        self.assertFalse(result['approved']);self.assertEqual(result['status'],'draft')
        self.assertEqual(result['events']['items'][0]['detail'],'Visible draft')

    def test_projects_retirement_never_reads_or_mutates_the_local_library(self):
        from tools_data import Library
        library=Library('workbench');key=library.create('Original project',notes='Original text')
        before=library.db.read_bytes()
        for name in ('lumen_projects_list','lumen_project_read','lumen_project_runs'):
            self.assertNotIn(name,DEFINITIONS)
            with self.assertRaisesRegex(ValueError,'paired Server tools'):
                invoke(name,dict(id=key,task=key,include_archived=True))
        self.assertEqual(library.db.read_bytes(),before)

    def test_real_stdio_discovery_excludes_retired_project_and_inbox_cache_tools(self):
        requests=[dict(jsonrpc='2.0',id=1,method='tools/list'),dict(jsonrpc='2.0',id=2,method='tools/call',params=dict(name='lumen_projects_list',arguments={})),dict(jsonrpc='2.0',id=3,method='tools/call',params=dict(name='lumen_inbox_search',arguments={'query':'private'}))]
        result=subprocess.run([sys.executable,str(Path(mcp.__file__))],input='\n'.join(json.dumps(r) for r in requests)+'\n',text=True,capture_output=True,env=dict(os.environ,LUMEN_MCP_ACTIONS='0'),timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        replies={r['id']:r for r in map(json.loads,result.stdout.splitlines())}
        names={t['name'] for t in replies[1]['result']['tools']}
        self.assertIn('lumen_files_search',names)
        self.assertTrue({'lumen_projects_list','lumen_project_read','lumen_project_runs','lumen_inbox_search','lumen_inbox_read','lumen_calendar_list'}.isdisjoint(names))
        self.assertTrue('error' in replies[2] or replies[2].get('result',{}).get('isError'))
        self.assertTrue('error' in replies[3] or replies[3].get('result',{}).get('isError'))

    def test_settings_conflict_history_and_privacy_keys(self):
        from lumen_history import entries
        settings = invoke('lumen_settings_get',{})
        self.assertFalse(settings['inbox_mcp'])
        args = dict(application='Files',key='searchDelay',value=400,expected=250)
        invoke('lumen_settings_set',args)
        self.assertEqual(QSettings('Lumen','Files').value('searchDelay',type=int),400)
        history = entries(self.store)
        self.assertEqual(history[0]['before'],{'searchDelay':250})
        with self.assertRaisesRegex(ValueError,'changed'):invoke('lumen_settings_set',dict(args,value=450))
        for key in ('autoApproveTools','mcpInboxRead','apiKey','appearance'):
            with self.assertRaises(ValueError):invoke('lumen_settings_set',dict(application='Assistant',key=key,value=True,expected=False))
        with self.assertRaises(ValueError):invoke('lumen_settings_set',dict(args,value=True,expected=400))

    def test_theme_and_shortcut_use_native_operations(self):
        with patch('desktop_settings.apply_appearance',return_value={'desktop':True}) as apply:
            result = invoke('lumen_theme_set',dict(design='midnight',expected='glass'))
            apply.assert_called_once_with({'design':'midnight'});self.assertTrue(result['saved'])
            self.assertEqual(QSettings('Lumen','Assistant').value('appearance'),'midnight')
            with self.assertRaises(ValueError):invoke('lumen_theme_set',dict(design='glass',expected='glass'))
            self.assertEqual(apply.call_count,1)
        with patch('desktop_settings.set_shortcut') as change:
            args=dict(component='lumen-ask.desktop',key=123,before=[456])
            invoke('lumen_shortcut_set',args);change.assert_called_once_with(args)
            with self.assertRaises(ValueError):invoke('lumen_shortcut_set',dict(args,component='other.desktop'))

    def test_retired_inbox_cache_cannot_override_server_rights_even_with_old_opt_in(self):
        from inbox_data import store
        library = store()
        identity=library.create('Test account',kind='imap',password='SECRET_PASSWORD',url='https://secret.invalid')
        with library.connect() as db:
            for i in range(3):
                db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?)',(identity,'INBOX','7',str(i),'thread','Workshop '+str(i),'Sender','Today','Message body',b'RAW_SECRET',1))
            db.execute('INSERT INTO calendar_cache VALUES (?,?,?)',(identity,'event',json.dumps(dict(uid='u',title='Workshop',start='2026-12-01',description='Description',ics='SECRET_ICS'))))
        settings=QSettings('Lumen','Assistant')
        for enabled in (False,True):
            settings.setValue('mcpInboxRead',enabled);settings.sync()
            with patch('inbox_data.store',side_effect=AssertionError('No access to retired message caches')):
                for name in ('lumen_inbox_search','lumen_inbox_read','lumen_calendar_list'):
                    with self.subTest(enabled=enabled,name=name),self.assertRaisesRegex(ValueError,'paired Server tools'):
                        invoke(name,{})
            self.assertFalse(invoke('lumen_settings_get',{})['inbox_mcp'])
        with library.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM messages').fetchone()[0],3)

    def test_vault_status_is_cached_and_does_not_unlock(self):
        from tools_data import Library
        Library('vault').create('Backup',repository='/unreachable',sources=['/source'],last_backup=123,password='SECRET',last_error='offline')
        with patch('tools_secrets.secret',side_effect=AssertionError('must not unlock')):
            result=invoke('lumen_vault_status',{})
        self.assertTrue(result['cached']);self.assertFalse(result['repository_checked'])
        self.assertEqual(result['items'][0]['last_backup'],123)
        self.assertNotIn('SECRET',json.dumps(result))

    def test_invalid_native_arguments_rejected_before_worker(self):
        for name,args in [('lumen_files_search',dict(library='x',source=True,query='a')),
                          ('lumen_memory_list',dict(query='a',limit=1000)),
                          ('lumen_settings_get',dict(secret=True)),
                          ('lumen_settings_get',[]),('lumen_settings_get',None)]:
            with self.subTest(name=name),patch.object(mcp,'tool_native') as worker:
                with self.assertRaises(ValueError):mcp.validate_schema(args,DEFINITIONS[name]['schema'])
                worker.assert_not_called()

    def test_http_plan_schema(self):
        schema = DEFINITIONS['lumen_vault_http_open']['schema']
        step = dict(method='POST', path='/session', body={'secret':{'$vault':'password'}})
        valid = dict(reference='vault:example', requests=[step, dict(method='GET',path='/status')])
        mcp.validate_schema(valid, schema)
        for plan in ([], [step]*13, ['bad'], [dict(step, session='override')], [dict(step, headers={})], [dict(path='/status')]):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                mcp.validate_schema(dict(reference='vault:example', requests=plan), schema)

    def test_timeout_kills_worker_process_group(self):
        process=unittest.mock.Mock(pid=123)
        process.communicate.side_effect=[subprocess.TimeoutExpired('worker',45),('','')]
        with patch.object(mcp.subprocess,'Popen',return_value=process),patch.object(mcp.os,'killpg') as kill:
            with self.assertRaisesRegex(ValueError,'timed out'):mcp.tool_native('lumen_settings_get',{})
        kill.assert_called_once();self.assertEqual(process.communicate.call_count,2)

    def test_api_write_schema_and_worker_failure_boundary(self):
        schema = DEFINITIONS['lumen_vault_api_request']['schema']
        for body in ({'text':'hello'}, [{'op':'replace'}], [0]*1001):
            mcp.validate_schema({'method':'POST','body':body}, schema)
        for body in ('text', 1, True, None):
            with self.assertRaises(ValueError): mcp.validate_schema({'method':'POST','body':body}, schema)
        for method in ('CONNECT','post','POST\r\nHeader: x'):
            with self.assertRaises(ValueError): mcp.validate_schema({'method':method}, schema)
        for name,args in [('lumen_vault_api_request',{'method':'POST'}),('lumen_vault_mcp',{'operation':'call','name':'x','arguments':{}}), ('lumen_vault_ssh_exec',{'reference':'vault:x','command':'uname -a'}), ('lumen_vault_http_request',{'session':'s','method':'GET','path':'/rpc'}), *[(f'lumen_vault_web_{op}', {'session':'opaque','snapshot':'snap','node':'1'}) for op in ('login','click','fill')]]:
            process=unittest.mock.Mock(pid=123)
            process.communicate.side_effect=[subprocess.TimeoutExpired('worker',105),('','')]
            with patch.object(mcp.subprocess,'Popen',return_value=process),patch.object(mcp.os,'killpg'):
                with self.assertRaisesRegex(ValueError,'outcome is unknown'):mcp.tool_native(name,args)
            for code,output in [(1,''),(0,'invalid'),(0,'[]'),(0,'{}'),(0,'x'*(2*1024*1024+1))]:
                process=unittest.mock.Mock(pid=123,returncode=code)
                process.communicate.return_value=(output,'')
                with patch.object(mcp.subprocess,'Popen',return_value=process):
                    with self.assertRaisesRegex(ValueError,'outcome is unknown'):mcp.tool_native(name,args)

    def test_api_near_limit_reply_through_real_worker_and_adapter(self):
        for char in ('a','ä'):
            with tempfile.TemporaryDirectory(prefix='lumen-mcp-',dir='/tmp') as directory, patch.dict(os.environ, XDG_RUNTIME_DIR=directory):
                endpoint=Path(directory)/'lumen-vault-access'
                service=socket.socket(socket.AF_UNIX);service.bind(str(endpoint));endpoint.chmod(0o600);service.listen(1)
                service.settimeout(10)
                body={'text':char*((1024*1024-12)//len(char.encode()))}
                reply={'untrusted_content':True,'http_status':201,'result':body}
                data=json.dumps(reply,ensure_ascii=False,separators=(',',':')).encode()+b'\n'
                self.assertGreater(len(data),1024*1024)
                received=[]
                def serve():
                    with service:
                        for payload in (b'{"unlocked":true}\n', data):
                            client,_=service.accept()
                            with client:
                                received.append(json.loads(client.recv(65536)))
                                client.sendall(payload)
                thread=threading.Thread(target=serve);thread.start()
                try:
                    result=mcp.tool_native('lumen_vault_api_request',{'method':'POST','path':'/pages','body':{'name':'Synthetic'}})
                    self.assertEqual(result,reply)
                    self.assertEqual(received,[{'operation':'unlock'},{'operation':'api_request','method':'POST','path':'/pages','body':{'name':'Synthetic'}}])
                finally:thread.join(timeout=12)

    def test_memory_discovery_has_no_keyword_gate_and_rechecks_scope_and_consent(self):
        from lumen_memory import Memory
        memory=Memory(self.store);memory.configure(True,True)
        global_note=memory.remember('照片','图片在网络磁盘上。',kind='fact')
        project_note=memory.remember('Projeto','Informação deste projeto.',scope='/project-a')
        listing=invoke('lumen_memory_list',dict(directory=str(self.root),limit=1))
        self.assertEqual([n['path'] for n in listing['items']],[global_note['path']])
        self.assertEqual(listing['total'],1)
        self.assertIn('图片',invoke('lumen_memory_read',dict(directory=str(self.root),path=global_note['path']))['text'])
        with self.assertRaises(ValueError):invoke('lumen_memory_read',dict(directory=str(self.root),path=project_note['path']))
        memory.forget(global_note['path'],global_note['hash'])
        with self.assertRaises(ValueError):invoke('lumen_memory_read',dict(directory=str(self.root),path=global_note['path']))
        memory.configure(False,False)
        self.assertEqual(invoke('lumen_memory_list',dict())['items'],[])

    def test_memory_proposals_correct_and_forget_only_after_native_review(self):
        from lumen_memory import Memory
        memory=Memory(self.store);memory.configure(True,False)
        request=dict(title='Preference',text='Brief answers',kind='preference')
        proposed=invoke('lumen_memory_propose',request)
        self.assertEqual(proposed['state'],'pending');self.assertEqual(memory.scan()['notes'],[])
        memory.review(proposed['id'],True);note=memory.scan()['notes'][0]
        corrected=invoke('lumen_memory_propose',dict(request,path=note['path'],revision=note['hash'],text='Detailed answers'))
        self.assertIn('Brief',memory.book.read(note['path'])['text'])
        memory.review(corrected['id'],True);current=memory.scan()['notes'][0]
        self.assertEqual(current['id'],note['id']);self.assertIn('Detailed',current['text'])
        with self.assertRaises(ValueError):invoke('lumen_memory_forget',dict(path=note['path'],revision=note['hash']))
        deletion=invoke('lumen_memory_forget',dict(path=current['path'],revision=current['hash']))
        self.assertEqual(len(memory.scan()['notes']),1)
        memory.review(deletion['id'],True);self.assertEqual(memory.scan()['notes'],[])
        self.assertEqual(memory.proposals(),[])

    def test_explicit_memory_uses_native_store_and_disabled_worker_refuses_writes(self):
        from lumen_memory import Memory
        memory=Memory(self.store);memory.configure(True,False)
        result=invoke('lumen_memory_remember',dict(title='Response style',text='Prefers brief answers.',kind='preference'))
        self.assertEqual(result['source'],'Explicit request via Lumen MCP')
        self.assertFalse(result['memory']['automatic'])
        request=dict(name='lumen_memory_remember',arguments=dict(title='Forbidden',text='Not saved',kind='fact'))
        worker=Path(mcp.__file__).resolve().parent.parent/'files/lumen_mcp_tools.py'
        process=subprocess.run([sys.executable,str(worker)],input=json.dumps(request),text=True,capture_output=True,env=dict(os.environ,LUMEN_MCP_ACTIONS='0'),timeout=10)
        self.assertIn('disabled',json.loads(process.stdout)['error'])
        self.assertEqual(len(memory.scan()['notes']),1)

    def test_stdio_roundtrip_errors_and_action_gate(self):
        requests=[dict(jsonrpc='2.0',id=1,method='initialize',params={'protocolVersion':'2025-06-18'}),
                  dict(jsonrpc='2.0',method='notifications/initialized'),
                  dict(jsonrpc='2.0',id=2,method='tools/list'),
                  dict(jsonrpc='2.0',id=3,method='tools/call',params={'name':'lumen_settings_get','arguments':{}}),
                  dict(jsonrpc='2.0',id=4,method='tools/call',params={'name':'lumen_theme_set','arguments':{}}),
                  dict(jsonrpc='2.0',id=5,method='tools/call',params={'name':[]}),
                  dict(jsonrpc='2.0',id=6,method='ping')]
        from wissen_data import activate, Notebook
        from lumen_memory import Memory
        activate(self.store);note=Notebook(self.store).create('Shared fixture','Workshop text')
        memory=Memory(self.store);memory.configure(True,False);memory.share(note['path'],True)
        task=self.store.create_task('Fixture task',directory=str(self.root))
        requests.extend([
            dict(jsonrpc='2.0',id=9,method='tools/call',params={'name':'lumen_present_files','arguments':{'paths':[str(self.root/'result.txt')], 'title':'Result'}}),
            dict(jsonrpc='2.0',id=7,method='tools/call',params={'name':'lumen_notes_read','arguments':{'path':note['path']}}),
            dict(jsonrpc='2.0',id=8,method='tools/call',params={'name':'lumen_task_get','arguments':{'id':task}})])
        payload='[]\ninvalid json\n' +'\n'.join(json.dumps(r) for r in requests)+'\n'
        (self.root/'result.txt').write_text('Synthetic preview result')
        env=dict(os.environ,LUMEN_MCP_ACTIONS='0')
        completed=subprocess.run([sys.executable,str(Path(mcp.__file__))],input=payload,text=True,capture_output=True,env=env,timeout=30)
        self.assertEqual(completed.returncode,0,completed.stderr)
        replies=[json.loads(line) for line in completed.stdout.splitlines()]
        keyed={r.get('id'):r for r in replies}
        self.assertEqual(keyed[1]['result']['protocolVersion'],'2025-06-18')
        tools={t['name']:t for t in keyed[2]['result']['tools']}
        self.assertFalse(any(name.startswith('lumen_notes_') for name in tools));self.assertNotIn('lumen_theme_set',tools)
        self.assertIn('lumen_notification_settings',tools);self.assertNotIn('lumen_notification_configure',tools)
        self.assertIn('lumen_vault_store',tools)
        self.assertIn('lumen_vault_store_from_chat',tools)
        self.assertIn('lumen_vault_mcp',tools)
        self.assertIn('lumen_vault_api_get',tools)
        self.assertIn('lumen_vault_api_request',tools)
        self.assertFalse(tools['lumen_vault_api_request']['annotations']['readOnlyHint'])
        self.assertTrue(tools['lumen_vault_api_request']['annotations']['destructiveHint'])
        self.assertIn('lumen_vault_connection',tools)
        self.assertFalse(tools['lumen_vault_store']['annotations']['readOnlyHint'])
        self.assertNotIn('password',tools['lumen_vault_store']['inputSchema']['properties'])
        self.assertTrue(tools['lumen_present_files']['annotations']['readOnlyHint'])
        self.assertEqual(keyed[9]['result']['structuredContent']['paths'], [str(self.root/'result.txt')])
        self.assertEqual(json.loads(keyed[9]['result']['content'][0]['text']), keyed[9]['result']['structuredContent'])
        self.assertIn('preferences',keyed[3]['result']['structuredContent'])
        self.assertIn('error',keyed[4]);self.assertIn('error',keyed[5]);self.assertEqual(keyed[6]['result'],{})
        self.assertIn('error',keyed[7])
        self.assertEqual(Notebook(self.store).read(note['path'])['hash'],note['hash'])
        self.assertEqual(keyed[8]['result']['structuredContent']['title'],'Fixture task')
        env['LUMEN_MCP_ACTIONS']='1'
        completed=subprocess.run([sys.executable,str(Path(mcp.__file__))],input=json.dumps(requests[2])+'\n',text=True,capture_output=True,env=env,timeout=10)
        names=[t['name'] for t in json.loads(completed.stdout)['result']['tools']]
        self.assertIn('lumen_theme_set',names);self.assertIn('lumen_memory_remember',names)
        self.assertIn('lumen_notification_configure',names)


if __name__=='__main__':unittest.main()
