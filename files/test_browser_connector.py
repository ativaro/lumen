import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
import browser_connector as browser


class DesktopBrowserTests(unittest.TestCase):
    def test_local_permission_is_bound_to_exact_pairing(self):
        config={'server':'https://test.invalid','device_id':str(uuid4()),'token':'synthetic'}
        with patch.object(browser.client,'read_config',return_value={**config,'browser_access':True}):
            self.assertTrue(browser.allowed(config))
            self.assertFalse(browser.allowed({**config,'token':'changed'}))
        with patch.object(browser.client,'read_config',return_value=config):self.assertFalse(browser.allowed(config))

    def test_sandbox_has_no_home_socket_environment_or_personal_profile(self):
        with tempfile.TemporaryDirectory() as root:
            base=Path(root);(base/'node').symlink_to('/usr/bin/true')
            with patch.object(browser,'BASE',base):args=browser.sandbox_command()
        self.assertIn('--clearenv',args)
        self.assertIn('--unshare-all',args)
        self.assertIn('--die-with-parent',args)
        self.assertNotIn('/home/example',args)
        self.assertIn('/tmp',args)
        self.assertNotIn('--no-sandbox',args)
        self.assertIn('HOME',args)

    def test_no_command_runs_after_local_or_server_revocation(self):
        connector=browser.Connector();config={'token':'test'}
        command={'id':str(uuid4()),'session':str(uuid4()),'method':'start','params':{}}
        for local,rights in ((False,['desktop','browser']),(True,['desktop'])):
            with patch.object(browser,'allowed',return_value=local),patch.object(browser,'ready',return_value=True),patch.object(browser.client,'request',side_effect=[command,{'capabilities':rights}]),patch.object(connector,'execute') as execute:
                with self.assertRaises(ValueError):connector.step(config)
                execute.assert_not_called()

    def test_only_fixed_protocol_methods_not_arbitrary_commands(self):
        connector=browser.Connector()
        for method in ('exec','shell','resources/read'):
            with self.assertRaises(ValueError):connector.execute({'session':str(uuid4()),'method':method,'params':{}})

    def test_runtime_restart_closes_old_browser_instances(self):
        connector=browser.Connector()
        with patch.object(browser,'allowed',return_value=True),patch.object(browser,'ready',return_value=True),patch.object(browser.client,'request',return_value={'reset':True}),patch.object(connector,'close') as close:
            connector.step({})
            close.assert_called_once()

    def test_reply_failure_does_not_reexecute(self):
        connector=browser.Connector();command={'id':str(uuid4()),'session':str(uuid4()),'method':'tools/call','params':{}}
        with patch.object(browser,'allowed',return_value=True),patch.object(browser,'ready',return_value=True),patch.object(browser.client,'request',side_effect=[command,{'capabilities':['desktop','browser']},OSError('lost')]),patch.object(connector,'execute',return_value={}) as execute:
            with self.assertRaises(OSError):connector.step({})
            execute.assert_called_once()

if __name__=='__main__':unittest.main()
