"""Native MCP contracts with isolated data; no real mail, backups or desktop writes."""
import json
import os
from pathlib import Path
import subprocess
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
        (config/'opencode.jsonc').write_text(json.dumps(before))
        repo=Path(mcp.__file__).resolve().parent.parent
        result=subprocess.run([str(repo/'bin/lumen-setup')],env=dict(os.environ,OPENCODE_HOME=str(config)),capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        after=json.loads((config/'opencode.jsonc').read_text())
        self.assertEqual(after['mcp']['cachyos']['command'],[str(repo/'bin/lumen-mcp')])
        before['mcp']['cachyos']['command']=after['mcp']['cachyos']['command']
        before['$schema']='https://opencode.ai/config.json'
        self.assertEqual(after,before)

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
        result = invoke('lumen_notes_search',dict(query='Workshop'))
        self.assertEqual(len(result['items']),2)
        self.assertNotIn('PRIVATE_SECRET',json.dumps(result))
        read = invoke('lumen_notes_read',dict(path=visible['path']))
        self.assertEqual(read['links'],[related['path']])
        for path in (private['path'],'../outside.md'):
            with self.assertRaises(ValueError):invoke('lumen_notes_read',dict(path=path))
        memory.share(visible['path'],False)
        with self.assertRaises(ValueError):invoke('lumen_notes_read',dict(path=visible['path']))
        memory.remember('Project fact','Scoped to project',scope=str(self.root/'project'))
        self.assertNotIn('Scoped to project',invoke('lumen_memory_context',dict(query='Project',directory=str(self.root)))['context'])
        self.assertIn('Scoped to project',invoke('lumen_memory_context',dict(query='Project',directory=str(self.root/'project')))['context'])
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

    def test_inbox_requires_opt_in_rechecks_revocation_and_omits_raw_credentials(self):
        from inbox_data import store
        library = store()
        identity=library.create('Test account',kind='imap',password='SECRET_PASSWORD',url='https://secret.invalid')
        with library.connect() as db:
            for i in range(3):
                db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?)',(identity,'INBOX','7',str(i),'thread','Workshop '+str(i),'Sender','Today','Message body',b'RAW_SECRET',1))
            db.execute('INSERT INTO calendar_cache VALUES (?,?,?)',(identity,'event',json.dumps(dict(uid='u',title='Workshop',start='2026-12-01',description='Description',ics='SECRET_ICS'))))
        with self.assertRaisesRegex(ValueError,'disabled'):invoke('lumen_inbox_search',dict(query='Workshop'))
        settings=QSettings('Lumen','Assistant');settings.setValue('mcpInboxRead',True);settings.sync()
        result=invoke('lumen_inbox_search',dict(query='Workshop',limit=2))
        self.assertEqual(result['next_offset'],2);self.assertEqual(len(result['items']),2)
        row=result['items'][0]
        read=invoke('lumen_inbox_read',{k:row[k] for k in ('account','folder','validity','uid')})
        self.assertEqual(read['body'],'Message body')
        calendar=invoke('lumen_calendar_list',dict(query='Workshop'))
        self.assertEqual(calendar['items'][0]['title'],'Workshop')
        self.assertNotIn('SECRET',json.dumps([result,read,calendar]))
        settings.setValue('mcpInboxRead',False);settings.sync()
        with self.assertRaisesRegex(ValueError,'disabled'):invoke('lumen_calendar_list',{})

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
                          ('lumen_notes_search',dict(query='a',limit=1000)),
                          ('lumen_settings_get',dict(secret=True)),
                          ('lumen_inbox_search',[]),('lumen_settings_get',None)]:
            with self.subTest(name=name),patch.object(mcp,'tool_native') as worker:
                with self.assertRaises(ValueError):mcp.validate_schema(args,DEFINITIONS[name]['schema'])
                worker.assert_not_called()

    def test_timeout_kills_worker_process_group(self):
        process=unittest.mock.Mock(pid=123)
        process.communicate.side_effect=[subprocess.TimeoutExpired('worker',45),('','')]
        with patch.object(mcp.subprocess,'Popen',return_value=process),patch.object(mcp.os,'killpg') as kill:
            with self.assertRaisesRegex(ValueError,'timed out'):mcp.tool_native('lumen_settings_get',{})
        kill.assert_called_once();self.assertEqual(process.communicate.call_count,2)

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
            dict(jsonrpc='2.0',id=7,method='tools/call',params={'name':'lumen_notes_read','arguments':{'path':note['path']}}),
            dict(jsonrpc='2.0',id=8,method='tools/call',params={'name':'lumen_task_get','arguments':{'id':task}})])
        payload='[]\ninvalid json\n' +'\n'.join(json.dumps(r) for r in requests)+'\n'
        env=dict(os.environ,LUMEN_MCP_ACTIONS='0')
        completed=subprocess.run([sys.executable,str(Path(mcp.__file__))],input=payload,text=True,capture_output=True,env=env,timeout=30)
        self.assertEqual(completed.returncode,0,completed.stderr)
        replies=[json.loads(line) for line in completed.stdout.splitlines()]
        keyed={r.get('id'):r for r in replies}
        self.assertEqual(keyed[1]['result']['protocolVersion'],'2025-06-18')
        tools={t['name']:t for t in keyed[2]['result']['tools']}
        self.assertIn('lumen_notes_read',tools);self.assertNotIn('lumen_theme_set',tools)
        self.assertTrue(tools['lumen_notes_read']['annotations']['readOnlyHint'])
        self.assertIn('preferences',keyed[3]['result']['structuredContent'])
        self.assertIn('error',keyed[4]);self.assertIn('error',keyed[5]);self.assertEqual(keyed[6]['result'],{})
        self.assertEqual(keyed[7]['result']['structuredContent']['title'],'Shared fixture')
        self.assertEqual(keyed[8]['result']['structuredContent']['title'],'Fixture task')
        env['LUMEN_MCP_ACTIONS']='1'
        completed=subprocess.run([sys.executable,str(Path(mcp.__file__))],input=json.dumps(requests[2])+'\n',text=True,capture_output=True,env=env,timeout=10)
        names=[t['name'] for t in json.loads(completed.stdout)['result']['tools']]
        self.assertIn('lumen_theme_set',names);self.assertIn('lumen_memory_remember',names)


if __name__=='__main__':unittest.main()
