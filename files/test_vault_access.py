"""Synthetic native Vault transport tests, no credentials or real vault access."""
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from vault_access import request, INSTRUCTION
from lumen_mcp_tools import DEFINITIONS, invoke


class VaultAccessTest(unittest.TestCase):
    def test_secret_parameters_are_not_in_tool_contract(self):
        self.assertEqual(set(DEFINITIONS['lumen_vault_store']['schema']['properties']), {'title', 'kind'})
        self.assertFalse(DEFINITIONS['lumen_vault_store']['schema']['additionalProperties'])
        self.assertTrue(DEFINITIONS['lumen_vault_store']['action'])
        self.assertIn('never in Markdown', INSTRUCTION)
        self.assertNotIn('token', DEFINITIONS['lumen_bookstack_read']['schema']['properties'])

    def test_adapter_never_supplies_credentials(self):
        with patch('vault_access.request', return_value={'saved': True, 'reference': 'vault:public-id'}) as native:
            result = invoke('lumen_vault_store', {'title': 'Documentation', 'kind': 'token'})
        native.assert_called_once_with({'operation': 'store', 'title': 'Documentation', 'kind': 'token'}, launch=True)
        self.assertEqual(result, {'saved': True, 'reference': 'vault:public-id'})

    def exercise(self, response, operation="check"):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, XDG_RUNTIME_DIR=directory):
            endpoint = Path(directory)/'lumen-vault-access'
            service = socket.socket(socket.AF_UNIX)
            service.bind(str(endpoint)); endpoint.chmod(0o600); service.listen(1)
            received = []
            def serve():
                with service:
                    connection, _ = service.accept()
                    with connection:
                        received.append(json.loads(connection.recv(4096)))
                        connection.sendall(response)
            thread = threading.Thread(target=serve); thread.start()
            try:
                result = request({'operation': operation})
            finally:
                thread.join(timeout=2)
            self.assertEqual(received, [{'operation': operation}])
            return result

    def test_mcp_disconnect_does_not_claim_cancellation(self):
        with self.assertRaisesRegex(ValueError, 'outcome is unknown'):
            self.exercise(b'', operation='mcp_call')

    def test_generic_tools_do_not_pass_credentials(self):
        with patch('vault_access.request', return_value={'result': {}}) as native:
            invoke('lumen_vault_api_get', {'path': '/status'})
            native.assert_called_once_with({'path': '/status', 'operation': 'api_get'}, launch=False)
        with patch('vault_access.request', return_value={'result': {}}) as native:
            invoke('lumen_vault_mcp', {'operation': 'call', 'name': 'example', 'arguments': {}})
            native.assert_called_once_with({'operation': 'mcp_call', 'name': 'example', 'arguments': {}}, launch=False)

    def test_connection_selection_and_pagination_reach_native_boundary(self):
        cases = [
            ('lumen_vault_connection', {'offset': 20}, {'offset': 20, 'operation': 'connection'}),
            ('lumen_vault_api_get', {'reference': 'vault:example', 'path': '/status'}, {'reference': 'vault:example', 'path': '/status', 'operation': 'api_get'}),
            ('lumen_vault_mcp', {'reference': 'vault:example', 'operation': 'list'}, {'reference': 'vault:example', 'operation': 'mcp_tools'}),
            ('lumen_bookstack_read', {'reference': 'vault:example', 'operation': 'check'}, {'reference': 'vault:example', 'operation': 'check'}),
        ]
        for name, args, expected in cases:
            self.assertTrue(set(args).issubset(DEFINITIONS[name]['schema']['properties']))
            with patch('vault_access.request', return_value={}) as native:
                invoke(name, args)
                native.assert_called_once_with(expected, launch=False)

    def test_native_result(self):
        self.assertEqual(self.exercise(b'{"connected":true}\n'), {'connected': True})

    def test_unknown_error_is_not_echoed(self):
        with self.assertRaisesRegex(ValueError, '^Vault request failed.$'):
            self.exercise(b'{"error":"SYNTHETIC_DO_NOT_ECHO"}\n')

    def test_invalid_result(self):
        with self.assertRaisesRegex(ValueError, '^Invalid Vault response.$'):
            self.exercise(b'[]\n')

    def test_no_public_runtime(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, XDG_RUNTIME_DIR=directory):
            Path(directory).chmod(0o755)
            with self.assertRaisesRegex(ValueError, 'Private desktop'):
                request({'operation': 'check'})

    def test_symlink_endpoint_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, XDG_RUNTIME_DIR=directory):
            target = Path(directory)/'target'; target.touch()
            (Path(directory)/'lumen-vault-access').symlink_to(target)
            with self.assertRaisesRegex(ValueError, 'Private Vault endpoint'):
                request({'operation': 'check'})


if __name__ == '__main__':
    unittest.main()
