import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from email.message import Message
from unittest.mock import patch

import server_app_session as host


USER = '72000000-0000-4000-8000-000000000001'
DEVICE = '72000000-0000-4000-8000-000000000002'
ORIGIN = 'https://lumen.test'
NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


class Response(io.BytesIO):
    def __init__(self, data, cookie=None):
        super().__init__(json.dumps(data).encode())
        self.headers = Message()
        if cookie is not None:
            self.headers.add_header('Set-Cookie', cookie)


class SessionTest(unittest.TestCase):
    def test_only_code_can_embed_known_sandbox_preview_routes(self):
        code=host.Binding(ORIGIN,USER,DEVICE,'code')
        path=ORIGIN+'/api/code-library/'+USER
        for value in (path+'/code-document?entry_revision=1&repo_revision=1&sha256='+('a'*64)+'&channel='+('b'*32),
                      path+'/document?revision=1&channel='+('b'*32)+'&draft=true', 'about:srcdoc'):
            with self.subTest(value=value):
                self.assertTrue(code.preview_navigation(value))
                for app in host.APPS:
                    if app!='code':self.assertFalse(host.Binding(ORIGIN,USER,DEVICE,app).preview_navigation(value))
        for value in (path+'/code-document?token=x',path+'/document?channel=a&channel=b',
                      path+'/document#secret',path.replace(ORIGIN,'https://foreign.test')+'/document',
                      path+'/app-note',path+'/document/extra',path.replace(USER,'../secret')+'/document',
                      ORIGIN+'/?app=code&presentation=desktop','about:blank','about:srcdoc?token=x',
                      'data:text/html,unsafe','file:///etc/passwd',None):
            with self.subTest(value=value):self.assertFalse(code.preview_navigation(value))

    def setUp(self):
        self.binding = host.Binding(ORIGIN, USER, DEVICE, 'compose')
        self.config = dict(server=ORIGIN, device_id=DEVICE, token='native-only-fixture')
        self.native_calls, self.web_calls = [], []
        self.clock = 10
        self.exchange = dict(user_id=USER, device_id=DEVICE, app='compose', access='read',
                             csrf='csrf-fixture', expires=(NOW + timedelta(seconds=900)).isoformat())
        self.me = dict(user=dict(id=USER, device_id=DEVICE, desktop_app='compose',
                                device_kind='desktop', admin=False, capabilities=['translate'],
                                csrf='csrf-fixture'))
        self.cookie = 'lumen_session=' + 'c' * 43 + '; Path=/; Max-Age=900; Secure; HttpOnly; SameSite=Strict'
        self.native = patch.object(host.lumen_connect, 'request', self.native_request).start()
        patch.object(host.lumen_connect, 'tls_context', return_value=None).start()
        self.opener = patch.object(host.urllib.request, 'build_opener').start().return_value
        self.opener.open.side_effect = self.web_request
        self.addCleanup(patch.stopall)

    def native_request(self, config, path, body=None, **kwargs):
        self.native_calls.append((dict(config), path, body))
        if path == '/bridge/me':
            return dict(id=USER, device_id=DEVICE, capabilities=['translate'])
        if path == '/bridge/apps/session-renew':
            return {k:self.exchange[k] for k in ('user_id','device_id','app','expires')}
        return dict(ticket='t' * 43, expires=(NOW + timedelta(seconds=30)).isoformat())

    def web_request(self, request, **kwargs):
        self.web_calls.append(request)
        if request.full_url.endswith('/exchange'):
            return Response(self.exchange, self.cookie)
        return Response(self.me)

    def session(self):
        return host.AppSession(self.config, self.binding, now=lambda: NOW, clock=lambda: self.clock)

    def test_exchange_and_me_use_separate_credentials(self):
        session = self.session(); session.connect()
        self.assertTrue(session.usable)
        self.assertEqual(session.url, ORIGIN + '/?app=translate&presentation=desktop')
        ticket = self.native_calls[1]
        self.assertEqual(ticket[1], '/bridge/apps/session-ticket')
        self.assertEqual(ticket[2]['app'], 'compose')
        self.assertRegex(ticket[2]['challenge'], '^[a-f0-9]{64}$')
        payload = json.loads(self.web_calls[0].data)
        self.assertEqual(payload['user_id'], USER)
        self.assertEqual(payload['device_id'], DEVICE)
        self.assertEqual(payload['app'], 'compose')
        for request in self.web_calls:
            self.assertIsNone(request.get_header('Authorization'))
            self.assertNotIn(self.config['token'], request.full_url)
            self.assertNotIn(self.config['token'], str(request.headers))
        self.assertIn('lumen_session=', self.web_calls[1].get_header('Cookie'))
        self.assertNotIn(self.config['token'], repr(session))

    def test_current_server_64_character_cookie_uses_existing_transport(self):
        token = 'Aa0_' * 16
        self.cookie = self.cookie.replace('c' * 43, token)
        session = self.session(); session.connect()
        self.assertTrue(session.usable)
        self.assertEqual(session._cookie, token.encode('ascii'))
        self.assertEqual(self.web_calls[1].get_header('Cookie'), 'lumen_session=' + token)
        self.assertEqual(len(self.native_calls[1][2]['challenge']), 64)
        self.assertEqual(len(json.loads(self.web_calls[0].data)['verifier']), 43)
        self.assertTrue(all(request.get_header('Authorization') is None for request in self.web_calls))

    def test_native_request_keeps_cookie_scope_and_checks_current_identity(self):
        session=self.session();session.connect()
        result={'id':USER,'body':'x'*100000}
        def response(request,**kwargs):
            self.web_calls.append(request)
            return Response(result if request.full_url.endswith('/documents') else self.me)
        self.opener.open.side_effect=response
        self.assertEqual(session.request('/api/documents',{'title':'Lumen'},max_bytes=1024**2),result)
        sent=[r for r in self.web_calls if r.full_url.endswith('/documents')]
        self.assertEqual(len(sent),1);self.assertEqual(sent[0].get_header('Origin'),ORIGIN)
        self.assertEqual(sent[0].get_header('X-lumen-csrf'),'csrf-fixture')
        self.assertIsNone(sent[0].get_header('Authorization'))
        self.assertTrue(session.usable)

    def test_native_request_rejects_external_paths_and_unbounded_responses_before_io(self):
        session=self.session();session.connect();before=len(self.web_calls)
        for path in ('https://other.invalid/api/documents','//other.invalid/api/documents','/bridge/me',
                     '/api/documents#fragment','/api/documents\n','/api/../bridge/me','/api/%2e%2e/bridge/me'):
            with self.subTest(path=path),self.assertRaises(host.SessionError):session.request(path)
        for maximum in (0,-1,1024**2+1,True,'100'):
            with self.subTest(maximum=maximum),self.assertRaises(host.SessionError):session.request('/api/documents',max_bytes=maximum)
        self.assertEqual(len(self.web_calls),before)

    def test_uncertain_native_write_never_retries(self):
        session=self.session();session.connect();sent=[]
        def response(request,**kwargs):
            if request.full_url.endswith('/documents'):
                sent.append(request);raise TimeoutError()
            return Response(self.me)
        self.opener.open.side_effect=response
        with self.assertRaises(host.SessionError):session.request('/api/documents',{'title':'Lumen'})
        self.assertTrue(session.uncertain);self.assertFalse(session.usable)
        with self.assertRaises(host.SessionError):session.request('/api/documents',{'title':'Lumen'})
        self.assertEqual(len(sent),1)

    def test_known_native_conflict_is_not_an_uncertain_write(self):
        session=self.session();session.connect()
        def response(request,**kwargs):
            if request.full_url.endswith('/documents'):
                raise host.urllib.error.HTTPError(request.full_url,409,'Conflict',{},None)
            return Response(self.me)
        self.opener.open.side_effect=response
        with self.assertRaises(host.urllib.error.HTTPError):session.request('/api/documents',{'title':'Lumen'})
        self.assertFalse(session.uncertain);self.assertTrue(session.usable)

    def test_native_write_result_is_not_released_after_identity_changes(self):
        session=self.session();session.connect()
        def response(request,**kwargs):
            if request.full_url.endswith('/documents'):
                session.close('identity');return Response({'id':USER})
            return Response(self.me)
        self.opener.open.side_effect=response
        with self.assertRaises(host.SessionError):session.request('/api/documents',{'title':'Lumen'})
        self.assertFalse(session.usable);self.assertTrue(session.uncertain)

    def test_late_native_conflict_body_is_closed_after_expiry_or_identity_change(self):
        for change in ('identity','expired'):
            session=self.session();session.connect();response_body=io.BytesIO(b'Old account response')
            def response(request,**kwargs):
                if request.full_url.endswith('/documents'):
                    if change=='identity':session.close('identity')
                    else:self.clock+=901
                    raise host.urllib.error.HTTPError(request.full_url,409,'Conflict',{},response_body)
                return Response(self.me)
            self.opener.open.side_effect=response
            with self.subTest(change=change),self.assertRaises(host.SessionError):session.request('/api/documents',{'title':'Lumen'})
            self.assertTrue(response_body.closed);self.assertTrue(session.uncertain)
            self.opener.open.side_effect=self.web_request

    def test_cookie_rejects_other_lengths_and_invalid_alphabet(self):
        original = self.cookie
        for token in ['c' * n for n in (42, 44, 63, 65)] + ['c' * 42 + '!', 'c' * 63 + '!']:
            with self.subTest(length=len(token), invalid_alphabet='!' in token):
                self.cookie = original.replace('c' * 43, token)
                session = self.session(); before = len(self.web_calls)
                with self.assertRaises(host.SessionError): session.connect()
                self.assertFalse(session.usable)
                self.assertEqual(len(self.web_calls), before + 1)

    def test_64_character_ticket_is_not_a_valid_session_ticket(self):
        def oversized_ticket(config, path, body=None, **kwargs):
            value = self.native_request(config, path, body, **kwargs)
            return dict(value, ticket='t' * 64) if path.endswith('/session-ticket') else value
        with patch.object(host.lumen_connect, 'request', side_effect=oversized_ticket):
            with self.assertRaises(host.SessionError): self.session().connect()
        self.assertEqual(self.web_calls, [])

    def test_origin_and_ids_reject_ambiguous_or_foreign_binding(self):
        for origin in ['http://lumen.test', ORIGIN+'/', ORIGIN+'?x=1', ORIGIN+'#x',
                       'https://user@lumen.test', ORIGIN+'\\evil', ORIGIN+'%2f', ORIGIN+'\n']:
            with self.subTest(origin=origin), self.assertRaises(host.SessionError):
                host.Binding(origin, USER, DEVICE, 'compose')
        for app in ['reader', 'files', 'translate', 'constructor']:
            with self.subTest(app=app), self.assertRaises(host.SessionError):
                host.Binding(ORIGIN, USER, DEVICE, app)
        with self.assertRaises(host.SessionError):
            host.AppSession(dict(self.config, server='https://other.test'), self.binding)
        with self.assertRaises(host.SessionError):
            host.Binding(ORIGIN, 'not-a-uuid', DEVICE, 'compose')

    def test_exchange_rejects_wrong_actor_app_device_and_deadline(self):
        for key,value in [('user_id',DEVICE),('device_id',USER),('app','notes'),('access','admin'),
                          ('expires',(NOW-timedelta(seconds=1)).isoformat()),
                          ('expires',(NOW+timedelta(hours=1)).isoformat())]:
            with self.subTest(key=key,value=value):
                original=self.exchange; self.exchange=dict(original, **{key:value})
                with self.assertRaises(host.SessionError):self.session().connect()
                self.exchange=original

    def test_cookie_must_be_host_only_secure_and_http_only(self):
        original=self.cookie
        for cookie in [original.replace('; Secure',''),original.replace('; HttpOnly',''),
                       original.replace('Strict','Lax'),original+'; Domain=other.test',
                       original.replace('Max-Age=900','Max-Age=9000'),original.replace('Path=/','Path=/api'),
                       'other=secret; Secure; HttpOnly; SameSite=Strict']:
            with self.subTest(cookie=cookie):
                self.cookie=cookie
                with self.assertRaises(host.SessionError):self.session().connect()
        self.cookie=original

    def test_me_checks_current_binding_and_never_admin(self):
        for key,value in [('id',DEVICE),('device_id',USER),('desktop_app','notes'),
                          ('device_kind','mobile'),('admin',True),('capabilities',['translate','vault']),
                          ('csrf','different')]:
            with self.subTest(key=key):
                original=self.me;self.me=dict(user=dict(original['user'],**{key:value}))
                with self.assertRaises(host.SessionError):self.session().connect()
                self.me=original

    def test_monotonic_expiry_and_revoke_close_access(self):
        session=self.session();session.connect();self.clock=911
        self.assertFalse(session.usable)
        self.assertEqual(session.state,'expired')
        session=self.session();self.clock=10;session.connect()
        self.opener.open.side_effect=host.urllib.error.HTTPError(ORIGIN+'/api/me',403,'fixture',{},None)
        self.assertFalse(session.check())
        self.assertEqual(session.state,'revoked')
        self.assertFalse(session.usable)

    def test_near_expiry_renews_only_auth_without_rotating_cookie_or_losing_draft(self):
        session=self.session();session.connect();session.remember_draft('Noch nicht gespeichert')
        cookie,csrf=session._cookie,session._csrf
        self.clock=860
        self.assertTrue(session.check())
        self.assertEqual(session._cookie,cookie);self.assertEqual(session._csrf,csrf)
        self.assertEqual(session.draft(self.binding),'Noch nicht gespeichert')
        self.assertGreater(session._deadline,1000)
        self.assertEqual(self.native_calls[-1][1],'/bridge/apps/session-renew')
        self.assertEqual(self.native_calls[-1][2],dict(app='compose',session_hash=host.hashlib.sha256(cookie).hexdigest()))
        self.assertEqual(sum(r.get_method()=='POST' for r in self.web_calls),1)

    def test_expired_bound_session_can_be_verified_again_without_a_new_web_login(self):
        session=self.session();session.connect();self.clock=911
        self.assertFalse(session.usable)
        self.assertTrue(session.check());self.assertTrue(session.usable)
        self.assertEqual(sum(r.get_method()=='POST' for r in self.web_calls),1)

    def test_late_or_wrong_renewal_never_reopens_session(self):
        for change in ('closed','account','app','deadline'):
            self.clock=10;session=self.session();session.connect();self.clock=860
            def renewal(config,path,body=None,**kwargs):
                if path.endswith('/session-renew'):
                    value={k:self.exchange[k] for k in ('user_id','device_id','app','expires')}
                    if change=='closed':session.close()
                    elif change=='account':value['user_id']=DEVICE
                    elif change=='app':value['app']='notes'
                    else:value['expires']=(NOW+timedelta(hours=2)).isoformat()
                    return value
                return self.native_request(config,path,body,**kwargs)
            with patch.object(host.lumen_connect,'request',side_effect=renewal):
                self.assertFalse(session.check());self.assertFalse(session.usable)

    def test_interruption_preserves_bound_draft_without_replay(self):
        session=self.session();session.connect();session.remember_draft('Ungesendeter Text')
        calls=len(self.web_calls);session.suspend('offline')
        self.assertEqual(session.draft(self.binding),'Ungesendeter Text')
        self.assertTrue(session.check())
        self.assertEqual(len(self.web_calls),calls+1)
        self.assertTrue(all(r.get_method()=='GET' for r in self.web_calls[calls:]))
        with self.assertRaises(host.SessionError):session.draft(host.Binding(ORIGIN,DEVICE,USER,'compose'))

    def test_unknown_write_stays_locked_without_an_authoritative_receipt(self):
        session=self.session();session.connect();session.observe_write();session.suspend('offline')
        self.assertTrue(session.uncertain)
        self.assertFalse(session.check())
        self.assertFalse(session.usable)
        with self.assertRaises(host.SessionError):session.connect()
        self.assertFalse(any(r.get_method()=='POST' for r in self.web_calls[1:]))

    def test_late_metadata_response_does_not_reopen_closed_session(self):
        session=self.session();session.connect()
        def late(*args,**kwargs):
            session.close();return Response(self.me)
        self.opener.open.side_effect=late
        self.assertFalse(session.check())
        self.assertFalse(session.usable)

    def test_navigation_accepts_only_exact_app_document_and_bound_origin(self):
        self.assertTrue(self.binding.navigation(self.binding.url))
        self.assertTrue(self.binding.navigation(self.binding.url+'#main-content'))
        for value in (None,ORIGIN+'\n/?app=translate&presentation=desktop',
                      ORIGIN+'/?app=translate&app=note&presentation=desktop',
                      ORIGIN+'/?app=translate&presentation=desktop&token=fixture',
                      ORIGIN+'/?app=translate&presentation=desktop#other',
                      ORIGIN+'.evil/?app=translate&presentation=desktop'):
            with self.subTest(value=value):self.assertFalse(self.binding.navigation(value))
        for value in (None,ORIGIN+'\t/api/me','http://lumen.test/api/me',
                      ORIGIN+'.evil/api/me',ORIGIN+'@other.test/api/me',ORIGIN+'\\api/me'):
            with self.subTest(value=value):self.assertFalse(self.binding.resource(value))

    def test_typed_reference_navigation_is_scoped_and_canonical(self):
        for app,page,key in (('notes','note','note'),('projects','projects','project'),('code','code','entry')):
            binding=host.Binding(ORIGIN,USER,DEVICE,app)
            ref=dict(version=2,app=page,id=USER,title='Lumen source',locator=dict(server=ORIGIN,account=USER))
            value=binding.reference_url(ref)
            self.assertTrue(binding.navigation(value));self.assertIn(key+'='+USER,value)
            self.assertNotIn('account',value)
            for invalid in (value+'&'+key+'='+DEVICE,value.replace(USER,'../note'),value+'&token=secret'):
                with self.subTest(value=invalid):self.assertFalse(binding.navigation(invalid))
            for foreign in (dict(ref,locator=dict(server=ORIGIN,account=DEVICE)),dict(ref,app='note' if page!='note' else 'projects')):
                with self.assertRaises(ValueError):binding.reference_url(foreign)

    def test_close_during_ticket_creation_prevents_exchange(self):
        session=self.session();original=self.native_request
        def close_after_ticket(config,path,body=None,**kwargs):
            value=original(config,path,body,**kwargs)
            if path.endswith('/session-ticket'):session.close()
            return value
        with patch.object(host.lumen_connect,'request',side_effect=close_after_ticket):
            with self.assertRaises(host.SessionError):session.connect()
        self.assertFalse(session.usable);self.assertEqual(self.web_calls,[])


if __name__ == '__main__':unittest.main()
