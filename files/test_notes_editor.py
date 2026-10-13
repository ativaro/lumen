import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from notes_editor import NotesEditor


class NotesEditorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor = NotesEditor()
        self.addCleanup(self.editor.deleteLater)

    def text(self, value):
        self.editor.setPlainText(value)
        self.editor.moveCursor(QTextCursor.End)

    def test_formatting_preserves_unicode_and_is_one_undo(self):
        self.text('Grüße 🌍')
        self.editor.selectAll()
        self.editor.wrap('**')
        self.assertEqual(self.editor.toPlainText(), '**Grüße 🌍**')
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), 'Grüße 🌍')

    def test_continue_list_and_leave_empty_item(self):
        for before, after in [('- first', '- first\n- '),
                              ('  - [x] Done', '  - [x] Done\n  - [ ] '),
                              ('9. Item', '9. Item\n10. '),
                              ('- ', '')]:
            with self.subTest(before=before):
                self.text(before)
                QTest.keyClick(self.editor, Qt.Key_Return)
                self.assertEqual(self.editor.toPlainText(), after)

    def test_no_list_continuation_in_fenced_code_or_middle(self):
        for before in ['```md\n- example', '~~~\n1. example']:
            self.text(before)
            QTest.keyClick(self.editor, Qt.Key_Return)
            self.assertEqual(self.editor.toPlainText(), before+'\n')
        self.text('- first')
        self.editor.moveCursor(QTextCursor.Start)
        QTest.keyClick(self.editor, Qt.Key_Return)
        self.assertEqual(self.editor.toPlainText(), '\n- first')

    def test_multiline_list_action_does_not_edit_next_unselected_line(self):
        self.text('first\nsecond\nkeep')
        cursor = self.editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(len('first\nsecond\n'), QTextCursor.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.prefix_lines('- ')
        self.assertEqual(self.editor.toPlainText(), '- first\n- second\nkeep')
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), 'first\nsecond\nkeep')

    def test_checkbox_toggle_preserves_indentation_and_text(self):
        self.text('  - [ ] Grüße 🌍')
        self.editor.toggle_checkbox()
        self.assertEqual(self.editor.toPlainText(), '  - [x] Grüße 🌍')
        self.editor.toggle_checkbox()
        self.assertEqual(self.editor.toPlainText(), '  - [ ] Grüße 🌍')

    def test_source_switch_does_not_change_content_or_undo(self):
        self.text('# Title\n**Text**')
        self.editor.insertPlainText('!')
        self.editor.set_source_mode(True)
        self.editor.set_source_mode(False)
        self.assertEqual(self.editor.toPlainText(), '# Title\n**Text**!')
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), '# Title\n**Text**')
