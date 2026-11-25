import json
import unittest
from unittest.mock import patch
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QApplication
from diagnostics_ui import DiagnosticsView


class Reply(QObject):
    readyRead = Signal()
    finished = Signal()
    def __init__(self, payload):
        super().__init__(); self.payload = payload
    def readAll(self):
        value = self.payload; self.payload = b''; return value
    def abort(self): pass
    def error(self): return QNetworkReply.NoError
    def attribute(self, _key): return 200
    def header(self, _key): return 'application/json; charset=utf-8'


class DiagnosticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        with patch('lumen_connect.read_config', side_effect=OSError): self.view = DiagnosticsView()
        self.addCleanup(self.view.deleteLater)
        self.view.server.setText('https://synthetic.invalid')

    def test_native_transport_sends_no_account_credentials_and_does_not_follow_redirects(self):
        reply = Reply(json.dumps(dict(service='Lumen Server', ready=True)).encode())
        with patch.object(self.view.network, 'get', return_value=reply) as request:
            self.view.run(); self.view.run(); self.assertEqual(request.call_count, 1)
            sent = request.call_args.args[0]
            self.assertEqual(sent.url().toString(), 'https://synthetic.invalid/api/status')
            self.assertFalse(sent.hasRawHeader('Authorization')); self.assertFalse(sent.hasRawHeader('Cookie'))
            self.assertEqual(sent.transferTimeout(), 3000)
            self.assertEqual(sent.attribute(QNetworkRequest.RedirectPolicyAttribute), QNetworkRequest.ManualRedirectPolicy)
            self.assertEqual(sent.attribute(QNetworkRequest.CookieLoadControlAttribute), QNetworkRequest.Manual)
            self.assertEqual(sent.attribute(QNetworkRequest.CookieSaveControlAttribute), QNetworkRequest.Manual)
            reply.readyRead.emit(); reply.finished.emit()
        self.assertIn('noch nicht geprüft', self.view.status.text())
        self.assertTrue(self.view.check.isEnabled())

    def test_the_paired_server_is_checked_with_its_private_ca_and_others_without(self):
        import subprocess, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as root:
            ca = Path(root)/'ca.pem'
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256', '-nodes',
                            '-keyout', str(Path(root)/'ca.key'), '-out', str(ca), '-days', '1', '-subj', '/CN=Lumen Server Local CA test'],
                           check=True, capture_output=True)
            config = {'server': 'https://lumen.synthetic.invalid', 'ca_file': str(ca)}
            with patch('lumen_connect.read_config', return_value=config): view = DiagnosticsView()
            self.addCleanup(view.deleteLater)
            self.assertEqual(view.server.text(), 'https://lumen.synthetic.invalid')
            names = lambda sent: {c.subjectDisplayName() for c in sent.sslConfiguration().caCertificates()}
            for address, trusted in (('https://lumen.synthetic.invalid', True), ('https://other.synthetic.invalid', False)):
                view.server.setText(address); reply = Reply(b'{}')
                with patch.object(view.network, 'get', return_value=reply) as request:
                    view.run(); self.assertEqual('Lumen Server Local CA test' in names(request.call_args.args[0]), trusted)
                    reply.finished.emit()

    def test_wrong_service_and_unconfigured_recovery_are_not_reported_as_healthy(self):
        reply = Reply(b'{"service":"foreign","ready":true}')
        with patch.object(self.view.network, 'get', return_value=reply):
            self.view.run(); reply.finished.emit()
        self.assertIn('bleibt offen', self.view.status.text())
        self.view.recovery.setText('https://synthetic.invalid')
        with patch('diagnostics_ui.QDesktopServices.openUrl') as opened:
            self.view.open_recovery(); opened.assert_not_called()

    def test_recovery_requires_an_independent_https_origin(self):
        self.view.recovery.setText('https://diagnostics.synthetic.invalid')
        with patch('diagnostics_ui.QDesktopServices.openUrl', return_value=True) as opened:
            self.view.open_recovery(); self.assertEqual(opened.call_args.args[0].toString(), 'https://diagnostics.synthetic.invalid')
        for value in ('http://diagnostics.synthetic.invalid','https://key@diagnostics.synthetic.invalid','https://diagnostics.synthetic.invalid/private'):
            self.view.recovery.setText(value)
            with patch('diagnostics_ui.QDesktopServices.openUrl') as opened:
                self.view.open_recovery(); opened.assert_not_called()

    def test_recovery_opens_without_a_known_application_address(self):
        self.view.server.clear(); self.view.recovery.setText('https://diagnostics.synthetic.invalid')
        with patch('diagnostics_ui.QDesktopServices.openUrl', return_value=True) as opened:
            self.view.open_recovery(); self.assertEqual(opened.call_count, 1)

if __name__ == '__main__': unittest.main()
