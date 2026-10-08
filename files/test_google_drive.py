import configparser
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox
from google_drive import DriveDialog, DrivePaths, GoogleDrive, oauth_client, bundle_oauth_client


class DriveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {key: str(self.root/key) for key in
            ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME')})
        self.env.start(); self.addCleanup(self.env.stop)
        self.paths = DrivePaths()
        client_patch = patch('google_drive.APP_CLIENT_FILE', self.root/'bundled-client.json')
        client_patch.start(); self.addCleanup(client_patch.stop)

    def wait(self, condition):
        deadline = time.monotonic()+8
        while not condition() and time.monotonic()<deadline: QTest.qWait(20)
        self.assertTrue(condition())

    def client_file(self, value):
        path = self.root/'client.json'; path.write_text(json.dumps(value)); return path

    def test_oauth_import_and_path_boundary(self):
        value = {'installed': {'client_id':'example.apps.googleusercontent.com', 'client_secret':'secret'}}
        self.assertEqual(oauth_client(self.client_file(value)), ('example.apps.googleusercontent.com', 'secret'))
        for bad in ({'web': value['installed']}, {}, {'installed': {'client_id': 4}},
                    {'installed': dict(value['installed'], client_secret='secret\n[type]')}):
            with self.assertRaises(ValueError): oauth_client(self.client_file(bad))
        self.assertTrue(self.paths.contains(self.paths.mount/'folder'))
        self.assertFalse(self.paths.contains(str(self.paths.mount)+'-other'))
        self.assertFalse(self.paths.contains(self.paths.mount/'../local'))
        self.assertFalse(self.paths.configured()); self.assertFalse(self.paths.mounted())

    def fake_rclone(self, code):
        path = self.root/'rclone'
        path.write_text('#!/usr/bin/python3\n'+code); path.chmod(0o700)
        return str(path)

    def dialog(self):
        dialog = DriveDialog(paths=self.paths)
        dialog.custom_client.setChecked(True)
        dialog.client.setText('example.apps.googleusercontent.com'); dialog.secret.setText('synthetic-private')
        dialog.show()
        self.addCleanup(lambda: (dialog.reject(), dialog.deleteLater(), QTest.qWait(10)))
        return dialog

    def test_bundled_client_login_and_missing_or_invalid_bundle(self):
        helper = self.fake_rclone("""import sys, configparser, json, os
from pathlib import Path
assert not any(key.startswith('RCLONE_') for key in os.environ)
assert 'synthetic-app-secret' not in ' '.join(sys.argv)
path = Path(sys.argv[sys.argv.index('--config')+1])
config = configparser.ConfigParser(interpolation=None); config.read(path)
assert config['drive']['client_id'] == 'lumen-test.apps.googleusercontent.com'
assert config['drive']['client_secret'] == 'synthetic-app-secret'
assert config['drive']['scope'] == 'drive'
config['drive']['token'] = json.dumps({'refresh_token': 'synthetic-refresh'})
with path.open('w') as output: config.write(output)
""")
        bundled = self.root/'bundled-client.json'
        with patch('google_drive.shutil.which', return_value=helper):
            for raw in (None, '{}', '{broken'):
                if raw is not None: bundled.write_text(raw)
                dialog = DriveDialog(paths=self.paths); dialog.show()
                self.assertFalse(dialog.buttons.button(QDialogButtonBox.Ok).isEnabled())
                dialog.connect_account(); self.assertIsNone(dialog.job)
                self.assertFalse(dialog.credentials.isVisible())
                dialog.custom_client.setChecked(True)
                self.assertTrue(dialog.buttons.button(QDialogButtonBox.Ok).isEnabled())
                dialog.reject(); dialog.deleteLater()
            source = self.client_file({'installed': {'client_id': 'lumen-test.apps.googleusercontent.com',
                'client_secret': 'synthetic-app-secret', 'token_uri': 'https://untrusted.invalid'},
                'refresh_token': 'must-not-ship'})
            bundle_oauth_client(source, bundled)
            self.assertEqual(set(json.loads(bundled.read_text())), {'installed'})
            self.assertEqual(set(json.loads(bundled.read_text())['installed']), {'client_id', 'client_secret'})
            before = bundled.read_bytes()
            with self.assertRaises(ValueError): bundle_oauth_client(self.client_file({'web': {}}), bundled)
            self.assertEqual(bundled.read_bytes(), before)
            with patch.dict(os.environ, {'RCLONE_CONFIG_DRIVE_CLIENT_ID': 'unwanted'}):
                dialog = DriveDialog(paths=self.paths); dialog.show()
                self.assertFalse(dialog.custom_client.isChecked()); self.assertFalse(dialog.credentials.isVisible())
                self.assertEqual(dialog.client.text(), '')
                self.assertTrue(dialog.buttons.button(QDialogButtonBox.Ok).isEnabled())
                dialog.buttons.button(QDialogButtonBox.Ok).click()
                self.wait(lambda: dialog.job is None)
                self.assertEqual(dialog.result(), QDialog.Accepted)
                dialog.deleteLater()
            self.assertTrue(self.paths.configured())
            self.assertEqual(self.paths.config.stat().st_mode & 0o777, 0o600)
            # A package's client rotation must not change an existing account's identity.
            bundled.write_text('{}')
            before = self.paths.config.read_bytes()
            dialog = DriveDialog(paths=self.paths); dialog.reject(); dialog.deleteLater()
            self.assertEqual(self.paths.config.read_bytes(), before)

