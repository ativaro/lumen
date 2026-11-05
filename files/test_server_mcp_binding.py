"""Paired server tools belong only to the effective private engine profile."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from PySide6.QtCore import QSettings, QProcess
from PySide6.QtWidgets import QApplication
from assistant_backend import OpenCodeBackend


class ServerMCPBindingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.environment = dict(HOME=str(self.root), XDG_CONFIG_HOME=str(self.root/'config'),
            XDG_DATA_HOME=str(self.root/'data'), XDG_CACHE_HOME=str(self.root/'cache'),
            XDG_STATE_HOME=str(self.root/'state'), XDG_RUNTIME_DIR=str(self.root/'run'),
            LUMEN_DATA=str(self.root/'lumen'), OPENCODE_CONFIG_CONTENT='{}')
        self.enterContext(patch.dict(os.environ, self.environment))
        self.config = self.root/'config/lumen-server/connection.json'
        self.write_pairing()
        self.binary = self.root/'engine'
        self.binary.write_text('#!'+sys.executable+'\nimport time\n'
            'print("opencode server listening on http://127.0.0.1:54321", flush=True)\ntime.sleep(60)\n')
        self.binary.chmod(0o700)
        self.enterContext(patch('assistant_backend.opencode_binary', return_value=str(self.binary)))

    def write_pairing(self, **changes):
        value = dict(server='https://staging.invalid', token='synthetic-device-token',
            device_id='a5c704e4-c826-479b-bcde-41b2c8dc8efb')
        value.update(changes)
        self.config.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.config.write_text(json.dumps(value)); self.config.chmod(0o600)
        return value

    def wait(self, condition):
        until = time.monotonic()+5
        while not condition() and time.monotonic() < until:
            self.app.processEvents(); time.sleep(.005)
        self.assertTrue(condition())

    def backend(self, **kwargs):
        backend = OpenCodeBackend(str(self.root), **kwargs)
        backend.settings = QSettings(str(self.root/'assistant.ini'), QSettings.IniFormat)
        self.addCleanup(backend.shutdown)
        return backend

    def start(self, backend):
        ready=[]
        backend.ensure_server(lambda: ready.append(True))
        self.wait(lambda: bool(ready))
        return json.loads(backend.proc.processEnvironment().value('OPENCODE_CONFIG_CONTENT'))

    def test_private_engine_merges_current_pairing_without_touching_disk_config(self):
        original = dict(model='provider/model', small_model='provider/small', provider={'provider':{'name':'Test'}},
            permission={'edit':'ask'}, mcp={'other':{'type':'local','command':['true']},
                'lumen-server':{'type':'remote','url':'https://stale.invalid/mcp/',
                                'headers':{'Authorization':'Bearer stale'},'enabled':False}})
        os.environ['OPENCODE_CONFIG_CONTENT']=json.dumps(original)
        before=self.config.read_bytes(); files=set(self.root.rglob('*'))
        backend=self.backend(); result=self.start(backend)
        expected=dict(type='remote',url='https://staging.invalid/mcp/',
            headers={'Authorization':'Bearer synthetic-device-token'},enabled=True,oauth=False)
        self.assertEqual(result['mcp']['lumen-server'],expected)
        self.assertEqual({k:v for k,v in result.items() if k not in ('mcp','skills','plugin')},
                         {k:v for k,v in original.items() if k not in ('mcp','skills')})
        self.assertEqual(result['mcp']['other'],original['mcp']['other'])
        self.assertEqual(result['skills'], {'urls':['https://staging.invalid/api/skills/']})
        self.assertEqual(self.config.read_bytes(),before)
        self.assertEqual(os.environ['OPENCODE_CONFIG_CONTENT'],json.dumps(original))
        self.assertFalse(any(p.name in ('opencode.json','opencode.jsonc','opencode-mcp.json')
                             for p in set(self.root.rglob('*'))-files))

    def test_compaction_plugin_is_bundled_once_and_preserves_user_plugins(self):
        asset = Path(__file__).with_name('engine-plugins')/'lumen-continuity.mjs'
        uri = asset.resolve().as_uri()
        self.assertTrue(asset.is_file())
        for own in ([], [uri], [[uri, {'own': 'options'}]]):
            original = {'plugin': ['@example/owned@1.0.0', *own], 'model': 'chosen/model'}
            os.environ['OPENCODE_CONFIG_CONTENT'] = json.dumps(original)
            backend = self.backend()
            result = self.start(backend)
            self.assertEqual(result['model'], 'chosen/model')
            self.assertEqual(result['plugin'][0], '@example/owned@1.0.0')
            self.assertEqual(sum(row == uri or isinstance(row, list) and row[0] == uri for row in result['plugin']), 1)
            self.assertEqual(os.environ['OPENCODE_CONFIG_CONTENT'], json.dumps(original))
            backend.shutdown()

    def test_shared_skills_merge_without_overriding_user_paths_or_learning(self):
        from server_mcp_binding import configuration
        original = {'skills': {'paths': ['/own/skills'], 'urls': ['https://own.invalid/skills/']}}
        value, _ = configuration(dict(self.environment, OPENCODE_CONFIG_CONTENT=json.dumps(original)))
        self.assertEqual(json.loads(value)['skills'], dict(paths=['/own/skills'],
            urls=['https://own.invalid/skills/', 'https://staging.invalid/api/skills/']))
        self.config.unlink()
        value, _ = configuration(dict(self.environment, OPENCODE_CONFIG_CONTENT=json.dumps(original)))
        self.assertEqual(json.loads(value)['skills'], original['skills'])

    def test_missing_pairing_masks_stale_inherited_server_without_altering_other_tools(self):
        self.config.unlink()
        os.environ['OPENCODE_CONFIG_CONTENT']=json.dumps(dict(model='p/m',mcp={
            'other':{'enabled':False},'lumen-server':{'type':'remote','url':'https://old.invalid/mcp/'}}))
        result=self.start(self.backend())
        self.assertEqual(result['mcp']['lumen-server'],{'enabled':False})
        self.assertEqual(result['mcp']['other'],{'enabled':False})
        self.assertEqual(result['model'],'p/m')

    def test_learning_environment_uses_its_effective_profile_without_personal_fallback(self):
        profile=self.root/'learning'
        backend=self.backend();backend.learning_environment=dict(HOME=str(profile),
            XDG_CONFIG_HOME=str(profile/'config'),OPENCODE_CONFIG_CONTENT=json.dumps(dict(
                model='learning/model',mcp={'lumen_learning':{'type':'local','command':['true']}})))
        result=self.start(backend)
        self.assertEqual(result['mcp']['lumen-server'],{'enabled':False})
        self.assertEqual(result['mcp']['lumen_learning'],{'type':'local','command':['true']})
        self.assertEqual(result['model'],'learning/model')
        self.assertEqual(backend.proc.processEnvironment().value('HOME'),str(profile))

    def test_home_fallback_uses_effective_home_even_with_empty_xdg_config(self):
        from server_mcp_binding import configuration
        home=self.root/'alternate'; path=home/'.config/lumen-server/connection.json'
        path.parent.mkdir(parents=True);path.write_bytes(self.config.read_bytes());path.chmod(0o600)
        result,_=configuration(dict(self.environment,HOME=str(home),XDG_CONFIG_HOME=''))
        self.assertEqual(json.loads(result)['mcp']['lumen-server']['url'],'https://staging.invalid/mcp/')
        path.unlink()
        result,_=configuration(dict(self.environment,HOME=str(home),XDG_CONFIG_HOME=''))
        self.assertEqual(json.loads(result)['mcp']['lumen-server'],{'enabled':False})

    def test_model_configuration_does_not_change_the_account_history_binding(self):
        from server_mcp_binding import configuration
        _,first=configuration(self.environment)
        _,second=configuration(dict(self.environment,OPENCODE_CONFIG_CONTENT=json.dumps(dict(model='another/model'))))
        self.assertEqual(first,second)
        self.write_pairing(token='replacement-token')
        _,third=configuration(self.environment)
        self.assertNotEqual(second,third)

    def test_invalid_configuration_never_starts_an_engine_or_exposes_secrets(self):
        cases=[dict(server='http://host.invalid'),dict(server='https://user@host.invalid'),
            dict(server='https://host.invalid/path'),dict(server='https://host.invalid:0'),
            dict(server='https://host.invalid\\@other.invalid'),dict(token='secret\r\nHeader: no'),
            dict(token='{env:SECRET}'),dict(token=''),dict(device_id='invalid')]
        for changes in cases:
            with self.subTest(changes=changes):
                self.write_pairing(**changes);backend=self.backend(); errors=[]; ready=[]
                backend.failed.connect(errors.append)
                backend.ensure_server(lambda:ready.append(True))
                self.assertIsNone(backend.proc);self.assertFalse(ready);self.assertTrue(errors)
                self.assertNotIn(str(changes),str(errors))
        self.write_pairing()
        for raw in ('null','[]','{"mcp": []}','{"mcp": null}','{bad'):
            with self.subTest(runtime=raw):
                os.environ['OPENCODE_CONFIG_CONTENT']=raw;backend=self.backend();errors=[]
                backend.failed.connect(errors.append);backend.ensure_server(lambda:None)
                self.assertIsNone(backend.proc);self.assertTrue(errors)

    def test_unreadable_oversize_symlink_or_public_pairing_fails_closed(self):
        from server_mcp_binding import BindingError, configuration
        for kind in ('malformed','oversize','public','symlink','fifo'):
            with self.subTest(kind=kind):
                self.write_pairing()
                if kind=='malformed':self.config.write_text('null')
                elif kind=='oversize':self.config.write_text(' '*65537)
                elif kind=='public':self.config.chmod(0o644)
                elif kind=='symlink':
                    self.config.rename(self.config.with_suffix('.target'))
                    self.config.symlink_to(self.config.with_suffix('.target'))
                else:
                    self.config.unlink();os.mkfifo(self.config,0o600)
                with self.assertRaises(BindingError):configuration(self.environment)
                self.config.unlink()

    def test_binding_change_fences_ensure_request_send_and_running_poll_then_resets_conversation(self):
        for operation in ('ensure','request','poll','send'):
            with self.subTest(operation=operation):
                self.write_pairing(); backend=self.backend();self.start(backend)
                backend.session='old-session';backend.messages=[{'info':{'role':'user'},'parts':[]}]
                backend.set_busy(True); failures=[];backend.failed.connect(failures.append)
                proc=backend.proc
                self.write_pairing(server='https://replacement.invalid',token='replacement-token',
                    device_id='b5c704e4-c826-479b-bcde-41b2c8dc8efb')
                with patch.object(backend.network,'sendCustomRequest') as network:
                    if operation=='ensure':backend.ensure_server(lambda: self.fail('Old callback used'))
                    elif operation=='request':backend.request('GET','/permission')
                    elif operation=='poll':backend.poll()
                    else:self.assertIs(backend.send('Do not attach this to the previous account'),False)
                    network.assert_not_called()
                self.assertIsNone(backend.proc);self.assertEqual(backend.session,'')
                self.assertEqual(backend.messages,[]);self.assertFalse(backend.busy)
                self.assertTrue(failures);self.assertEqual(proc.state(),QProcess.ProcessState.NotRunning)
                result=self.start(backend)
                self.assertEqual(result['mcp']['lumen-server']['url'],'https://replacement.invalid/mcp/')
                self.assertEqual(result['mcp']['lumen-server']['headers']['Authorization'],'Bearer replacement-token')
                backend.shutdown()

    def test_watcher_stops_waiting_engine_after_disconnect_without_a_new_request(self):
        backend=self.backend();self.start(backend)
        backend.session='old-session';backend.set_busy(True);backend.polling=True
        self.config.unlink()
        self.wait(lambda:backend.proc is None)
        self.assertEqual(backend.session,'');self.assertFalse(backend.busy)
        self.assertFalse(backend.binding_timer.isActive())

    def test_after_binding_reset_a_new_send_creates_a_new_session_without_old_context(self):
        state={'prompt':None,'paths':[],'row':None}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_GET(self):self.respond()
            def do_POST(self):self.respond()
            def respond(self):
                path=self.path.split('?')[0];state['paths'].append(path)
                body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or 'null')
                value={}
                if path=='/config':value={'model':'synthetic/model'}
                elif path=='/session':
                    if self.command=='POST':
                        state['row']=dict(body,id='new-session',directory=str(self_root))
                        value=state['row']
                    else:value=[]
                elif path=='/session/new-session':value=state['row']
                elif path.endswith('/prompt_async'):state['prompt']=body
                elif path in ('/permission','/question'):value=[]
                elif path.endswith('/message'):
                    value=[{'info':{'role':'assistant','parentID':state['prompt']['messageID'],
                        'time':{'completed':1}},'parts':[{'type':'text','text':'Synthetic completion'}]}]
                raw=json.dumps(value).encode();self.send_response(200)
                self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
                self.end_headers();self.wfile.write(raw)
        self_root=self.root
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        backend=self.backend();self.start(backend)
        backend.session='old-account-session';backend.messages=[dict(info={'role':'user'},parts=[{'text':'old private context'}])]
        self.write_pairing(token='new-account-token')
        self.assertIs(backend.send('First send notices the change'),False)
        self.assertEqual(backend.session,'');self.assertEqual(backend.messages,[])
        self.start(backend);backend.url='http://127.0.0.1:'+str(server.server_port)
        backend.send('New account question',proposal=True)
        self.wait(lambda:state['prompt'] is not None and not backend.busy)
        self.assertEqual(backend.session,'new-session')
        self.assertTrue(all('old-account-session' not in path for path in state['paths']))
        self.assertNotIn('old private context',json.dumps(state['prompt']))

    def test_history_and_live_selection_cannot_restore_a_different_binding(self):
        backend=self.backend();self.start(backend)
        rows=[dict(id='current',directory=str(self.root),metadata=dict(client='lumen',
                  lumen_server_binding=backend.server_mcp_binding)),
              dict(id='previous',directory=str(self.root),metadata=dict(client='lumen',lumen_server_binding='old')),
              dict(id='legacy',directory=str(self.root),metadata=dict(client='lumen'))]
        captured=[];backend.sessionsChanged.connect(captured.append)
        def request(method,path,body=None,callback=None,error=None):
            if path.startswith('/session?'):callback(rows)
            else:callback(next(row for row in rows if path.endswith('/'+row['id'])))
        with patch.object(backend,'request',side_effect=request):
            backend.refresh_sessions()
            self.assertEqual([r['id'] for r in captured[-1]],['current'])
            with patch.object(backend,'poll') as poll:
                backend.select_session('current')
                self.assertEqual(backend.session,'current');poll.assert_called_once()
            backend.select_session('previous')
            self.assertEqual(backend.session,'');self.assertEqual(captured[-1],[])
        # Nothing in the shared engine database was deleted or rewritten.
        self.assertEqual([row['id'] for row in rows],['current','previous','legacy'])

    def test_recovery_assigned_session_id_is_checked_before_messages_or_prompt(self):
        requests=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_GET(self):
                requests.append(self.path.split('?')[0])
                raw=json.dumps(dict(id='old-restored-session',directory=str(self_root),
                    metadata=dict(client='lumen',lumen_server_binding='previous-account'))).encode()
                self.send_response(200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def do_POST(self):requests.append(self.path);self.send_error(500)
        self_root=self.root
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        backend=self.backend();self.start(backend)
        backend.url='http://127.0.0.1:'+str(server.server_port)
        backend.session='old-restored-session';backend.set_busy(True)
        backend.request('POST','/session/old-restored-session/prompt_async',{'parts':[]})
        self.wait(lambda:backend.proc is None)
        self.assertEqual(requests,['/session/old-restored-session']);self.assertEqual(backend.session,'')

    def test_disconnect_or_broken_config_stops_old_engine_and_clears_context(self):
        for change in ('disconnect','broken','runtime','account'):
            with self.subTest(change=change):
                self.write_pairing();os.environ['OPENCODE_CONFIG_CONTENT']='{}'
                backend=self.backend();self.start(backend);backend.session='old-session';backend.set_busy(True)
                if change=='disconnect':self.config.unlink()
                elif change=='broken':self.config.write_text('{bad')
                elif change=='runtime':os.environ['OPENCODE_CONFIG_CONTENT']='null'
                else:self.write_pairing(account='replacement-account')
                with patch.object(backend.network,'sendCustomRequest') as network:backend.poll();network.assert_not_called()
                self.assertIsNone(backend.proc);self.assertEqual(backend.session,'');self.assertFalse(backend.busy)

    def test_reply_from_old_pairing_cannot_reach_a_callback(self):
        entered=threading.Event(); release=threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_GET(self):
                entered.set();release.wait(3)
                raw=b'{"private":"old response"}'
                self.send_response(200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown);self.addCleanup(release.set)
        backend=self.backend();self.start(backend)
        backend.url='http://127.0.0.1:'+str(server.server_port);backend.session='old-session'
        callbacks=[];backend.request('GET','/config',callback=callbacks.append)
        self.wait(entered.is_set);self.write_pairing(token='replacement-token');release.set()
        self.wait(lambda:backend.proc is None)
        self.assertEqual(callbacks,[]);self.assertEqual(backend.session,'')

    def test_explicit_external_engine_is_not_claimed_or_reconfigured(self):
        backend=self.backend(server_url='http://127.0.0.1:54321')
        self.config.write_text('broken pairing must not configure an external engine')
        ready=[];backend.ensure_server(lambda:ready.append(True))
        self.assertEqual(ready,[True]);self.assertIsNone(backend.proc)
        self.assertIsNone(getattr(backend,'server_mcp_binding',None))


if __name__=='__main__':unittest.main()
