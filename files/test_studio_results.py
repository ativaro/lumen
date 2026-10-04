"""Presentation contracts: explicit completed tools only, no prose extraction."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from studio_results import present, from_messages


class ResultTest(unittest.TestCase):
    def test_valid_files_clear_and_invalid_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp)/'日本語.png'; file.write_bytes(b'fixture')
            fifo = Path(tmp)/'pipe'; os.mkfifo(fifo)
            result = present([str(file), str(file)], 'Bilder / Images / 画像')
            self.assertEqual(result['paths'], [str(file)])
            self.assertEqual(present([])['paths'], [])
            for paths in ([tmp], [str(fifo)], [tmp+'/missing'], ['relative.png'],
                          ['https://example.com/a.png'], ['/bad\0path'], [str(file)]*101):
                with self.subTest(paths=paths), self.assertRaises(ValueError): present(paths)

    def test_only_successful_tool_output_is_presented(self):
        result = present([])
        part = dict(type='tool', tool='cachyos_lumen_present_files',
                    state=dict(status='completed', output=json.dumps(result)))
        message = dict(info=dict(role='assistant'), parts=[part])
        self.assertEqual(from_messages([message]), result)
        for changed in (dict(part, tool='bash'), dict(type='text', text=json.dumps(result)),
                        dict(part, state=dict(status='running', output=json.dumps(result))),
                        dict(part, state=dict(status='completed', output='Fehler: no file')),
                        dict(part, state=dict(status='completed', output=json.dumps(dict(result, paths=['https://invalid']))))):
            self.assertIsNone(from_messages([dict(message, parts=[changed])]))
        self.assertIsNone(from_messages([dict(message, info=dict(role='user'))]))
        newer = dict(result, id='new-result')
        next_message = dict(message, parts=[dict(part, state=dict(status='completed', output=json.dumps(newer)))])
        self.assertEqual(from_messages([message, next_message]), newer)


if __name__ == '__main__': unittest.main()
