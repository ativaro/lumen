import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextCursor
from PySide6.QtCore import QCoreApplication, QEvent, Qt

from tools_data import Library
import interop_sources as sources


class SourcesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'LUMEN_DATA': str(self.root/'lumen'), 'LUMEN_TOOLS_DATA': str(self.root/'tools')})
        self.env.start()
        self.addCleanup(self.env.stop)

    def window(self, cls):
        window = cls(self.root/'tools')
        def close():
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.addCleanup(close)
        return window

    def capture(self, window):
        from interop_data import validate_payload
        return validate_payload(sources.capture(window))

    def select(self, editor, start, end):
        cursor = editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        editor.setTextCursor(cursor)

    def test_files_capture_only_explicit_selection_and_bounds(self):
        path = self.root/'notes.md'
        path.write_text('not read by capture')
        hidden = self.root/'nested'
        hidden.mkdir()
        (hidden/'private.txt').write_text('unselected')
        value = sources.from_paths([path, hidden, path])
        self.assertEqual(value['paths'], [str(path), str(hidden)])
        self.assertEqual(value['text'], '')
        self.assertNotIn('private.txt', json.dumps(value))
        with self.assertRaises(ValueError): sources.from_paths([])
        with self.assertRaises(ValueError): sources.from_paths(['relative.md'])
        with self.assertRaises(ValueError): sources.from_paths([self.root/'missing'])

    def test_reader_quote_and_live_margin_note_exclude_document_copy(self):
        from tools_reader import Reader
        with patch.object(Reader, 'render_page'):
            window = self.window(Reader)
            asset = window.library.asset('book.txt')
            asset.write_text('first and second page')
            key = window.library.create('Book', asset=asset.name, name='book.txt', notes=[dict(id='note', page=2, text='saved quote', note='old note')], page=2, pages=3)
            window.current = key
            window.page_index = 2
            window.text.setPlainText('visible selection and other text')
            window.mode.setCurrentIndex(1)
            self.select(window.text, 0, 17)
            value = self.capture(window)
            self.assertEqual(value['text'], 'visible selection')
            self.assertEqual(value['paths'], [])
            self.assertEqual(value['source']['position'], dict(page=2, start=0, end=17, engine='lumen-1'))
            self.select(window.text, 0, 0)
            window.note_id = 'note'
            window.note.setPlainText('edited unsaved margin')
            value = self.capture(window)
            self.assertIn('edited unsaved margin', value['text'])
            self.assertEqual(value['source']['position']['note'], 'note')
            self.assertNotIn('first and second page', value['text'])







    def test_household_selected_document_excludes_other_attachments(self):
        from tools_household import Household
        window = self.window(Household)
        for name in ('receipt.pdf', 'private.pdf'):
            window.library.asset(name).write_bytes(name.encode())
        key = window.library.create('Device', kind='Gerät', attachments=[dict(asset='receipt.pdf', name='Receipt', text='selected OCR'), dict(asset='private.pdf', name='Private receipt', text='unselected')], notes='whole device notes', serial='private serial')
        window.focus_record(key)
        window.attachments.setCurrentRow(0)
        value = self.capture(window)
        self.assertEqual(value['paths'], [str(window.library.asset('receipt.pdf'))])
        self.assertEqual(value['text'], 'selected OCR')
        self.assertNotIn('private serial', json.dumps(value))
        self.assertNotIn('private.pdf', json.dumps(value))
        self.select(window.notes, 0, 5)
        value = self.capture(window)
        self.assertEqual(value['text'], 'whole')
        self.assertEqual(value['paths'], [])




    def test_vault_and_sound_capture_only_useful_settings(self):
        from tools_vault import Vault
        from tools_sound import Sound
        vault = self.window(Vault)
        key = vault.library.create('Backup', sources=[str(self.root)], repository='/secret/repository', password='secret-password')
        vault.focus_record(key)
        value = self.capture(vault)
        self.assertEqual(value['paths'], [])
        self.assertNotIn('secret', json.dumps(value))
        vault.sources.setCurrentRow(0)
        vault._interop_focus = vault.sources
        self.assertEqual(self.capture(vault)['paths'], [str(self.root)])
        with patch.object(Sound, 'poll'):
            sound = self.window(Sound)
        sound.timer.stop()
        sound.library.update(sound.current, rules={'reader': dict(title='Lumen Reader', volume=80, mute=False, sink='headphones', role='music')}, arbitrary_private='excluded')
        sound.load_rules()
        sound.rules.setCurrentItem(sound.rules.topLevelItem(0))
        value = self.capture(sound)
        self.assertEqual(value['items'][0]['title'], 'Lumen Reader')
        self.assertNotIn('arbitrary_private', json.dumps(value))

    def test_wissen_live_note_selection_and_collection_keep_notebook_locator(self):
        from tools_wissen import Wissen
        from wissen_data import Notebook
        with patch.object(Wissen, 'initialize'):
            window = self.window(Wissen)
            QCoreApplication.processEvents()
        window.poll_timer.stop()
        window.book = Notebook(window.store, self.root/'notebook', create=True)
        note = window.book.create('Selected note', 'Original notebook content #topic')
        other = window.book.create('Other note', 'Another topic #topic')
        window.notes = {value['path']: value for value in (note, other)}
        window.show_note(note)
        before = (window.book.root/note['path']).read_text()
        window.editor.setPlainText('Live unsaved words\nUnselected remainder')
        self.select(window.editor, 0, 18)
        window.draft_timer.stop()
        window.autosave_timer.stop()
        value = self.capture(window)
        self.assertEqual(value['text'], 'Live unsaved words')
        self.assertEqual(value['paths'], [])
        self.assertEqual(value['source']['locator']['root'], str(window.book.root))
        self.assertEqual((window.book.root/note['path']).read_text(), before)
        window._interop_focus = window.collections
        value = self.capture(window)
        self.assertEqual(value['source']['kind'], 'collection')
        self.assertEqual(set(value['paths']), {str(window.book.root/value['path']) for value in (note, other)})
        window.dirty = False

    def test_every_payload_passes_registry_bounds_and_roundtrips_reference(self):
        from interop_data import Registry, validate_payload
        path = self.root/'selected.txt'
        path.write_text('content')
        value = sources.from_paths([path])
        self.assertEqual(validate_payload(value), value)
        registry = Registry(self.root/'tools')
        ref = dict(app='reader', kind='record', id='book', title='Book', position=dict(page=4, start=5, end=9))
        self.assertEqual(registry.resolve(registry.register(ref)), ref)
        with self.assertRaises(ValueError):
            sources._bounded(dict(value, text='a' * 120001))
        with self.assertRaises(ValueError):
            sources._bounded(dict(value, items=[{}] * 1001))


if __name__ == '__main__':
    unittest.main()
