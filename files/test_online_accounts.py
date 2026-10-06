import configparser
import json
import os
from pathlib import Path
import tempfile
import shutil
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from online_accounts import AccountPaths, AccountDialog, accounts, webdav_url, AccountsWidget


class AccountsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {key: str(self.root/key) for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME')})
        env.start(); self.addCleanup(env.stop)

    def fake_rclone(self, code):
        path = self.root/'rclone'; path.write_text('#!/usr/bin/python3\n'+code); path.chmod(0o700)
        return str(path)

    def wait(self, condition):
        deadline = time.monotonic()+5
        while not condition() and time.monotonic()<deadline: QTest.qWait(20)
        self.assertTrue(condition())

    def test_isolated_provider_login_and_onedrive_choice(self):
        helper = self.fake_rclone('''import configparser,json,sys,os
from pathlib import Path
assert not any(k.startswith('RCLONE_') for k in os.environ)
path=Path(sys.argv[sys.argv.index('--config')+1])
c=configparser.ConfigParser(interpolation=None); c.read(path)
if c['drive']['type']=='onedrive' and '--continue' not in sys.argv:
 print(json.dumps({'State':'driveid_final','Option':{'Name':'config_driveid','Examples':[{'Value':'work-drive','Help':'Work'}]}}))
else:
 if c['drive']['type']=='onedrive':
  assert sys.argv[sys.argv.index('--result')+1]=='work-drive'
  c['drive']['drive_id']='work-drive'; c['drive']['drive_type']='business'
 c['drive']['token']=json.dumps({'refresh_token':'synthetic'})
 with path.open('w') as f:c.write(f)
 print(json.dumps({'State':''}))
''')
        with patch('google_drive.shutil.which', return_value=helper), patch.dict(os.environ, RCLONE_CONFIG_DRIVE_TYPE='unwanted'):
            for index, provider in enumerate(('onedrive','dropbox')):
                paths = AccountPaths(str(index)*32, provider, provider+' Work')
                dialog = AccountDialog(None, paths); dialog.show(); dialog.connect_account()
                self.wait(lambda: dialog.job is None)
                if provider == 'onedrive':
                    self.assertFalse(paths.config.exists()); self.assertTrue(dialog.drive_choice.isVisible())
                    dialog.connect_account(); self.wait(lambda: dialog.job is None)
                self.assertEqual(dialog.result(), QDialog.Accepted)
                self.assertTrue(paths.configured()); self.assertEqual(paths.config.stat().st_mode & 0o777, 0o600)
                self.assertEqual(paths.root.stat().st_mode & 0o777, 0o700)
                self.assertEqual(list(paths.root.glob('login-*')), [])
                dialog.deleteLater(); QTest.qWait(10)
        found = accounts(); self.assertEqual(len(found), 2)
        self.assertNotEqual(found[0].mount, found[1].mount)
        self.assertFalse(found[0].contains(found[1].mount))
        self.assertFalse(found[0].contains(found[0].mount/'../outside'))

    def test_webdav_checks_credentials_without_password_in_arguments(self):
        helper = self.fake_rclone('''import sys,configparser
assert 'private-password' not in ' '.join(sys.argv)
if sys.argv[1]=='obscure':
 assert sys.stdin.read()=='private-password'
 print('obscured-test')
else:
 c=configparser.ConfigParser(interpolation=None); c.read(sys.argv[sys.argv.index('--config')+1])
 assert c['drive']['pass']=='obscured-test'
 assert c['drive']['url']=='https://cloud.example/dav/'
 assert c['drive']['user']=='me'
 assert 'private-password' not in str(dict(c['drive']))
''')
        with patch('google_drive.shutil.which', return_value=helper):
            paths = AccountPaths('a'*32,'webdav')
            dialog = AccountDialog(None,paths); dialog.url.setText('https://cloud.example/dav/')
            dialog.user.setText('me'); dialog.secret.setText('private-password'); dialog.connect_account()
            self.wait(lambda: dialog.job is None)
            self.assertEqual(dialog.result(), QDialog.Accepted); self.assertTrue(paths.configured())
            self.assertEqual(dialog.secret.text(), '')
            dialog.deleteLater(); QTest.qWait(10)
        for bad in ('http://cloud.example/', 'https://user:pass@cloud.example/', 'https://cloud.example/?token=secret', 'file:///tmp/a'):
            with self.assertRaises(ValueError): webdav_url(bad)
        with self.assertRaises(ValueError): AccountPaths('../outside', 'dropbox')


    def test_cancel_malformed_selection_and_account_removal(self):
        helper = self.fake_rclone("import time; time.sleep(10)")
        paths = AccountPaths('b'*32, 'onedrive')
        with patch('google_drive.shutil.which', return_value=helper):
            dialog = AccountDialog(None, paths); dialog.connect_account()
            self.wait(lambda: dialog.job is not None)
            dialog.reject(); self.assertIsNone(dialog.job)
            self.assertFalse(paths.config.exists()); self.assertEqual(list(paths.root.glob('login-*')), [])
            dialog.deleteLater(); QTest.qWait(10)
        # A malformed provider response must return to a usable form, never raise in a Qt slot.
        helper = self.fake_rclone('import json; print(json.dumps({"State":"driveid_final", "Option":[]}))')
        with patch('google_drive.shutil.which', return_value=helper):
            dialog = AccountDialog(None, paths); dialog.connect_account(); self.wait(lambda: dialog.job is None)
            self.assertFalse(paths.config.exists()); self.assertIn('nicht abgeschlossen', dialog.status.text())
            dialog.deleteLater(); QTest.qWait(10)
        paths.config.write_text('[drive]\ntype=onedrive\ndescription=Work\ntoken={"refresh_token":"synthetic"}\ndrive_id=1\ndrive_type=business\n')
        widget = AccountsWidget(); self.assertEqual(widget.list.count(), 1)
        with patch.object(AccountPaths, 'mounted', return_value=True), patch.object(QMessageBox, 'question') as ask:
            widget.remove_selected(); ask.assert_not_called(); self.assertTrue(paths.config.exists())
        with patch.object(AccountPaths, 'mounted', return_value=False), patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            widget.remove_selected(); self.assertFalse(paths.config.exists()); self.assertEqual(widget.list.count(), 0)
        widget.deleteLater(); QTest.qWait(10)

