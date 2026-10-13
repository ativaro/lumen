import tempfile
import unittest
from unittest.mock import patch
from lumen_store import Store
import preferences_sync as sync


class PreferencesTest(unittest.TestCase):
    def test_three_way_merge_conflicts_and_disable(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(temp)
            base=dict(language='de',appearance='glass')
            store.set_setting('sync/preferences',dict(enabled=True,scope='same',base=base))
            remote=dict(enabled=True,revision=2,profile=dict(language='en',appearance='glass'))
            with patch.object(sync.connector,'read_config',return_value={}),patch.object(sync,'scope',return_value='same'),patch.object(sync.connector,'request',return_value=remote) as request,patch.object(sync,'local',return_value=dict(language='de',appearance='graphite')),patch.object(sync,'apply') as apply:
                sync.synchronize(store)
                apply.assert_called_once_with(dict(language='en',appearance='graphite'))
                self.assertEqual(request.call_args.args[2]['revision'],2)
                store.set_setting('sync/preferences',dict(enabled=True,scope='same',base=base))
                remote['profile']=dict(language='de',appearance='midnight');apply.reset_mock()
                result=sync.synchronize(store)
                self.assertEqual(result['conflicts'],['appearance']);apply.assert_not_called()
                request.reset_mock();sync.configure(store,False);request.assert_not_called()
                self.assertFalse(store.setting('sync/preferences')['enabled'])

    def test_rejects_security_fields(self):
        with self.assertRaises(ValueError):sync.validate(dict(language='en',appearance='glass',token='no'))
