import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from notes_editor import NotesEditor
from notes_rich_editor import RichEditor
from notes_table import table_at


class RichTableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def test_table_menu_operations_roundtrip_undo_and_guards(self):
        original = '| A | B |\n| --- | --- |\n| one | two |\n| three | four |\n\nTail'
        source = NotesEditor(); source.setPlainText(original)
        rich = RichEditor(SimpleNamespace(editor=source, book=None, doc=None))
        self.addCleanup(rich.deleteLater); self.addCleanup(source.deleteLater)
        def select(text): rich.setTextCursor(rich.document().find(text))
        def action(key):
            rich.update_table_menu()
            return next(a for a in rich.table_menu.actions() if a.data() == key)
        select('one')
        self.assertFalse(action('insert').isEnabled())
        action('add_row').trigger()
        table = rich.textCursor().currentTable()
        self.assertEqual(table.rows(), 4)
        self.assertEqual(table.cellAt(3, 0).firstCursorPosition().block().text(), 'three')
        rich.undo(); self.assertEqual(source.toPlainText(), original)
        rich.redo(); self.assertEqual(rich.textCursor().currentTable().rows(), 4)
        select('one'); action('add_column').trigger()
        self.assertEqual(rich.textCursor().currentTable().columns(), 3)
        line = next(i for i, line in enumerate(source.toPlainText().splitlines()) if line.startswith('|'))
        self.assertEqual(table_at(source.toPlainText(), line)[2][1], ['one', '', 'two'])
        rich.load_source(); select('one')
        self.assertEqual(rich.textCursor().currentTable().columns(), 3)
        rich.setTextCursor(rich.textCursor().currentTable().cellAt(1,1).firstCursorPosition())
        action('remove_column').trigger()
        self.assertEqual(rich.textCursor().currentTable().columns(), 2)
        select('three'); action('remove_row').trigger()
        self.assertNotIn('three', source.toPlainText()); self.assertIn('Tail', source.toPlainText())
        select('A'); self.assertFalse(action('remove_row').isEnabled())
        select('one'); action('remove_row').trigger()
        self.assertFalse(action('remove_row').isEnabled())
        action('remove_column').trigger()
        self.assertFalse(action('remove_column').isEnabled())
        before = source.toPlainText()
        for readonly, enabled in [(True, True), (False, False)]:
            rich.setReadOnly(readonly); rich.setEnabled(enabled)
            for key in ('insert', 'add_row', 'remove_row', 'add_column', 'remove_column', 'remove_table'):
                self.assertFalse(action(key).isEnabled())
            rich.change_table('add_row'); rich.insert_table()
            self.assertEqual(source.toPlainText(), before)
        rich.setReadOnly(False); rich.setEnabled(True); select('Tail')
        self.assertTrue(action('insert').isEnabled())
        self.assertFalse(action('add_row').isEnabled())
        rich.setTextCursor(rich.document().rootFrame().childFrames()[0].firstCursorPosition())
        before=source.toPlainText();action('remove_table').trigger()
        self.assertIsNone(rich.textCursor().currentTable());self.assertIn('Tail',source.toPlainText())
        rich.undo();self.assertEqual(source.toPlainText(),before)

    def test_empty_columns_and_literal_code_roundtrip(self):
        from notes_rich_codec import Codec, SafeDocument, markdown
        original='```\n|A||\n|---||\n|one||\n```\n\n| A | B |\n| --- | --- |\n| one | two |'
        codec=Codec(original);doc=SafeDocument();doc.setMarkdown(codec.rendered)
        table=doc.find('two').currentTable();table.insertColumns(1,1)
        encoded=codec.encode(doc)
        self.assertIn('```\n|A||\n|---||\n|one||\n```',encoded)
        reopened=SafeDocument();reopened.setMarkdown(Codec(encoded).rendered)
        self.assertEqual(reopened.find('two').currentTable().columns(),3)
        cursor=QTextCursor(reopened);cursor.movePosition(QTextCursor.End);cursor.insertBlock()
        empty=cursor.insertTable(2,2);fmt=empty.format();fmt.setHeaderRowCount(1);empty.setFormat(fmt)
        result=markdown(reopened);again=SafeDocument();again.setMarkdown(Codec(result).rendered)
        tables=again.rootFrame().childFrames()
        self.assertEqual(len(tables),2);self.assertEqual(tables[-1].columns(),2)
        self.assertNotIn('lumen-empty-',result)

    def wait(self, check):
        for _ in range(600):
            QTest.qWait(20)
            if check(): return
        self.fail('Notes table timed out')
