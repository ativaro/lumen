import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request
from urllib.error import HTTPError
from uuid import uuid4


class Response(io.BytesIO):
    status = 200
    reason = 'OK'
    headers = {}

    def isclosed(self):
        return self.closed or self.tell() == len(self.getvalue())


class Connection:
    def __init__(self, *args, **kwargs):
        self.sock = None
        self.closed = False
        self.calls = []
        self.response = lambda: Response(b'{}')

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))

    def getresponse(self):
        return self.response()

    def close(self):
        self.closed = True


class SessionTest(unittest.TestCase):
    config = dict(server='https://staging.invalid', token='synthetic-test-token')

    def request(self, url='https://staging.invalid/bridge/drive/uploads/one'):
        return Request(url, data=b'{}', headers={'Authorization': 'Bearer synthetic-test-token'})

    def test_reuses_connection_and_tls_context_then_closes(self):
        import drive_http
        import drive_transport
        with patch.object(drive_http, 'HTTPSConnection', side_effect=Connection) as create, patch.object(drive_http.lumen_connect, 'tls_context', return_value=object()) as tls:
            with drive_transport.session(self.config) as session:
                for _ in range(3):
                    with drive_transport.opener(self.config).open(self.request()) as response:
                        response.read()
                connection = session.connection
                self.assertEqual(len(connection.calls), 3)
                self.assertEqual(create.call_count, 1)
                tls.assert_called_once_with(self.config)
                self.assertIsNot(drive_transport.opener(dict(self.config, token='different-account')), session)
            self.assertTrue(connection.closed)
            self.assertIsNone(getattr(drive_transport._active, 'session', None))

    def test_origin_auth_redirect_and_incomplete_response_are_closed(self):
        import drive_http
        session = drive_http.Session(self.config)
        with patch.object(drive_http, 'HTTPSConnection', side_effect=Connection) as create, patch.object(drive_http.lumen_connect, 'tls_context', return_value=object()):
            for url in ('https://elsewhere.invalid/bridge/drive/uploads/a', 'http://staging.invalid/bridge/drive/uploads/a', 'https://staging.invalid/api/me'):
                with self.assertRaises(ValueError), session.open(self.request(url)):
                    pass
            wrong = self.request(); wrong.add_header('Authorization', 'Bearer other-user')
            with self.assertRaises(ValueError), session.open(wrong):
                pass
            self.assertEqual(create.call_count, 0)
            with session.open(self.request()) as response:
                connection = session.connection
                response.read(1)
            self.assertTrue(connection.closed)
            self.assertIsNone(session.connection)
            session.connection = Connection()
            response = Response(b'redirect'); response.status = 302
            session.connection.response = lambda: response
            with self.assertRaises(HTTPError) as error, session.open(self.request()):
                pass
            self.assertEqual(error.exception.code, 302)
            error.exception.close()
            self.assertIsNone(session.connection)

    def test_uncertain_write_is_not_replayed(self):
        import drive_http
        session = drive_http.Session(self.config)
        session.context = object()
        connection = Connection(); session.connection = connection
        connection.getresponse = lambda: (_ for _ in ()).throw(ConnectionResetError())
        with self.assertRaises(ConnectionResetError), session.open(self.request()):
            pass
        self.assertEqual(len(connection.calls), 1)
        self.assertTrue(connection.closed)


class CleanupTest(unittest.TestCase):
    def test_current_and_legacy_tickets_cancel_only_unfinished_uploads(self):
        import lumen_transfers
        import drive_transport
        import drive_sync
        import lumen_connect
        config = SessionTest.config
        for legacy in (None, 'old-project'):
            drive = dict(scope=drive_sync.scope(config), folder=None)
            if legacy:
                drive['space'] = legacy
            ticket = dict(drive=drive, upload_plan=dict(files=[dict(request='done'), dict(request='pending')]), upload_done=['done'], action='drive-upload')
            with patch.object(lumen_connect, 'read_config', return_value=config), patch.object(drive_transport, 'request') as request:
                lumen_transfers.cleanup(None, ticket)
                request.assert_called_once_with(config, '/uploads/pending' + ('?workspace=old-project' if legacy else ''), method='DELETE')
                request.reset_mock()
                ticket['drive'] = {}
                with self.assertRaises(KeyError):
                    lumen_transfers.cleanup(None, ticket)
                request.assert_not_called()
                ticket['drive'] = dict(scope='another-account')
                with self.assertRaises(ValueError):
                    lumen_transfers.cleanup(None, ticket)
                request.assert_not_called()


