"""Pairing choices are applied once, not re-enabled by background polling."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

class PairingChoicesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_dialog_allows_deselecting_requested_capabilities(self):
        import lumen_connect_gui as gui
        with patch.object(gui.client,'parse_pairing_uri',side_effect=ValueError):
            dialog=gui.PairingDialog('invalid')
        dialog.preview(dict(account='Synthetic',email='user@test.invalid',name='Desktop',protocol=1,
                            capabilities=['notes','memory_sync'],pairing_features=['capabilities_v1']))
        self.assertTrue(all(c.isChecked() for c in dialog.rights_checks.values()))
        dialog.rights_checks['notes'].setChecked(False)
        with patch.object(dialog,'run_job',side_effect=lambda action,done:action()),patch.object(gui,'accept_pairing') as accepted:
            dialog.confirm()
            accepted.assert_called_once_with('invalid',['memory_sync'])
        dialog.close()

    def test_server_app_permissions_are_visible_and_explicit_optouts(self):
        import lumen_connect_gui as gui
        with patch.object(gui.client,'parse_pairing_uri',side_effect=ValueError):
            dialog=gui.PairingDialog('invalid')
        requested=['notes','projects','code','media','translate']
        dialog.preview(dict(account='Synthetic',email='user@test.invalid',name='Desktop',protocol=1,
                            capabilities=requested,pairing_features=['capabilities_v1']))
        try:
            self.assertEqual(set(dialog.rights_checks),set(requested))
            self.assertTrue(all(check.isEnabled() and check.isChecked() for check in dialog.rights_checks.values()))
            self.assertIn('Lumen Code',dialog.rights_checks['code'].text())
            self.assertIn('Lumen Audio Studio',dialog.rights_checks['media'].text())
            dialog.rights_checks['code'].setChecked(False)
            dialog.rights_checks['translate'].setChecked(False)
            with patch.object(dialog,'run_job',side_effect=lambda action,done:action()),patch.object(gui,'accept_pairing') as accepted:
                dialog.confirm()
            accepted.assert_called_once_with('invalid',['notes','projects','media'])
        finally:dialog.close()

    def test_existing_connection_is_not_upgraded_by_pairing(self):
        import lumen_connect_gui as gui
        import lumen_connect as client
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);config=root/'connection.json';original=b'{"capabilities":["notes"]}'
            config.write_bytes(original)
            with patch.object(client,'ROOT',root),patch.object(client,'CONFIG',config), \
                    patch.object(client,'pairing_request') as pairing,self.assertRaises(ValueError):
                gui.accept_pairing('synthetic',['notes','code','media'])
            pairing.assert_not_called();self.assertEqual(config.read_bytes(),original)

    def test_pairing_prepares_connection_without_publishing_local_data(self):
        import lumen_connect_gui as gui
        import lumen_connect as client
        config=dict(server='https://server.test',device_id=str(uuid4()),token='x'*40,backup_token='y'*40,
                    capabilities=['memory_sync'])
        with tempfile.TemporaryDirectory() as temp, patch.object(client,'ROOT',Path(temp)),patch.object(client,'CONFIG',Path(temp)/'connection.json'), \
             patch.object(client,'pairing_request',return_value=config),patch.object(client,'request',return_value={'device_id':config['device_id']}), \
             patch('sync_settings.prepare_connection',return_value=config) as prepare,patch('lumen_store.Store'),patch('memory_sync.configure') as memory,patch('wissen_sync.sync_config') as notes,patch.object(gui.subprocess,'run') as service:
            service.return_value.returncode=0
            result=gui.accept_pairing('synthetic',['memory_sync'])
            self.assertEqual(result,dict(watching=True,sync_errors=[]))
            prepare.assert_called_once_with();memory.assert_not_called();notes.assert_not_called()

if __name__=='__main__': unittest.main()
