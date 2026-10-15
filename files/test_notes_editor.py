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

    def test_bold_and_italic_can_be_combined_and_toggled(self):
        self.text('Grüße 🌍'); self.editor.selectAll()
        self.editor.wrap('**'); self.editor.wrap('*')
        self.assertEqual(self.editor.toPlainText(), '***Grüße 🌍***')
        self.editor.wrap('*')
        self.assertEqual(self.editor.toPlainText(), '**Grüße 🌍**')
        self.editor.wrap('**')
        self.assertEqual(self.editor.toPlainText(), 'Grüße 🌍')

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

    def test_source_mode_still_avoids_list_continuation_in_code(self):
        self.editor.set_source_mode(True)
        self.text('```\n- code')
        QTest.keyClick(self.editor, Qt.Key_Return)
        self.assertEqual(self.editor.toPlainText(), '```\n- code\n')

    def test_switcher_disambiguates_duplicate_titles_by_path(self):
        from notes_switcher import NoteSwitcher
        dialog = NoteSwitcher([dict(title='Plan', path='Haus/Plan.md'), dict(title='Plan', path='Work/Plan.md')])
        self.addCleanup(dialog.deleteLater)
        dialog.search.setText('haus plan')
        self.assertEqual(dialog.rows.count(), 1)
        dialog.choose()
        self.assertEqual(dialog.path, 'Haus/Plan.md')

    def test_link_completion_preserves_unicode_prefix_and_existing_closer(self):
        self.editor.completion.notes=lambda:[dict(title='Plan', path='Haus/Plan.md', tags=['projekt/haus'])]
        self.editor.completion.origin=lambda:'Haus/Ideen.md'
        self.text('🌍 [[Pl]]')
        cursor=self.editor.textCursor();cursor.movePosition(QTextCursor.PreviousCharacter, QTextCursor.MoveAnchor, 2)
        self.editor.setTextCursor(cursor)
        self.editor.completion.refresh()
        self.editor.completion.choose('Plan · Haus/Plan.md')
        self.assertEqual(self.editor.toPlainText(), '🌍 [[Plan.md]]')
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), '🌍 [[Pl]]')

    def test_nested_tag_completion_and_stale_choice(self):
        self.editor.completion.notes=lambda:[dict(title='Plan', path='Plan.md', tags=['projekt/haus'])]
        self.text('🌍 #pro')
        self.editor.completion.refresh()
        self.editor.completion.choose('#projekt/haus')
        self.assertEqual(self.editor.toPlainText(), '🌍 #projekt/haus')
        self.text('#pro');self.editor.completion.refresh();self.text('Different note')
        self.editor.completion.choose('#projekt/haus')
        self.assertEqual(self.editor.toPlainText(), 'Different note')

    def test_completion_can_be_selected_with_keyboard(self):
        self.editor.completion.notes=lambda:[dict(title='Plan', path='Plan.md', tags=['projekt/haus'])]
        self.editor.show();self.editor.setFocus()
        QTest.keyClicks(self.editor, '#pro')
        self.assertTrue(self.editor.completion.popup.popup().isVisible())
        QTest.keyClick(self.editor.completion.popup.popup(), Qt.Key_Down)
        QTest.keyClick(self.editor.completion.popup.popup(), Qt.Key_Return)
        self.assertEqual(self.editor.toPlainText(), '#projekt/haus')
        self.editor.hide()
