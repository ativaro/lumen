"""Retired Notes sync cannot revive old local writers; originals remain readable."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from lumen_store import Store
from wissen_data import Notebook
import wissen_sync as sync


class NotesRetirementTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store=Store(self.root/'state')
        self.book=Notebook(self.store,self.root/'notes',create=True)
        self.note=self.book.create('Original','Keep all local content')
        self.store.set_setting('knowledge/background-sync',dict(enabled=True,root=str(self.book.root),identity=self.book.identity,scope='old'))
        self.store.set_setting('knowledge/server-sync/old',dict(enabled=True,attachments=True,notes={'n':{'revision':7}}))
        self.before=self.book.read(self.note['path'])

    def test_background_does_not_read_connection_or_notebook(self):
        with patch('lumen_connect.read_config',side_effect=AssertionError('no connection')),patch('wissen_data.Notebook',side_effect=AssertionError('no notebook')):
            self.assertEqual(sync.background(self.store),dict(enabled=False,reason='server_owned'))
        self.assertEqual(self.book.read(self.note['path']),self.before)
        self.assertTrue(self.store.setting('knowledge/background-sync')['enabled'])

    def test_old_direct_writer_is_explicitly_refused_without_any_network(self):
        with patch('lumen_connect.request') as network,patch.object(self.book,'write') as write,patch.object(self.book,'remove') as remove:
            with self.assertRaisesRegex(ValueError,'Lumen Server'):sync.sync(self.book)
            network.assert_not_called();write.assert_not_called();remove.assert_not_called()

    def test_enabling_old_scope_fails_and_disable_does_not_modify_history(self):
        before=self.store.setting('knowledge/server-sync/old')
        with patch('lumen_connect.read_config') as config:
            with self.assertRaisesRegex(ValueError,'Lumen Server'):sync.sync_config(self.book,'old',True,attachments=True)
            self.assertEqual(sync.sync_config(self.book,'old',False),dict(enabled=False,reason='server_owned'))
            config.assert_not_called()
        self.assertEqual(before,self.store.setting('knowledge/server-sync/old'))

    def test_old_enabled_and_info_cannot_claim_sync_is_active(self):
        self.assertFalse(sync.enabled(self.book))
        info=sync.sync_info(self.book)
        self.assertFalse(info['enabled']);self.assertFalse(info['allowed']);self.assertEqual(info['reason'],'server_owned')

    def test_old_ui_adds_neither_timer_nor_menu_action(self):
        import wissen_sync_ui
        window=SimpleNamespace(notebook_menu=Mock(),action=Mock())
        wissen_sync_ui.install(window);wissen_sync_ui.configure(window);wissen_sync_ui.synchronize(window)
        window.notebook_menu.addAction.assert_not_called();window.action.assert_not_called();self.assertFalse(hasattr(window,'sync_timer'))

    def test_separate_legacy_connector_helper_process_returns_disabled(self):
        env=dict(os.environ,HOME=str(self.root/'home'),XDG_CONFIG_HOME=str(self.root/'config'),LUMEN_DATA=str(self.root/'other-state'))
        run=subprocess.run([sys.executable,str(Path(sync.__file__).resolve())],env=env,capture_output=True,text=True,timeout=10)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(run.stdout),dict(enabled=False,reason='server_owned'))
        self.assertFalse((self.root/'other-state').exists())

    def test_memory_text_helper_keeps_existing_heading_semantics(self):
        self.assertIn('# Memory',sync.remote_text(dict(title='Memory',body='Keep memory text')))
        self.assertIn('Keep memory text',sync.remote_text(dict(title='Memory',body='Keep memory text')))

    def test_connector_fallback_only_runs_memory_and_other_remaining_areas(self):
        import lumen_connect as client
        with patch.object(client,'_DATA_PROCESS',None),patch.object(client,'_DATA_NEXT',0), \
                patch('pathlib.Path.exists',return_value=False), \
                patch.object(client,'sync_memory') as memory,patch.object(client,'sync_projects'), \
                patch.object(client,'sync_drive'),patch.object(client,'sync_vault'), \
                patch.object(client.subprocess,'Popen') as spawn:
            client.sync_data();memory.assert_called_once_with();spawn.assert_not_called()
        self.assertFalse(hasattr(client,'sync_notes'))

    def test_shared_asset_folder_helper_still_verifies_symlinks(self):
        sync.ensure_folder(self.book,'Folder/Nested')
        self.assertTrue((self.book.root/'Folder/Nested').is_dir())
        (self.book.root/'Link').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises((ValueError,OSError)):sync.ensure_folder(self.book,'Link/Nested')
        self.assertEqual(self.book.read(self.note['path']),self.before)
