import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QListWidget
from note_tags import add_tag, tags, rename_tag
from lumen_i18n import tr


class DirectTagsTest(unittest.TestCase):
    def test_add_preserves_metadata_body_and_nested_tags(self):
        for text in ['---\ntags:\ncustom: yes\n---\n# Title', '# Title\n\nBody 🌍', '---\ncustom: {keep: true} # yes\ntags: [old/child]\n---\n# Title\nBody', '---\ncustom: yes\n---\n# Title']:
            result = add_tag(text, ' Neu/Idee ')
            self.assertIn('neu/idee', tags(result))
            self.assertTrue(result.endswith(text.split('---\n')[-1]))
            if 'custom:' in text: self.assertIn(next(line for line in text.splitlines() if line.startswith('custom:')), result)
            self.assertEqual(add_tag(result, 'NEU/IDEE'),result)
        self.assertEqual(tags(rename_tag('#parent #parent/child','parent','',descendants=False)),['parent/child'])

    def test_invalid_metadata_is_not_rewritten(self):
        for text in ['---\ntags: [broken\n---\n', '---\nother: &list [old]\ntags: *list\n---\n', '---\ntags: [old]\ntags: [other]\n---\n', '---\nunterminated', '---\n{custom: keep}\n---\n']:
            with self.subTest(text=text), self.assertRaises(ValueError): add_tag(text,'new')


class DirectNotesNativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def wait(self, check):
        for _ in range(600):
            QTest.qWait(20)
            if check(): return
        self.fail('Notes operation timed out')

    def test_direct_edit_tags_save_switch_and_empty_state(self):
        from tools_wissen import Wissen
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ,{'LUMEN_DATA':root+'/state'}):
            w=Wissen(Path(root)/'tools');w.resize(1180,800);w.show()
            try:
                self.wait(lambda:w.book and not w.job and not w.poller)
                w.poll_timer.stop()
                first=w.book.create('First','Grüße 🌍\n\n#parent #parent/child `#parent`')
                second=w.book.create('Second','#other')
                w.scanned(w.book.scan());w.show_note(first)
                self.assertEqual(w.split.count(),2)
                self.assertTrue(w.note_tags.isVisible())
                # This regression exercises the explicitly retained Markdown editor.
                w.source_mode.setChecked(True)
                w.editor.selectAll()
                QTest.mouseClick(w.editor_tools.widgetForAction(w.format_actions['bold']),Qt.LeftButton)
                self.assertTrue(w.editor.toPlainText().startswith('**Grüße 🌍'))
                QTest.mouseClick(w.editor_tools.widgetForAction(w.format_actions['bold']),Qt.LeftButton)
                self.assertTrue(w.editor.toPlainText().startswith('Grüße 🌍'))
                w.editor.undo();self.assertTrue(w.editor.toPlainText().startswith('**Grüße 🌍'))
                w.editor.undo();self.assertTrue(w.editor.toPlainText().startswith('Grüße 🌍'))
                cursor=w.editor.textCursor();cursor.movePosition(QTextCursor.Start);w.editor.setTextCursor(cursor)
                w.paragraph.setCurrentIndex(2);w.paragraph.activated.emit(2)
                self.assertTrue(w.editor.toPlainText().startswith('## Grüße'))
                w.paragraph.setCurrentIndex(1);w.paragraph.activated.emit(1)
                self.assertTrue(w.editor.toPlainText().startswith('# Grüße'))
                w.editor.undo();w.editor.undo()
                QTest.mouseClick(w.note_tags.add_button,Qt.LeftButton)
                picker=w.note_tags.picker
                field=picker.findChild(QLineEdit);field.setText('Wichtig');QTest.keyClick(field,Qt.Key_Return)
                self.assertIn('wichtig',tags(w.document_text()))
                self.assertNotIn('wichtig',w.editor.toPlainText())
                field.clear()
                choices=picker.findChild(QListWidget)
                item=next(choices.item(i) for i in range(choices.count()) if choices.item(i).data(Qt.UserRole)=='parent')
                item.setCheckState(Qt.Unchecked)
                self.assertNotIn('parent',tags(w.document_text()))
                self.assertIn('parent/child',tags(w.document_text()))
                self.assertIn('`#parent`',w.editor.toPlainText());picker.close()
                # A dirty note must finish saving before selection changes.
                w.open_note(second['path'])
                self.wait(lambda:w.doc and w.doc['path']==second['path'] and not w.job)
                saved=w.book.read(first['path'])
                self.assertIn('wichtig',saved['tags']);self.assertNotIn('parent',saved['tags'])
                w.show_note(saved);self.assertIn('wichtig',w.note_tags.values)
                before=w.document_text();body=w.editor.toPlainText()
                w.heading_prefix='---\ntags: [broken\n---\n'
                invalid=w.document_text()
                with self.assertRaises(ValueError):w.note_tags.change('new',True)
                self.assertEqual(w.document_text(),invalid)
                w.show_note(saved)
                # New metadata must not reset text undo history.
                w.editor.moveCursor(QTextCursor.End);w.editor.insertPlainText('pending')
                w.note_tags.change('later',True);w.editor.undo()
                self.assertFalse(w.editor.toPlainText().endswith('pending'))
                self.assertIn('later',tags(w.document_text()))
                w.save_note();self.wait(lambda:not w.job and not w.dirty)
                w.clear_note('Empty');self.assertFalse(w.note_tags.isEnabled());self.assertFalse(w.editor_tools.isEnabled())
                w.show_note(saved);self.assertTrue(w.editor_tools.isEnabled())
                w.tabs.setCurrentIndex(w.sources_tab);self.assertTrue(w.sidebar.isVisible())
                w.area_buttons['user'].click();self.assertEqual(w.tabs.currentIndex(),0)
            finally:
                self.wait(lambda:not w.job and not w.poller)
                w.close();self.wait(lambda:not w.job);w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
