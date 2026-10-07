"""Paired target scoping, TLS failures and secret-free metadata/commands."""
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import vault_targets as target
import vault_data as vault
from lumen_jobs import Job


class ServerTargetTest(unittest.TestCase):
    def setUp(self):
        self.request_patch = patch.object(target.connector, 'request', return_value=[])
        self.request_patch.start()
        self.addCleanup(self.request_patch.stop)

    config = dict(server='https://server.test', device_id='12345678-1234-1234-1234-123456789abc',
                  backup_token='synthetic-backup-token', token='synthetic-bridge-token')

    def test_pairing_scope_and_private_transport(self):
        with patch.object(target.connector, 'read_config', return_value=self.config):
            descriptor = target.available()[0]['server_target']
            self.assertNotIn('token', json.dumps(descriptor))
            with self.assertRaises(ValueError): target.connection(dict(descriptor, server='https://other.test'))
            plan = dict(repository=target.repository(descriptor), server_target=descriptor)
            class Runner:
                def command(self, args, **kwargs):
                    assert 'synthetic-backup-token' not in ' '.join(args)
                    assert 'synthetic-key' not in ' '.join(args)
                    assert kwargs['env']['RESTIC_REST_PASSWORD'] == 'synthetic-backup-token'
                    assert kwargs['data'] == b'synthetic-key\n'
                    assert 'BEGIN CERTIFICATE' in Path(args[args.index('--cacert')+1]).read_text()
                    raise ValueError('remote echoed synthetic-backup-token synthetic-key')
            with self.assertRaises(ValueError) as error:
                target.command(plan, 'synthetic-key', ['snapshots'], Runner(), 'restic', 30)
            self.assertNotIn('synthetic', str(error.exception))
            with self.assertRaises(ValueError):
                target.command(dict(plan, repository='rest:https://other.test/'), 'key', [], None, 'restic', 30)

    def test_only_404_initializes_and_redirects_are_denied(self):
        with patch.object(target.connector, 'read_config', return_value=self.config), patch.object(target.urllib.request, 'build_opener') as opener:
            descriptor = target.available()[0]['server_target']
            for code in (301, 302, 401, 403, 500):
                opener.return_value.open.side_effect = urllib.error.HTTPError('https://server.test', code, '', {}, None)
                with self.assertRaises(ValueError): target.probe(descriptor)
            opener.return_value.open.side_effect = urllib.error.HTTPError('https://server.test', 404, '', {}, None)
            self.assertFalse(target.probe(descriptor)['existing'])
            opener.return_value.open.side_effect = urllib.error.URLError('bad certificate')
            with self.assertRaises(ValueError): target.probe(descriptor)

    def test_recovery_target_is_explicit_and_never_allows_backup(self):
        config = dict(self.config)
        old = 'abcdefab-1234-1234-1234-123456789abc'
        grants = [dict(device_id=old, backup_token='synthetic-recovery-token', name='Old desktop')]
        with patch.object(target.connector, 'read_config', return_value=config), patch.object(target.connector, 'request', return_value=grants):
            selected = target.available()[1]['server_target']
            connection, descriptor = target.connection(selected)
            self.assertTrue(connection['recovery'])
            self.assertEqual(descriptor['device_id'], old)
            with self.assertRaises(ValueError):
                target.command(dict(repository=target.repository(selected), server_target=selected), 'key', ['backup'], None, 'restic', 30)
        with patch.object(target.connector, 'read_config', return_value=config):
            with self.assertRaises(ValueError): target.connection(selected)

    def test_job_environment_and_remote_source_validation(self):
        import sys
        from lumen_i18n import worker_environment
        output = Job(lambda _: None).command([sys.executable, '-c', 'import os;print(os.environ["LUMEN_TEST_VALUE"])'],
                                             env=dict(worker_environment(), LUMEN_TEST_VALUE='synthetic'))
        self.assertEqual(output.strip(), b'synthetic')
        with tempfile.TemporaryDirectory() as directory:
            repo = target.repository({k: self.config[k] for k in ('server', 'device_id')})
            self.assertEqual(vault.paths(repo, [directory]), (repo, [directory]))
            with self.assertRaises(ValueError): vault.paths(repo, [])
            with self.assertRaises(OSError): vault.paths(repo, [directory + '/missing'])


if __name__ == '__main__': unittest.main()
