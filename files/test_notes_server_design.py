"""The server Notes layout on native widgets, using disposable notebook profiles."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QPalette, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from lumen_i18n import language


class ServerDesignTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def wait(self,check):
        for _ in range(600):
            QTest.qWait(20)
            if check():return
        self.fail('Notes design timed out')

    def test_layout_tags_save_table_and_two_isolated_profiles(self):
        from tools_wissen import Wissen
        from note_tags import tags
        from notes_design import summary
        for profile in ('A','B'):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as root, patch.dict(os.environ,{'LUMEN_DATA':root+'/state','XDG_CONFIG_HOME':root+'/config'}):
                w=Wissen(Path(root)/'tools');w.show()
                try:
                    self.wait(lambda:w.book and not w.job and not w.poller);w.poll_timer.stop()
                    self.assertFalse(w.notes)
                    note=w.book.create('Schreibprobe '+profile,'## Willkommen\n\nDirekt **formatiert** schreiben.\n\n- [ ] Prüfen\n\n| Aufgabe | Status |\n| --- | --- |\n| Entwurf | In Arbeit |')
                    w.book.create('Zweite Notiz','Anderer Inhalt');w.scanned(w.book.scan());w.show_note(note)
                    self.assertEqual(w.palette().color(QPalette.Window),self.app.palette().color(QPalette.Window))
                    self.assertNotIn('**',summary(note['text']));self.assertNotIn('**',w.rich_editor.toPlainText())
                    w.note_tags.input.setText('entwurf');QTest.keyClick(w.note_tags.input,Qt.Key_Return)
                    self.assertIn('entwurf',tags(w.document_text()));self.assertEqual(w.note_tags.input.text(),'')
                    self.assertFalse(w.source_mode.isChecked())
                    w.rich_editor.setTextCursor(w.rich_editor.document().find('Entwurf'))
                    self.assertTrue(w.table_tools.isVisible())
                    action=next(a for a in w.table_tools.actions() if a.data()=='add_column')
                    action.trigger();self.assertEqual(w.rich_editor.textCursor().currentTable().columns(),3)
                    if os.environ.get('LUMEN_NOTES_SCREENSHOTS'):
                        output=Path(os.environ['LUMEN_NOTES_SCREENSHOTS']);output.mkdir(parents=True,exist_ok=True)
                        QTest.qWait(60);w.grab().save(str(output/f'notes-{language()}-{profile}-table.png'))
                    w.rich_editor.moveCursor(QTextCursor.Start);self.assertFalse(w.table_tools.isVisible())
                    for width in (1440,1180,840,1440):
                        w.resize(width,960);QTest.qWait(60)
                        self.assertEqual(w._notes_compact,width<1100)
                        self.assertGreaterEqual(w.paragraph.width(),150)
                        self.assertTrue(w.editor_tools.widgetForAction(w.format_actions['bold']).isVisible())
                        self.assertGreater(w.rich_editor.height(),150)
                        self.assertGreater(w.editor_frame.mapTo(w,w.editor_frame.rect().topLeft()).y(),w.title.mapTo(w,w.title.rect().bottomLeft()).y())
                        if os.environ.get('LUMEN_NOTES_SCREENSHOTS'):
                            output=Path(os.environ['LUMEN_NOTES_SCREENSHOTS']);output.mkdir(parents=True,exist_ok=True)
                            w.grab().save(str(output/f'notes-{language()}-{profile}-{width}.png'))
                    before=w.document_text();QTest.mouseClick(w.save_note_button,Qt.LeftButton)
                    self.wait(lambda:not w.job and not w.dirty);self.assertEqual(w.book.read(note['path'])['text'],before)
                    w.show_note(w.book.read(note['path']));w.rich_editor.setTextCursor(w.rich_editor.document().find('Entwurf'))
                    self.assertEqual(w.rich_editor.textCursor().currentTable().columns(),3)
                    w.rich_editor.moveCursor(QTextCursor.End);w.rich_editor.insertPlainText(' ungespeichert')
                    w.conflict=True;w.save_note();self.assertTrue(w.recovery.isVisible());self.assertEqual(w.book.read(note['path'])['text'],before)
                    w.conflict=False;w.save_note();self.wait(lambda:not w.job and not w.dirty)
                finally:
                    self.wait(lambda:not w.job and not w.poller and not w.live_preview.job)
                    w.close();self.wait(lambda:not w.job);w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
