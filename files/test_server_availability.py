import unittest
from uuid import uuid4
from unittest.mock import patch
from urllib.error import URLError

import server_availability as available


class ServerAvailabilityTest(unittest.TestCase):
    def setUp(self):
        self.config = dict(server='https://server.test', token='private-test-token',
                           account=str(uuid4()), device_id=str(uuid4()))
        self.me = dict(id=self.config['account'], device_id=self.config['device_id'], capabilities=['drive', 'notes'])

    def test_authenticated_binding_and_capabilities(self):
        with patch.object(available.lumen_connect, 'read_config', return_value=self.config), patch.object(available.lumen_connect, 'request', return_value=self.me) as get:
            self.assertEqual(available.capabilities(), {'drive', 'notes'})
            get.assert_called_once_with(self.config, '/bridge/me', timeout=2)

    def test_missing_offline_revoked_wrong_identity_and_changed_pairing_hide(self):
        for result in ({}, dict(self.me, id='invalid'), dict(self.me, device_id=str(uuid4())), dict(self.me, capabilities='drive')):
            with self.subTest(result=result), patch.object(available.lumen_connect, 'read_config', return_value=self.config), patch.object(available.lumen_connect, 'request', return_value=result):
                self.assertFalse(available.capabilities())
        for error in (FileNotFoundError(), URLError('offline'), ValueError('bad config')):
            with patch.object(available.lumen_connect, 'read_config', side_effect=error):
                self.assertFalse(available.capabilities())
        with patch.object(available.lumen_connect, 'read_config', side_effect=[self.config, dict(self.config, token='new-token')]), patch.object(available.lumen_connect, 'request', return_value=self.me):
            self.assertFalse(available.capabilities())

    def test_account_display_label_is_not_an_identity_field(self):
        self.config['account'] = 'My account'
        with patch.object(available.lumen_connect, 'read_config', return_value=self.config), patch.object(available.lumen_connect, 'request', return_value=self.me):
            self.assertEqual(available.capabilities(), {'drive', 'notes'})

    def test_actual_panel_filters_only_server_apps(self):
        from lumen_panel import applications
        with patch.object(available, 'capabilities', return_value=set()):
            names = {r['id'] for r in applications()}
            self.assertTrue({'lumen', 'files', 'system'} <= names)
            self.assertFalse(names & {'wissen', 'workbench', 'code', 'meetings', 'vault', 'inbox', 'photos'})
        with patch.object(available, 'capabilities', return_value={'notes', 'media'}):
            names = {r['id'] for r in applications()}
            self.assertTrue({'wissen', 'meetings'} <= names)
            self.assertFalse(names & {'workbench', 'code', 'vault', 'inbox', 'photos'})


if __name__ == '__main__': unittest.main()
