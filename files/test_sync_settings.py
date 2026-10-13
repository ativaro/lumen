import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from lumen_store import Store
from wissen_data import Notebook
import lumen_connect as connector
import wissen_sync
import sync_settings as sync


class SettingsTest(unittest.TestCase):
    def test_binding_retains_note_scope_and_manual_pause_is_offline(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);store=Store(root/'state');book=Notebook(store,root/'notes',create=True)
            store.set_setting('knowledge/notebook',str(book.root));store.set_setting('knowledge/identity',book.identity)
            cfg=dict(server='https://test.invalid',device_id=str(uuid4()),token='synthetic')
            user=dict(id=str(uuid4()),workspace_id=str(uuid4()),device_id=cfg['device_id'])
            old=wissen_sync.scope(book,cfg)
            store.set_setting('knowledge/background-sync',dict(enabled=True,root=str(book.root),identity=book.identity,scope=old))
            store.set_setting('knowledge/server-sync/'+old,dict(enabled=True,attachments=True))
            with patch.object(sync,'Store',return_value=store),patch.object(connector,'ROOT',root/'config'),patch.object(connector,'CONFIG',root/'config/connection.json'),patch.object(connector,'read_config',return_value=cfg),patch.object(connector,'request',return_value=user),patch.object(sync,'vault_root',return_value=root/'absent'):
                prepared=sync.prepare_connection()
                self.assertEqual(wissen_sync.scope(book,prepared),old)
                with patch.object(connector,'request',side_effect=OSError('offline')) as network:
                    sync.configure('attachments',False);sync.configure('notes',False)
                    network.assert_not_called()
                self.assertFalse(store.setting('knowledge/background-sync')['enabled'])
                self.assertFalse(store.setting('knowledge/server-sync/'+old)['attachments'])

    def test_status_never_claims_old_success_is_current(self):
        self.assertEqual(sync.state_label(dict(enabled=True,last_sync=1)), 'Wartet auf Abgleich')
        self.assertEqual(sync.state_label(dict(enabled=False)), 'Pausiert')
        self.assertEqual(sync.state_label(dict(enabled=True,conflicts=1)), 'Konflikt / neue Fassung prüfen')

    def test_one_failed_area_does_not_stop_other_areas(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(temp)
            with patch.object(sync,'Store',return_value=store),patch.object(sync,'prepare_connection'),patch.object(sync,'project_library'),patch('wissen_sync.background',side_effect=OSError('offline')),patch('memory_sync.synchronize',return_value=dict(enabled=True)) as memory,patch('projects_sync.synchronize',return_value={}) as projects,patch('drive_sync.read',return_value=dict(roots=[])),patch.object(sync,'vault_root',return_value=Path(temp)/'absent'),patch('preferences_sync.synchronize',return_value={}),patch('lumen_notifications.report'):
                result=sync.sync_now()
                self.assertFalse(result['notes']['ok'])
                memory.assert_called_once();projects.assert_called_once()
                self.assertFalse(store.setting('knowledge/background-status')['ok'])
                self.assertTrue(store.setting('memory/sync-status')['ok'])
