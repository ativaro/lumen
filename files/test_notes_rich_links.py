"""Mixed-link regressions for the rendered editor's Markdown serialization."""
import unittest
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextCursor, QTextCharFormat
from notes_editor import NotesEditor
from notes_rich_editor import RichEditor
from notes_rich_codec import Codec, SafeDocument, markdown


class RichLinksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_edited_paragraph_preserves_each_link(self):
        for source in ('[A](a) [[B]]', '[A](a) and [[B|C]]',
                       '[A](a) [[B|Grüße 🌍]] [[D|Ende]]',
                       '[A](a) [Text](b) [[B|C]]'):
            with self.subTest(source=source):
                codec = Codec(source); document = SafeDocument()
                document.setMarkdown(codec.rendered)
                cursor = QTextCursor(document); cursor.insertText('X', QTextCharFormat())
                encoded = codec.encode(document)
                self.assertIn('[A](a)', encoded)
                for raw, target, label in codec.wiki.values():
                    self.assertIn(raw, encoded)
                self.assertNotIn('lumen-wiki:', encoded)

    def test_underlined_text_does_not_capture_preceding_link(self):
        for label in ('B', 'C [D]', r'C \ D'):
            with self.subTest(label=label):
                document = SafeDocument(); document.setMarkdown('[A](a) ' + label)
                cursor = document.find(label)
                fmt = QTextCharFormat(); fmt.setFontUnderline(True); cursor.mergeCharFormat(fmt)
                encoded = markdown(document)
                self.assertIn('[A](a)', encoded)
                self.assertIn('<u>', encoded)
                self.assertNotIn('lumen-underline:', encoded)
                restored = SafeDocument(); restored.setMarkdown(encoded)
                self.assertEqual(restored.toPlainText(), document.toPlainText())

    def test_native_source_update_and_undo_keep_links_separate(self):
        source = NotesEditor(); source.setPlainText('[A](a) [[B|C]]')
        rich = RichEditor(SimpleNamespace(editor=source, book=None, doc=None))
        try:
            cursor = rich.textCursor(); cursor.setPosition(0)
            cursor.insertText('X', QTextCharFormat())
            self.assertEqual(source.toPlainText(), 'X[A](a) [[B|C]]')
            rich.undo(); self.assertEqual(source.toPlainText(), '[A](a) [[B|C]]')
            rich.redo(); self.assertEqual(source.toPlainText(), 'X[A](a) [[B|C]]')
        finally:
            rich.deleteLater(); source.deleteLater()