class UploadStampTest(unittest.TestCase):
    def setUp(self):
        import drive_local
        import drive_transport
        from transfer_copy import root
        self.local=drive_local;self.transport=drive_transport
        self.base=Path(self.enterContext(tempfile.TemporaryDirectory(dir=os.environ.get('LUMEN_IMPORT_FIXTURES'))))
        self.path=self.base/'selected.txt';self.content=b'confirmed original bytes'
        self.path.write_bytes(self.content);self.root=root(self.base)
        self.stamp=self.local.signature(self.path.stat());self.key=str(uuid4())
        self.args=(SessionTest.config,self.root,self.path.name,str(uuid4()),str(uuid4()),self.local.checksum(self.root,self.path.name))
        self.calls=[]

    def wire(self,config,path,body=None,method='POST',content_type='application/json'):
        self.calls.append((path,method,body))
        if method=='PUT':return dict(offset=len(body))
        if path.endswith('/finish'):return dict(id=self.key)
        return dict(id=self.key,size=len(self.content),offset=0)

    def test_expected_stamp_allows_unchanged_fd_and_old_positional_callers(self):
        for options in ({},{'expected_stamp':self.stamp}):
            self.calls.clear();progress=[]
            with patch.object(self.transport,'request',side_effect=self.wire):
                result=self.transport.upload(*self.args,None,lambda *value:progress.append(value),**options)
            self.assertEqual(result,dict(id=self.key))
            self.assertEqual([body for _,method,body in self.calls if method=='PUT'],[self.content])
            self.assertEqual([method for _,method,_ in self.calls],['POST','PUT','POST'])
            self.assertTrue(progress)

    def test_replacement_or_in_place_edit_before_stream_open_sends_nothing(self):
        for replace in (True,False):
            self.path.write_bytes(self.content);stamp=self.local.signature(self.path.stat())
            if replace:
                other=self.base/'new';other.write_bytes(b'X'*len(self.content));other.replace(self.path)
            else:self.path.write_bytes(b'X'*len(self.content))
            with patch.object(self.transport,'request') as request,self.assertRaises(ValueError):
                self.transport.upload(*self.args,expected_stamp=stamp)
            request.assert_not_called()

    def test_stream_open_still_rejects_symlink_directory_and_replaced_parent(self):
        self.path.unlink();other=self.base/'other';other.write_bytes(self.content);self.path.symlink_to(other)
        with patch.object(self.transport,'request') as request,self.assertRaises((OSError,ValueError)):
            self.transport.upload(*self.args,expected_stamp=self.stamp)
        request.assert_not_called()
        self.path.unlink();self.path.mkdir()
        with patch.object(self.transport,'request') as request,self.assertRaises((OSError,ValueError)):
            self.transport.upload(*self.args,expected_stamp=self.stamp)
        request.assert_not_called()
        self.path.rmdir();self.path.write_bytes(self.content)
        self.root['identity'][1]+=1
        with patch.object(self.transport,'request') as request,self.assertRaises(ValueError):
            self.transport.upload(*self.args,expected_stamp=self.stamp)
        request.assert_not_called()

    def test_legacy_stream_checks_the_same_stamp_before_opening_http(self):
        for options in ({},{'expected_stamp':self.stamp}):
            bodies=[]
            def opened(request,timeout):
                bodies.append(b''.join(request.data));return Response(b'{"ok":true}')
            with patch.object(self.transport,'opener') as opener:
                opener.return_value.open.side_effect=opened
                self.assertEqual(self.transport.legacy_upload(*self.args,**options),dict(ok=True))
            self.assertEqual(len(bodies),1);self.assertIn(self.content,bodies[0])
        other=self.base/'new';other.write_bytes(b'X'*len(self.content));other.replace(self.path)
        with patch.object(self.transport,'opener') as opener,self.assertRaises(ValueError):
            self.transport.legacy_upload(*self.args,expected_stamp=self.stamp)
        opener.assert_not_called()

    def test_legacy_fallback_rechecks_the_reopened_fd(self):
        error=HTTPError('https://staging.invalid/bridge/drive/uploads/test',404,'Not found',None,None)
        self.addCleanup(error.close)
        def missing(*args):
            other=self.base/'new';other.write_bytes(b'X'*len(self.content));other.replace(self.path)
            raise error
        with patch.object(self.transport,'request',side_effect=missing) as request, \
             patch.object(self.transport,'opener') as opener,self.assertRaises(ValueError):
            self.transport.upload(*self.args,legacy_target=str(uuid4()),expected_stamp=self.stamp)
        self.assertEqual(request.call_count,1);opener.assert_not_called()

    def test_legacy_fallback_preserves_old_callers_and_unchanged_opt_in(self):
        for options in ({},{'expected_stamp':self.stamp}):
            error=HTTPError('https://staging.invalid/bridge/drive/uploads/test',404,'Not found',None,None)
            self.addCleanup(error.close);bodies=[]
            def opened(request,timeout):
                bodies.append(b''.join(request.data));return Response(b'{"ok":true}')
            with patch.object(self.transport,'request',side_effect=error) as request, \
                 patch.object(self.transport,'opener') as opener:
                opener.return_value.open.side_effect=opened
                self.assertEqual(self.transport.upload(*self.args,legacy_target=str(uuid4()),**options),dict(ok=True))
            self.assertEqual(request.call_count,1)
            self.assertEqual(len(bodies),1);self.assertIn(self.content,bodies[0])

    def test_opt_in_legacy_stream_rejects_in_place_changes_before_file_bytes(self):
        sent=[]
        def opened(request,timeout):
            self.path.write_bytes(b'X'*len(self.content))
            for chunk in request.data:sent.append(chunk)
            raise AssertionError('Changed file should not finish')
        with patch.object(self.transport,'opener') as opener,self.assertRaises(ValueError):
            opener.return_value.open.side_effect=opened
            self.transport.legacy_upload(*self.args,expected_stamp=self.stamp)
        self.assertEqual(len(sent),1)
        self.assertNotIn(self.content,sent[0]);self.assertNotIn(b'X'*len(self.content),sent[0])


if __name__ == '__main__':
    unittest.main()
