"""Drive tool discovery and transport; no personal profile or network access."""
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from uuid import uuid4

from lumen_mcp_tools import DEFINITIONS, invoke
from test_mcp import mcp


class DriveMCPTest(unittest.TestCase):
    def test_registered_read_only_and_uses_paired_transport(self):
        self.assertNotIn('lumen_drive_spaces', mcp.TOOLS)
        for name in ('lumen_drive_search',):
            self.assertIn(name, mcp.TOOLS)
            self.assertTrue(DEFINITIONS[name]['annotations']['readOnlyHint'])
            self.assertFalse(DEFINITIONS[name]['action'])
        with patch('lumen_connect.read_config', return_value={'server':'https://staging.invalid','token':'fixture'}) as config, patch('lumen_connect.request', return_value=[{'name':'Report.pdf'}]) as request:
            self.assertEqual(invoke('lumen_drive_search', {'query':'Öl & 100%_','offset':50}), [{'name':'Report.pdf'}])
            request.assert_called_once_with(config.return_value, '/bridge/drive/search?query=%C3%96l+%26+100%25_&offset=50')
            request.reset_mock()
            invoke('lumen_drive_search', {})
            request.assert_called_once_with(config.return_value, '/bridge/drive/search?query=&offset=0')
            request.side_effect=HTTPError('https://staging.invalid',403,'Forbidden',{},None)
            with self.assertRaises(HTTPError): invoke('lumen_drive_search', {})
        with patch('lumen_connect.read_config', side_effect=FileNotFoundError):
            with self.assertRaisesRegex(ValueError, 'Server-Verbindung'): invoke('lumen_drive_search', {})

    def test_rejects_identity_override_and_unbounded_inputs(self):
        for args in ({'query':'x'*201}, {'offset':-1}, {'offset':5001}, {'server':'https://other.invalid'}, {'token':'x'}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                mcp.validate_schema(args, DEFINITIONS['lumen_drive_search']['schema'])
        with self.assertRaises(ValueError):
            mcp.validate_schema({'workspace': str(uuid4())}, DEFINITIONS['lumen_drive_search']['schema'])



if __name__ == '__main__':
    unittest.main()
