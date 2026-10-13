import json
import unittest
from unittest.mock import patch
from uuid import uuid4
import sync_identity as sync


class IdentityTest(unittest.TestCase):
    def test_renewal_preserves_checkpoint_but_account_and_offline_fail_closed(self):
        user = dict(id=str(uuid4()), workspace_id=str(uuid4()), device_id=str(uuid4()))
        cfg = dict(server='https://test.invalid', token='old-secret', device_id=user['device_id'])
        old = 'a' * 64
        self.assertEqual(sync.scope(cfg, ['notes'], old), old)
        with patch('lumen_connect.request', return_value=user) as request:
            bound = sync.prepare(cfg, [(['notes'], old)])
            self.assertNotIn('secret', json.dumps(bound['sync_binding']))
            bound['token'] = 'renewed'
            self.assertEqual(sync.scope(bound, ['notes'], 'b' * 64), old)
            fresh = {k: v for k, v in bound.items() if isinstance(k, str)}
            request.side_effect = OSError('offline')
            with self.assertRaises(OSError): sync.scope(fresh, ['notes'], 'b' * 64)
            request.side_effect = None
            request.return_value = dict(user, id=str(uuid4()))
            bound['token'] = 'other'
            with self.assertRaises(ValueError): sync.scope(bound, ['notes'], 'b' * 64)

    def test_device_mismatch_and_bad_alias(self):
        user = dict(id=str(uuid4()), workspace_id=str(uuid4()), device_id=str(uuid4()))
        cfg = dict(server='https://test.invalid', token='synthetic', device_id=str(uuid4()))
        with patch('lumen_connect.request', return_value=user):
            with self.assertRaises(ValueError): sync.prepare(cfg, [])
            cfg['device_id'] = user['device_id']
            bound = sync.prepare(cfg, [(['drive'], 'invalid')])
            with self.assertRaises(ValueError): sync.scope(bound, ['drive'], 'a' * 64)


if __name__ == '__main__': unittest.main()
