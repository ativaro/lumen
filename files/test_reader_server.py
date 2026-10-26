import unittest
from reader_server import reading_html


class SharedReaderTests(unittest.TestCase):
    def test_untrusted_office_text_is_escaped_and_source_location_survives(self):
        text='Budget!A1: <script>alert(1)</script>'
        html=reading_html(dict(text=text,blocks=[dict(start=0,end=len(text),location=dict(sheet='Budget'))]),0)
        self.assertIn('Tabellenblatt Budget',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertNotIn('<script>',html)
