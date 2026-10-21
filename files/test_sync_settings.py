"""Only true local data synchronize; Server Notes are never replicated."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from lumen_store import Store
from lumen_i18n import tr
from wissen_data import Notebook
import lumen_connect as connector
import sync_settings as sync


class SettingsTest(unittest.TestCase):
    def test_binding_preserves_other_areas_without_reopening_old_notebook(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);store=Store(root/'state')
            store.set_setting('knowledge/notebook',str(root/'missing-old-notebook'))
            store.set_setting('knowledge/background-sync',dict(enabled=True,root=str(root/'missing-old-notebook'),identity=[1,2],scope='old'))
            cfg=dict(server='https://test.invalid',device_id=str(uuid4()),token='synthetic')
            user=dict(id=str(uuid4()),workspace_id=str(uuid4()),device_id=cfg['device_id'])
            with patch.object(sync,'Store',return_value=store),patch.object(connector,'ROOT',root/'config'),patch.object(connector,'CONFIG',root/'config/connection.json'),patch.object(connector,'read_config',return_value=cfg),patch.object(connector,'request',return_value=user),patch.object(sync,'vault_root',return_value=root/'absent'),patch('wissen_data.Notebook.__init__',side_effect=AssertionError('retired notebook')):
                prepared=sync.prepare_connection()
                aliases=prepared['sync_binding']['aliases']
                self.assertEqual(len(aliases),3)
                self.assertTrue(store.setting('knowledge/background-sync')['enabled'])
                self.assertFalse((root/'missing-old-notebook').exists())

    def test_old_note_toggle_cannot_reenable_replication_or_change_originals(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp)/'state');book=Notebook(store,Path(temp)/'notes',create=True);note=book.create('Original','Keep me')
            with patch.object(sync,'Store',return_value=store),patch.object(sync,'prepare_connection') as prepare:
                for domain in ('notes','attachments'):
                    self.assertEqual(sync.configure(domain,False),dict(enabled=False,reason='server_owned'))
                    with self.assertRaisesRegex(ValueError,'Lumen Server'):sync.configure(domain,True)
                prepare.assert_not_called()
            self.assertEqual(book.read(note['path']),note)

    def test_snapshot_has_no_note_replica_status_and_preserves_memory(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(temp);store.set_setting('memory/sync-choice',dict(enabled=True,scope='m'))
            store.set_setting('memory/server-sync/m',dict(last_sync=1))
            with patch.object(sync,'Store',return_value=store),patch.object(sync,'project_library'),patch('projects_sync.read_state',return_value={}),patch('drive_sync.read',return_value=dict(roots=[])),patch.object(sync,'vault_root',return_value=Path(temp)/'absent'),patch.object(connector,'read_config',side_effect=FileNotFoundError):
                result=sync.snapshot()
            self.assertNotIn('notes',result);self.assertNotIn('attachments',result);self.assertTrue(result['memory']['enabled'])
            self.assertEqual(set(result),{'memory','projects','vault','preferences','drive','server'})

    def test_status_never_claims_old_success_is_current(self):
        self.assertEqual(sync.state_label(dict(enabled=True,last_sync=1)), tr('Wartet auf Abgleich'))
        self.assertEqual(sync.state_label(dict(enabled=False)), tr('Pausiert'))
        self.assertEqual(sync.state_label(dict(enabled=True,conflicts=1)), tr('Konflikt / neue Fassung prüfen'))

    def test_one_failed_area_does_not_stop_other_areas_or_run_old_notes(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(temp)
            with patch.object(sync,'Store',return_value=store),patch.object(sync,'prepare_connection'),patch.object(sync,'project_library'),patch('wissen_sync.background',side_effect=AssertionError('retired writer')) as notes,patch('memory_sync.synchronize',side_effect=OSError('offline')),patch('projects_sync.synchronize',return_value={}) as projects,patch('drive_sync.read',return_value=dict(roots=[])),patch.object(sync,'vault_root',return_value=Path(temp)/'absent'),patch('preferences_sync.synchronize',return_value={}),patch('lumen_notifications.report'):
                result=sync.sync_now()
                self.assertFalse(result['memory']['ok']);self.assertNotIn('notes',result);self.assertNotIn('attachments',result)
                notes.assert_not_called();projects.assert_called_once();self.assertFalse(store.setting('memory/sync-status')['ok'])
                self.assertIsNone(store.setting('knowledge/background-status'))
