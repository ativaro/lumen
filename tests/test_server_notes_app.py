"""Focused launcher checks with private synthetic connection/profile files."""
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['LUMEN_LANGUAGE'] = 'de'

from PySide6.QtWidgets import QApplication, QMessageBox
from server_app_session import SessionError
import lumen_connect
import server_notes_app as notes


USER = '73000000-0000-4000-8000-000000000001'
DEVICE = '73000000-0000-4000-8000-000000000002'


class ServerNotesEntryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('LUMEN_NOTES_TEST_ROOT'))
        self.root = Path(self.temp.name)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir(mode=0o700)
        self.config_root = self.root / 'config'
        self.config_root.mkdir(mode=0o700)
        self.config = self.config_root / 'connection.json'
        self.config.write_text(json.dumps(dict(server='https://notes.example.invalid', device_id=DEVICE,
            token='synthetic-private-fixture')))
        self.config.chmod(0o600)
        self.environment = patch.dict(os.environ, dict(XDG_RUNTIME_DIR=str(self.runtime),
            XDG_CONFIG_HOME=str(self.config_root), LUMEN_DATA=str(self.root / 'state'),
            LUMEN_TOOLS_DATA=str(self.root / 'tools')))
        self.environment.start()
        self.location = patch.object(lumen_connect, 'CONFIG', self.config)
        self.location.start()
        self.job = SimpleNamespace(check=lambda: None)
        self.identity = dict(id=USER, device_id=DEVICE, capabilities=['notes'], permissions_revision=1)

    def tearDown(self):
        self.location.stop()
        self.environment.stop()
        self.temp.cleanup()

    def context(self, identity=None):
        with patch.object(lumen_connect, 'request', return_value=identity or self.identity):
            return notes.context(self.job)

    def test_confirmed_private_connection_and_xdg_runtime(self):
        config, binding, stamp, revision = self.context()
        self.assertEqual(revision, 1)
        self.assertEqual((binding.origin, binding.account, binding.device, binding.app),
            ('https://notes.example.invalid', USER, DEVICE, 'notes'))
        root = notes.runtime_root(binding, stamp)
        self.assertEqual(root.parent, self.runtime)
        self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
        self.assertEqual(notes.runtime_root(binding, stamp), root)
        self.assertNotIn(config['token'], str(root))
        root.rmdir()
        root.symlink_to(self.runtime, target_is_directory=True)
        with self.assertRaises(SessionError):
            notes.runtime_root(binding, stamp)

    def test_missing_private_config_and_wrong_identity_fail_closed(self):
        for changes in (dict(device_id=USER), dict(capabilities=[]), dict(id='invalid'),
                        dict(permissions_revision=True)):
            with self.subTest(changes=changes), self.assertRaises(SessionError):
                self.context(dict(self.identity, **changes))
        self.config.unlink()
        with patch.object(lumen_connect, 'request') as request, self.assertRaises(SessionError):
            notes.context(self.job)
        request.assert_not_called()

    def test_connection_change_during_identity_check_is_rejected(self):
        def changed(*args, **kwargs):
            replacement = self.config.with_suffix('.new')
            replacement.write_text(self.config.read_text())
            replacement.chmod(0o600)
            replacement.replace(self.config)
            return self.identity
        with patch.object(lumen_connect, 'request', side_effect=changed), self.assertRaises(SessionError):
            notes.context(self.job)

    def test_existing_wissen_command_dispatches_before_any_local_library(self):
        import tools_app
        with patch.object(sys, 'argv', ['tools_app.py', 'wissen']), \
                patch.object(tools_app, 'pilot_profile', return_value=None), \
                patch.object(tools_app, 'create_app', return_value=self.app), \
                patch.object(notes, 'run', return_value=7) as run, \
                patch('tools_data.Library', side_effect=AssertionError('No local Notes library')):
            self.assertEqual(tools_app.main(), 7)
        run.assert_called_once_with(self.app, {})

    def test_legacy_arguments_explain_gap_and_never_open_local_notes(self):
        import tools_app
        for arguments in (['file.md'], ['--area', 'user'], ['--section', 'notes'], ['--clipboard']):
            with self.subTest(arguments=arguments), \
                    patch.object(sys, 'argv', ['tools_app.py', 'wissen', *arguments]), \
                    patch.object(tools_app, 'pilot_profile', return_value=None), \
                    patch.object(tools_app, 'create_app', return_value=self.app), \
                    patch.object(notes, 'run') as run, patch.object(QMessageBox, 'warning') as warning, \
                    patch('tools_data.Library', side_effect=AssertionError('No local Notes library')):
                self.assertEqual(tools_app.main(), 2)
                run.assert_not_called()
                self.assertIn('noch nicht unterstützt', warning.call_args.args[2])

    def test_handoff_and_reference_open_the_server_app_with_that_activation(self):
        import tools_app
        for arguments, activation in ((['--handoff', 'synthetic'], dict(handoff='synthetic')),
                                      (['--ref', 'synthetic'], dict(reference='synthetic'))):
            with self.subTest(arguments=arguments), \
                    patch.object(sys, 'argv', ['tools_app.py', 'wissen', *arguments]), \
                    patch.object(tools_app, 'pilot_profile', return_value=None), \
                    patch.object(tools_app, 'create_app', return_value=self.app), \
                    patch.object(notes, 'run', return_value=0) as run, \
                    patch('tools_data.Library', side_effect=AssertionError('No local Notes library')):
                self.assertEqual(tools_app.main(), 0)
                run.assert_called_once_with(self.app, activation)

    def test_missing_server_offers_native_recovery_without_launching_host(self):
        self.config.unlink()
        original_quit = self.app.quitOnLastWindowClosed()
        try:
            with patch.object(lumen_connect, 'request') as request, \
                    patch.object(notes, 'recover', return_value=False) as recover, \
                    patch.object(notes, 'ServerAppWindow') as host:
                self.assertEqual(notes.run(self.app), 1)
            recover.assert_called_once()
            request.assert_not_called()
            host.assert_not_called()
        finally:
            self.app.setQuitOnLastWindowClosed(original_quit)


if __name__ == '__main__':
    unittest.main()
