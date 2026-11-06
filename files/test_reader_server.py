import unittest
from reader_server import reading_html
from reader_server import read_file
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile
import os


class SharedReaderTests(unittest.TestCase):
    def test_untrusted_office_text_is_escaped_and_source_location_survives(self):
        text='Budget!A1: <script>alert(1)</script>'
        html=reading_html(dict(text=text,blocks=[dict(start=0,end=len(text),location=dict(sheet='Budget'))]),0)
        self.assertIn('Tabellenblatt Budget',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertNotIn('<script>',html)

    def test_named_pipe_is_rejected_before_network_or_blocking_read(self):
        config=dict(server='https://lumen.invalid',token='synthetic')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'pipe.docx';os.mkfifo(path)
            with patch('lumen_connect.read_config',return_value=config),patch('drive_http.Session') as transport:
                with self.assertRaisesRegex(ValueError,'reguläre'):read_file(path,0,Mock(),config)
                transport.assert_not_called()

    def test_server_change_never_transmits_a_previously_opened_document(self):
        with patch('lumen_connect.read_config',return_value=dict(server='https://other.invalid',token='new')):
            with self.assertRaisesRegex(ValueError,'Serververbindung'):
                read_file('/nonexistent.docx',0,Mock(),dict(server='https://lumen.invalid',token='old'))

    def test_drive_original_opens_reference_without_downloading_and_uploading_again(self):
        from drive_browser import Browser
        path='lumen-drive:/synthetic';browser=Mock()
        browser.entries={path:('file',dict(name='Report.docx'))}
        Browser.open(browser,path)
        browser.server_tools.assert_called_once_with([path],reader=True)
        browser.fetch.assert_not_called()
