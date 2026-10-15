import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QTableWidgetItem,QMessageBox
from PySide6.QtGui import QTextCursor
from notes_editor import NotesEditor
from notes_table import cells,table_at,markdown,TableEditor


class TablesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_escaped_pipe_alignment_and_code(self):
        source='Before\n\n| A | B |\n| :--- | ---: |\n| a\\|b | 🌍 |\n\nAfter'
        start,end,values,alignment=table_at(source,4)
        self.assertEqual(values,[['A','B'],['a|b','🌍']])
        self.assertEqual(markdown(values,alignment),source[start:end].rstrip('\n'))
        self.assertIsNone(table_at('```\n'+source+'\n```',5))
    def test_edit_is_single_undo_cancel_and_stale_guard(self):
        editor=NotesEditor();editor.setPlainText('Before\n\n| A | B |\n| --- | --- |\n| x | y |\n\nAfter');original=editor.toPlainText()
        cursor=editor.textCursor();cursor.setPosition(original.index('| x'));editor.setTextCursor(cursor)
        dialog=TableEditor(editor);dialog.grid.item(1,1).setText('🌍 | value');dialog.accept()
        self.assertIn('🌍 \\| value',editor.toPlainText());self.assertTrue(editor.toPlainText().endswith('After'))
        editor.undo();self.assertEqual(editor.toPlainText(),original)
        cancelled=TableEditor(editor);cancelled.add_row();cancelled.reject();self.assertEqual(editor.toPlainText(),original)
        stale=TableEditor(editor);editor.appendPlainText('Newer')
        with patch.object(QMessageBox,'warning') as warning:stale.accept();warning.assert_called_once()
        self.assertTrue(editor.toPlainText().endswith('Newer'))
        for widget in (dialog,cancelled,stale,editor):widget.deleteLater()

    def test_literal_pipes_after_backslashes_roundtrip(self):
        values=[['Header'],['a|b'],[r'a\|b'],[r'a\\|b']]
        text=markdown(values,['---'])
        self.assertEqual(table_at(text,0)[2],values)
