import io
import unittest
from unittest.mock import patch
from urllib.request import Request
from urllib.error import HTTPError


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


if __name__ == '__main__':
    unittest.main()
