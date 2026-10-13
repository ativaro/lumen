"""Synthetic native Vault transport tests, no credentials or real vault access."""
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from vault_access import _exchange as request, request as prepared_request, VaultError, INSTRUCTION
from lumen_mcp_tools import DEFINITIONS, invoke


class VaultAccessTest(unittest.TestCase):
    def test_unlock_precedes_exact_action_and_cancel_never_dispatches(self):
        args = {"operation": "api_request", "method": "POST", "path": "/item", "body": {"name": "fixture"}}
        with patch("vault_access._exchange", side_effect=[{"unlocked": True}, {"http_status": 201}]) as exchange:
            self.assertEqual(prepared_request(args), {"http_status": 201})
            self.assertEqual([c.args[0] for c in exchange.call_args_list], [{"operation": "unlock"}, args])
            self.assertTrue(exchange.call_args_list[0].kwargs["launch"])
        with patch("vault_access._exchange", side_effect=VaultError("access_denied")) as exchange:
            with self.assertRaises(VaultError): prepared_request(args)
            self.assertEqual(exchange.call_count, 1)
        with patch("vault_access._exchange", side_effect=[{"unlocked": True}, ValueError("unknown")]) as exchange:
            with self.assertRaisesRegex(ValueError, "unknown"): prepared_request(args)
            self.assertEqual(exchange.call_count, 2)

    def test_secret_parameters_are_not_in_tool_contract(self):
        self.assertEqual(set(DEFINITIONS['lumen_vault_store']['schema']['properties']), {'title', 'kind'})
        self.assertFalse(DEFINITIONS['lumen_vault_store']['schema']['additionalProperties'])
        self.assertTrue(DEFINITIONS['lumen_vault_store']['action'])
        self.assertIn('Secrets already stored in Vault remain non-exportable', INSTRUCTION)
        self.assertIn('Providing a password or token for use is not a request to save it.', INSTRUCTION)
        self.assertNotIn('Credentials belong in Lumen Vault, never', INSTRUCTION)
        self.assertIn('then continue the requested task in the same turn', INSTRUCTION)
        self.assertIn("set a named user's password", INSTRUCTION)
        self.assertNotIn('token', DEFINITIONS['lumen_bookstack_read']['schema']['properties'])

    def test_adapter_never_supplies_credentials(self):
        with patch('vault_access.request', return_value={'saved': True, 'reference': 'vault:public-id'}) as native:
            result = invoke('lumen_vault_store', {'title': 'Documentation', 'kind': 'token'})
        native.assert_called_once_with({'operation': 'store', 'title': 'Documentation', 'kind': 'token'}, launch=True)
        self.assertEqual(result, {'saved': True, 'reference': 'vault:public-id'})

    def exercise(self, response, operation="check", **arguments):
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
                result = request(dict(arguments, operation=operation))
            finally:
                thread.join(timeout=2)
            self.assertEqual(received, [dict(arguments, operation=operation)])
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

    def test_api_write_adapter_and_unknown_transport_results(self):
        args = {'method': 'PATCH', 'reference': 'vault:example', 'path': '/pages/7', 'body': [{'op': 'replace', 'path': '/name', 'value': 'Changed'}]}
        with patch('vault_access.request', return_value={'http_status': 200}) as native:
            invoke('lumen_vault_api_request', args)
            native.assert_called_once_with(dict(args, operation='api_request'), launch=False)
        for method in ('POST','PUT','PATCH','DELETE'):
            for response in (b'', b'[]\n', b'invalid\n'):
                with self.subTest(method=method, response=response), self.assertRaisesRegex(ValueError, 'outcome is unknown'):
                    self.exercise(response, operation='api_request', method=method)
        with self.assertRaisesRegex(ValueError, 'declined'):
            self.exercise(b'{"error":"access_denied"}\n', operation='api_request', method='DELETE')

    def test_api_body_is_bounded_before_connecting(self):
        with patch('vault_access.socket.socket') as socket_factory:
            for body in ('text', None, True, {'text': 'x'*32768}):
                with self.assertRaises(ValueError): request({'operation':'api_request','method':'POST','body':body})
            for method in ('GET','DELETE'):
                with self.assertRaises(ValueError): request({'operation':'api_request','method':method,'body':{}})
            socket_factory.assert_not_called()

    def test_web_tools_route_without_credentials(self):
        for suffix in ('open', 'inspect', 'login', 'click', 'fill', 'close'):
            name = 'lumen_vault_web_' + suffix
            props = DEFINITIONS[name]['schema']['properties']
            self.assertFalse({'password','username','url','script','selector'} & set(props))
            args = {'reference':'vault:example'} if suffix == 'open' else {'session':'opaque'}
            with patch('vault_access.request', return_value={}) as native:
                invoke(name, args)
                native.assert_called_once_with(dict(args, operation='web_'+suffix), launch=False)
        for op in ('web_login','web_click','web_fill'):
            with self.subTest(op=op), self.assertRaisesRegex(ValueError, 'outcome is unknown'):
                self.exercise(b'', operation=op)

    def test_general_http_routes_and_unknown_outcome(self):
        for op in ('open','request','close'):
            args = {'reference':'vault:example'} if op == 'open' else {'session':'native-session'}
            if op == 'open': args['requests'] = [dict(method='POST',path='/session',body={'secret':{'$vault':'password'}}),dict(method='GET',path='/status')]
            if op == 'request': args.update(method='POST',path='/rpc',body={'params':{'password':{'$vault':'password'}}})
            name = 'lumen_vault_http_' + op
            self.assertFalse({'password','username','url','headers','script'} & set(DEFINITIONS[name]['schema']['properties']))
            self.assertTrue(DEFINITIONS[name]['native_confirmation'])
            with patch('vault_access.request',return_value={}) as native:
                invoke(name,args)
                native.assert_called_once_with(dict(args,operation='http_'+op),launch=False)
        with self.assertRaisesRegex(ValueError,'outcome is unknown'):
            self.exercise(b'',operation='http_request')

    def test_ssh_contract_and_uncertain_result(self):
        for operation in ('check','exec'):
            name = 'lumen_vault_ssh_' + operation
            args = {'reference':'vault:example', 'port':2222}
            if operation == 'exec': args['command'] = 'uname -a'
            self.assertEqual(set(DEFINITIONS[name]['schema']['properties']), set(args))
            self.assertTrue(DEFINITIONS[name]['native_confirmation'])
            with patch('vault_access.request', return_value={}) as native:
                invoke(name, args)
                native.assert_called_once_with(dict(args, operation='ssh_'+operation), launch=False)
        with self.assertRaisesRegex(ValueError, 'outcome is unknown'):
            self.exercise(b'', operation='ssh_exec')

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