    @unittest.skipUnless(shutil.which('rclone'), 'rclone not installed')
    def test_real_rclone_provider_denials_keep_no_accounts(self):
        from urllib.request import urlopen
        from urllib.error import HTTPError
        with patch.dict(os.environ, BROWSER='/bin/false'):
            for index, provider in enumerate(('onedrive', 'dropbox')):
                paths = AccountPaths(str(index+3)*32, provider)
                dialog = AccountDialog(None, paths); dialog.connect_account()
                self.wait(lambda: bool(dialog.login_url) or dialog.job is None)
                self.assertTrue(dialog.login_url)
                state = dialog.login_url.split('state=')[1]
                try:
                    with urlopen('http://127.0.0.1:53682/?error=access_denied&state='+state, timeout=2): pass
                except HTTPError as error:
                    self.assertEqual(error.code, 400); error.close()
                self.wait(lambda: dialog.job is None)
                self.assertNotEqual(dialog.result(), QDialog.Accepted); self.assertFalse(paths.config.exists())
                dialog.deleteLater(); QTest.qWait(10)

    def test_sidebar_shows_account_setup_until_google_login_is_complete(self):
        from app import Window
        window = Window(str(self.root), QSettings(str(self.root/'sidebar.ini'), QSettings.IniFormat))
        def entries(): return [window.places.item(i) for i in range(window.places.count())]
        try:
            self.assertNotIn('Google Drive', [item.text() for item in entries()])
            setup = next(item for item in entries() if item.text() == 'Online-Konten')
            original = window.current_path
            with patch.object(window, 'show_accounts') as show:
                window.places.itemClicked.emit(setup)
                window.places.itemActivated.emit(setup)
                self.assertEqual(show.call_count, 2)
            self.assertEqual(window.current_path, original)
            paths = window.drive.paths; paths.root.mkdir(parents=True, exist_ok=True)
            paths.config.write_text('[drive]\ntype=drive\ntoken={}\n')
            window.populate_places()
            self.assertNotIn('Google Drive', [item.text() for item in entries()])
            paths.config.write_text('[drive]\ntype=drive\ntoken={"refresh_token":"synthetic"}\n')
            window.populate_places()
            item = next(item for item in entries() if item.text() == 'Google Drive')
            self.assertEqual(item.data(Qt.UserRole), str(paths.mount))
            self.assertIn('Online-Konten', [item.text() for item in entries()])
            paths.config.unlink(); window.populate_places()
            self.assertNotIn('Google Drive', [item.text() for item in entries()])
        finally: window.close(); window.deleteLater(); QTest.qWait(100)

    def test_accounts_are_searchable_in_shared_settings(self):
        from settings_dialog import SettingsDialog
        settings = QSettings(str(self.root/'assistant.ini'), QSettings.IniFormat)
        dialog = SettingsDialog(assistant_settings=settings, files_settings=settings, load_system=False)
        try:
            for query in ('Online-Konten', 'OneDrive', 'Dropbox'):
                dialog.navigation.search.setText(query)
                self.assertTrue(any(hit[0] == dialog.accounts_page for hit in dialog.navigation.hits), query)
        finally: dialog.close(); dialog.deleteLater(); QTest.qWait(20)

    def test_files_navigation_and_write_guards_are_per_account(self):
        from app import Window
        configured = []
        for index, provider in enumerate(('dropbox', 'webdav')):
            paths = AccountPaths(str(index+7)*32, provider, provider+' Private')
            paths.root.mkdir(parents=True); paths.mount.mkdir(parents=True)
            paths.config.write_text('[drive]\ntype='+provider+'\ndescription='+paths.label+'\ntoken={"refresh_token":"synthetic"}\nurl=https://example.com/dav/\n')
            configured.append(paths)
        settings = QSettings(str(self.root/'prefs.ini'), QSettings.IniFormat)
        window = Window(str(self.root), settings)
        try:
            drive = window.cloud.for_path(configured[0].mount)
            with patch.object(drive.paths, 'mounted', return_value=True):
                window.navigate(str(drive.paths.mount))
                self.assertEqual(window.heading.text(), drive.paths.label)
                self.assertEqual(window.location_badge.text(), drive.paths.label)
                with patch.object(window, 'error') as error:
                    window.run_operation('copy', [str(drive.paths.mount/'source')], str(configured[1].mount))
                    error.assert_called_once(); self.assertIsNone(window.file_job)
            drive.pending = (window.tabs_data[0], str(drive.paths.mount), True, None)
            window.navigate(str(self.root)); self.assertIsNone(drive.pending)
        finally: window.close(); window.deleteLater(); QTest.qWait(100)


if __name__ == '__main__': unittest.main()
