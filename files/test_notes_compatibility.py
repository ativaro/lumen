import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from lumen_store import Store
from wissen_data import Notebook
from notes_query import resolve_link


class NotesCompatibilityTest(unittest.TestCase):
    def test_external_markdown_roundtrip_and_ambiguous_titles(self):
        corpus = json.loads(Path(__file__).with_name('notes_compatibility.json').read_text())
        with tempfile.TemporaryDirectory() as root:
            book = Notebook(Store(Path(root)/'state'), Path(root)/'notes', create=True)
            for item in corpus:
                file = book.root/item['path']; file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(item['text'].encode())
            before = {item['path']: hashlib.sha256((book.root/item['path']).read_bytes()).hexdigest() for item in corpus}
            notes = {note['path']: note for note in book.scan()['notes']}
            self.assertEqual(set(notes), set(before))
            for item in corpus:
                note = notes[item['path']]
                self.assertEqual(note['text'], item['text'])
                self.assertEqual(note['tags'], item['bodyTags'])
                book.write(note['path'], note['text'], note['hash'])
                self.assertEqual(hashlib.sha256((book.root/note['path']).read_bytes()).hexdigest(), before[note['path']])
            self.assertEqual(resolve_link('Haus/Überblick.md', 'Plan|Bauplan', notes), 'Haus/Plan.md')
            self.assertIsNone(resolve_link('Ohne-Titel.md', 'Plan', notes))
            self.assertIsNone(resolve_link('Haus/Plan.md', 'Fehlt', notes))

    def test_external_change_never_replaced_by_stale_editor(self):
        with tempfile.TemporaryDirectory() as root:
            book = Notebook(Store(Path(root)/'state'), Path(root)/'notes', create=True)
            note = book.create('Original', 'Body')
            external = '# Other editor\n\nPreserve\n'
            (book.root/note['path']).write_text(external)
            with self.assertRaisesRegex(ValueError, 'CONFLICT'):
                book.write(note['path'], 'Stale local draft', note['hash'])
            self.assertEqual((book.root/note['path']).read_text(), external)
