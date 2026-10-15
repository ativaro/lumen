from datetime import datetime,timezone
from pathlib import Path
import tempfile
import unittest
from lumen_store import Store
from wissen_data import Notebook
from notes_capture import daily,from_template,render_template


class CaptureTest(unittest.TestCase):
    def test_daily_reopen_preserves_edits_and_rejects_paths(self):
        with tempfile.TemporaryDirectory() as root:
            book=Notebook(Store(Path(root)/'state'),Path(root)/'notes',create=True)
            first=daily(book,'2026-10-13','Tasks')
            edited=book.write(first['path'],first['text']+'\nMy changes',first['hash'])
            again=daily(Notebook(book.store,book.root),'2026-10-13','Different template')
            self.assertEqual(again['hash'],edited['hash']);self.assertEqual(len(book.scan()['notes']),1)
            for day in ('../private','2026-02-30','20261013'):
                with self.subTest(day=day),self.assertRaises(ValueError):daily(book,day)
    def test_template_keeps_yaml_and_source_rejects_stale(self):
        with tempfile.TemporaryDirectory() as root:
            book=Notebook(Store(Path(root)/'state'),Path(root)/'notes',create=True)
            book.create_collection('Vorlagen')
            text='---\ntags: [project]\nunknown: keep\n---\n\n# {{title}}\n\nDate: {{date}}\n{{unknown}}'
            source=book.write('Vorlagen/Projekt.md',text,'')
            note=from_template(book,'New 🌍',source['path'],source['hash'])
            self.assertTrue(note['text'].startswith('---\ntags:'));self.assertIn('unknown: keep',note['text']);self.assertIn('# New 🌍',note['text'])
            self.assertEqual(note['text'].count('# New 🌍'),1);self.assertIn('{{unknown}}',note['text']);self.assertEqual(book.read(source['path'])['hash'],source['hash'])
            book.write(source['path'],text+'\nNew',source['hash'])
            with self.assertRaises(ValueError):from_template(book,'Other',source['path'],source['hash'])
    def test_template_substitution_is_single_pass_and_timezone_explicit(self):
        now=datetime(2026,10,13,23,59,tzinfo=timezone.utc)
        self.assertEqual(render_template('{{title}} {{date}} {{time}} {{danger()}}','{{date}}',now),'{{date}} 2026-10-13 23:59 {{danger()}}')
