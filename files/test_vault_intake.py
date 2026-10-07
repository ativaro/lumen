"""Synthetic credentials only; no real chat, engine, vault or network access."""
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from lumen_mcp_tools import DEFINITIONS, invoke
from vault_access import VaultError
from vault_intake import IntakeSources, select

SAVED = {'saved': True, 'reference': 'vault:11111111-2222-3333-4444-555555555555'}


class IntakeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, XDG_RUNTIME_DIR=self.tmp))
        self.sources = IntakeSources()
        self.addCleanup(self.sources.close)
        self.source = self.sources.add('User: sünthétique\nSecret: demo-only-秘密\nhttps://example.invalid')
        self.args = dict(source=self.source, title='Synthetic account', kind='login', fields={
            'username': {'line': 1, 'word': 2}, 'secret': {'line': 2, 'word': 2}, 'url': {'line': 3}})

    def call(self):
        return invoke('lumen_vault_store_from_chat', self.args)

    def test_numeric_selectors_prefill_locally_and_return_reference_only(self):
        with patch('vault_access.request', return_value=SAVED) as native:
            result = self.call()
        self.assertEqual(result, SAVED)
        values = native.call_args.args[0]
        self.assertEqual(values['prefill'], dict(UserName='sünthétique', Password='demo-only-秘密', URL='https://example.invalid'))
        self.assertNotIn('demo-only', json.dumps(self.args))
        self.assertNotIn('demo-only', json.dumps(result))
        self.assertNotIn('LumenApiEnabled', values['prefill'])
        self.assertEqual(native.call_args.kwargs['launch'], True)
        self.assertEqual([p.name for p in Path(self.tmp).iterdir()], [self.sources.path.name])
        self.assertTrue(self.sources.path.is_socket())

    def test_decline_unknown_outcome_and_success_are_not_replayed(self):
        for outcome in (VaultError('entry_not_saved'), ValueError('Synthetic transport failure'), SAVED):
            with self.subTest(outcome=type(outcome).__name__):
                self.args['source'] = self.sources.add('a\nb\nc')
                self.args['fields'] = {'secret': {'line': 2}}
                with patch('vault_access.request', side_effect=outcome if isinstance(outcome, Exception) else None,
                           return_value=SAVED) as native:
                    try:
                        self.call()
                    except ValueError:
                        pass
                    self.args['fields'] = {'secret': {'line': 2, 'start': 0, 'end': 1}}
                    with self.assertRaises(ValueError):
                        self.call()
                    self.assertEqual(native.call_count, 1)

    def test_unlock_and_busy_allow_retry_without_losing_values(self):
        for code in ('unlock_vault_then_retry', 'vault_busy'):
            with patch('vault_access.request', side_effect=VaultError(code)):
                with self.assertRaises(VaultError) as error:
                    self.call()
                self.assertEqual(error.exception.code, code)
        with patch('vault_access.request', return_value=SAVED):
            self.assertEqual(self.call(), SAVED)

    def test_expiry_bounds_and_shutdown_invalidate_source(self):
        key = self.source.split('.')[1]
        with self.sources.lock:
            _, text = self.sources.sources[key]
            self.sources.sources[key] = (time.monotonic() - 1, text)
        with patch('vault_access.request') as native:
            with self.assertRaisesRegex(ValueError, 'expired'):
                self.call()
            native.assert_not_called()
        self.assertEqual(self.sources.add('a' * 16385), '')
        for _ in range(30):
            self.sources.add('synthetic')
        self.assertLessEqual(len(self.sources.sources), 16)
        self.sources.close()
        self.assertFalse(self.sources.sources)
        self.assertFalse(self.sources.path.exists())

    def test_selectors_unicode_empty_lines_and_strict_ranges(self):
        self.assertEqual(select('题🙂: geheim\n\n geheim ', {'line': 1, 'start': 4, 'end': 10}), 'geheim')
        self.assertEqual(select('題🙂: geheim', {'line': 1, 'word': 1, 'start': 0, 'end': 2}), '題🙂')
        self.assertEqual(select('a\n\n geheim ', {'line': 3}), ' geheim ')
        for selector in ({'line': True}, {'line': 0}, {'line': 4}, {'line': 1, 'start': -1},
                         {'line': 1, 'start': 2, 'end': 1}, {'line': 1, 'end': 999},
                         {'line': 1, 'word': 0}, {'line': 1, 'word': 1.5}, {'line': 1, 'secret': 'value'}):
            with self.subTest(selector=selector), self.assertRaises(ValueError):
                select('demo only', selector)

    def test_native_limits_and_unknown_fields_fail_before_dispatch(self):
        for text, fields in [('x' * 1025, {'username': {'line': 1}, 'secret': {'line': 1}}),
                             ('x\tbad', {'secret': {'line': 1}}),
                             ('x', {'secret': {'line': 1}, 'LumenApiEnabled': {'line': 1}})]:
            self.args.update(source=self.sources.add(text), fields=fields)
            with patch('vault_access.request') as native:
                with self.assertRaises(ValueError):
                    self.call()
                native.assert_not_called()

    def test_tool_schema_accepts_only_numeric_references(self):
        from test_mcp import mcp
        schema = DEFINITIONS['lumen_vault_store_from_chat']['schema']
        mcp.validate_schema(self.args, schema)
        self.assertTrue(DEFINITIONS['lumen_vault_store_from_chat']['native_confirmation'])
        for bad in ('demo-password', {'line': 2, 'value': 'demo-password'}):
            self.args['fields']['secret'] = bad
            with self.assertRaises(ValueError):
                mcp.validate_schema(self.args, schema)

    def test_real_mcp_worker_resolves_only_in_local_source_service(self):
        from test_mcp import mcp
        with patch('vault_access.request', return_value=SAVED) as native:
            self.assertEqual(mcp.tool_native('lumen_vault_store_from_chat', self.args), SAVED)
        self.assertEqual(native.call_args.args[0]['prefill']['Password'], 'demo-only-秘密')

    def test_tool_disconnect_closes_pending_native_connection(self):
        received, closed = threading.Event(), threading.Event()
        server = socket.socket(socket.AF_UNIX)
        self.addCleanup(server.close)
        endpoint = Path(self.tmp) / 'lumen-vault-access'
        server.bind(str(endpoint)); endpoint.chmod(0o600); server.listen(1); server.settimeout(3)
        def native():
            with server.accept()[0] as peer:
                peer.settimeout(3)
                data = bytearray()
                while b'\n' not in data:
                    data.extend(peer.recv(65536))
                received.set()
                if peer.recv(1) == b'':
                    closed.set()
        thread = threading.Thread(target=native, daemon=True); thread.start()
        with patch('vault_access.subprocess.Popen'):
            with socket.socket(socket.AF_UNIX) as client:
                client.connect(str(self.sources.path))
                client.sendall(json.dumps(self.args).encode() + b'\n')
                self.assertTrue(received.wait(3))
            self.assertTrue(closed.wait(3), 'Aborted MCP intake must dismiss pending native confirmation')
        thread.join(3)

    def test_unexpected_native_output_is_not_exported(self):
        with patch('vault_access.request', return_value={'saved': True, 'reference': SAVED['reference'], 'Password': 'SYNTHETIC'}):
            self.assertEqual(self.call(), SAVED)

    def test_closed_tool_connection_cancels_before_native_dispatch(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        right.close()
        with patch('vault_access.request', side_effect=lambda *a, **kw: {'cancelled': kw['cancelled']()}) as native:
            self.sources._store(self.args, left)
            self.assertEqual(native.call_count, 1)
            self.assertTrue(native.call_args.kwargs['cancelled']())
