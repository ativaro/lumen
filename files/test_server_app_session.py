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