    def test_native_login_publishes_private_credentials_and_cancel_keeps_no_account(self):
        helper = self.fake_rclone("""import sys, configparser, json
from pathlib import Path
assert 'synthetic-private' not in ' '.join(sys.argv)
path = Path(sys.argv[sys.argv.index('--config')+1])
config = configparser.ConfigParser(interpolation=None); config.read(path)
config['drive']['token'] = json.dumps({'refresh_token': 'synthetic-refresh', 'access_token': 'synthetic-access'})
with path.open('w') as output: config.write(output)
print('{"State":"","Error":"","Result":""}')
""")
        with patch('google_drive.shutil.which', return_value=helper):
            dialog = self.dialog(); dialog.connect_account()
            self.wait(lambda: dialog.job is None)
            self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertTrue(self.paths.configured())
        self.assertEqual(self.paths.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.paths.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual(list(self.paths.root.glob('login-*')), [])
        self.assertNotIn('synthetic', dialog.status.text()); self.assertEqual(dialog.secret.text(), '')
        self.paths.config.unlink()
        helper = self.fake_rclone('import time\ntime.sleep(30)\n')
        with patch('google_drive.shutil.which', return_value=helper):
            dialog = self.dialog(); dialog.connect_account()
            self.wait(lambda: dialog.job.processId() > 0)
            pid = dialog.job.processId(); dialog.reject()
        self.assertFalse((Path('/proc')/str(pid)).exists())
        self.assertFalse(self.paths.config.exists()); self.assertEqual(list(self.paths.root.glob('login-*')), [])

    @unittest.skipUnless(shutil.which('rclone'), 'optional real rclone OAuth cancellation test')
    def test_real_rclone_browser_denial_leaves_no_credentials(self):
        with patch.dict(os.environ, {'BROWSER': '/bin/false'}):
            dialog = self.dialog(); dialog.connect_account()
            self.wait(lambda: bool(dialog.login_url) or dialog.job is None)
            self.assertTrue(dialog.login_url)
            state = dialog.login_url.split('state=')[1]
            try:
                with urlopen('http://127.0.0.1:53682/?error=access_denied&state='+state, timeout=2): pass
            except HTTPError as error:
                self.assertEqual(error.code, 400); error.close()
            self.wait(lambda: dialog.job is None)
            self.assertNotEqual(dialog.result(), QDialog.Accepted)
            self.assertFalse(self.paths.config.exists())
            self.assertNotIn('synthetic-private', dialog.status.text())

    def test_mount_command_and_tab_navigation_do_not_unmount_other_clients(self):
        from app import Window
        self.paths.root.mkdir(parents=True)
        self.paths.config.write_text('[drive]\ntype=drive\ntoken={"refresh_token":"synthetic"}\n')
        command = self.paths.command()
        self.assertIn('--service-type=notify', command); self.assertIn('--vfs-cache-mode=writes', command)
        self.assertNotIn('synthetic', ' '.join(command))
        self.paths.mount.joinpath('folder').mkdir()
        settings = QSettings(str(self.root/'prefs.ini'), QSettings.IniFormat)
        window = Window(str(self.root), settings); window.show()
        try:
            with patch.object(window.cloud.legacy.paths, 'mounted', return_value=True):
                window.navigate(str(self.paths.mount/'folder'))
                self.assertEqual(window.current_path, str(self.paths.mount/'folder'))
                self.assertEqual(window.location_badge.text(), 'Google Drive')
            with patch.object(window.cloud.legacy.paths, 'mounted', return_value=False), patch.object(window, 'error') as error:
                window.run_operation('mkdir', [str(self.paths.mount/'new-folder')])
                error.assert_called_once(); self.assertIsNone(window.file_job)
            window.cloud.legacy.pending = (window.tabs_data[0], str(self.paths.mount), True, None)
            window.navigate(str(self.root))
            self.assertIsNone(window.cloud.legacy.pending)
            with patch('google_drive.worker_process') as launch:
                window.cloud.legacy.close(); launch.assert_not_called()
        finally: window.close(); window.deleteLater(); QTest.qWait(100)


if __name__ == '__main__': unittest.main()
