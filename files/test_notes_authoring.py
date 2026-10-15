import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt,QTimer,QEvent,QUrl
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QTableWidgetItem


class AuthoringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def wait(self,check):
        for _ in range(600):
            QTest.qWait(20)
            if check():return
        self.fail('Native authoring timed out')
    def test_live_render_table_heading_links_and_completion(self):
        from tools_wissen import Wissen
        from notes_table import TableEditor
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'LUMEN_DATA':root+'/state','XDG_CONFIG_HOME':root+'/config'}):
            w=Wissen(Path(root)/'tools');w.resize(1240,900);w.show()
            try:
                self.wait(lambda:w.book and not w.job and not w.poller);w.poll_timer.stop()
                first=w.book.create('First','Start\n\n[[Second#Details|Weiter]]')
                second=w.book.create('Second','## Details\n\nA paragraph 🌍 ^target\n\nMore')
                w.scanned(w.book.scan());w.show_note(first);w.live_action.setChecked(True)
                self.wait(lambda:'Weiter' in w.live_preview.preview.toPlainText())
                original=w.editor.toPlainText();w.editor.moveCursor(QTextCursor.End);w.editor.insertPlainText('\n\n**Live changed**')
                self.wait(lambda:'Live changed' in w.live_preview.preview.toPlainText());w.editor.undo()
                self.wait(lambda:'Live changed' not in w.live_preview.preview.toPlainText());self.assertEqual(w.editor.toPlainText(),original)
                # The preview preserves a heading target when following a rendered link.
                w.live_preview.preview.follow(QUrl('lumen-note:/'+second['path']+'#Details'))
                self.wait(lambda:w.doc['path']==second['path'] and not w.job)
                self.assertTrue(w.editor.textCursor().block().text().startswith('## Details'))
                w.open_note_target(second['path'],'^target');self.assertIn('A paragraph',w.editor.textCursor().block().text())
                with self.assertRaises(ValueError):w.open_note_target(second['path'],'^missing')
                w.editor.moveCursor(QTextCursor.End);w.editor.insertPlainText('\n\n## Unsaved heading\n\n[[#Uns')
                w.editor.completion.refresh();self.assertIn('Unsaved heading',w.editor.completion.items)
                w.editor.undo()
                w.editor.insertPlainText('\n\n[[#Det')
                w.editor.completion.refresh();self.assertIn('Details',w.editor.completion.items)
                w.editor.completion.choose('Details');self.assertTrue(w.editor.toPlainText().endswith('[[#Details]]'))
                w.editor.moveCursor(QTextCursor.PreviousCharacter);QTest.keyClick(w.editor,Qt.Key_Return,Qt.ControlModifier)
                self.assertTrue(w.editor.textCursor().block().text().startswith('## Details'))
                w.editor.moveCursor(QTextCursor.End);w.editor.insertPlainText('\n\n')
                failures=[]
                def table():
                    dialog=QApplication.activeModalWidget()
                    try:
                        self.assertIsInstance(dialog,TableEditor);dialog.grid.item(0,0).setText('Name');dialog.grid.item(1,0).setText('Grüße 🌍');dialog.accept()
                    except Exception as error:
                        failures.append(str(error));dialog.reject()
                QTimer.singleShot(60,table);w.table_action.trigger();self.assertFalse(failures,failures)
                self.assertIn('| Grüße 🌍 |',w.editor.toPlainText())
                self.wait(lambda:'Grüße 🌍' in w.live_preview.preview.toPlainText())
                before=w.document_text();w.save_note();self.wait(lambda:not w.job and not w.dirty)
                self.assertEqual(w.book.read(second['path'])['text'],before)
                w.editor.undo();self.assertNotIn('| Grüße 🌍 |',w.editor.toPlainText())
                w.save_note();self.wait(lambda:not w.job and not w.dirty)
                w.live_action.setChecked(False);self.assertFalse(w.live_preview.preview.isVisible())
            finally:
                self.wait(lambda:not w.job and not w.poller and not w.live_preview.job)
                w.close();self.wait(lambda:not w.job);w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_local_image_worker_and_remote_resource_denied(self):
        from tools_wissen import Wissen
        from PySide6.QtGui import QTextDocument
        from PIL import Image
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'LUMEN_DATA':root+'/state','XDG_CONFIG_HOME':root+'/config'}):
            w=Wissen(Path(root)/'tools');w.show()
            try:
                self.wait(lambda:w.book and not w.job and not w.poller);w.poll_timer.stop()
                image=Path(root)/'sample.png';Image.new('RGB',(8,8),'red').save(image)
                path=w.book.add_image(image)
                note=w.book.create('Picture','![local]('+path+')\n![remote](https://example.invalid/private.png)')
                w.scanned(w.book.scan());w.show_note(note);w.live_action.setChecked(True)
                self.wait(lambda:path in w.live_preview.images and not w.live_preview.job)
                self.assertIsNone(w.live_preview.preview.loadResource(QTextDocument.ImageResource,QUrl('https://example.invalid/private.png')))
                self.assertIsNone(w.live_preview.preview.loadResource(QTextDocument.ImageResource,QUrl.fromLocalFile('/etc/passwd')))
                self.assertNotIn('tags:',w.live_preview.preview.toPlainText())
                w.live_preview.image_key=None;w.live_preview.refresh()
                self.assertIsNotNone(w.live_preview.job)
                w.close();self.wait(lambda:not w.isVisible() and not w.live_preview.job)
            finally:
                self.wait(lambda:not w.job and not w.poller and not w.live_preview.job)
                w.close();self.wait(lambda:not w.job);w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_daily_button_and_template_dialog_use_current_notebook(self):
        from tools_wissen import Wissen
        from notes_capture import choose_template
        from PySide6.QtWidgets import QInputDialog
        from lumen_i18n import tr
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'LUMEN_DATA':root+'/state','XDG_CONFIG_HOME':root+'/config'}):
            w=Wissen(Path(root)/'tools');w.show()
            try:
                self.wait(lambda:w.book and not w.job and not w.poller);w.poll_timer.stop()
                QTest.mouseClick(w.daily_button,Qt.LeftButton)
                self.wait(lambda:w.doc and not w.job)
                path=w.doc['path'];self.assertTrue(path.startswith('Journal/'))
                w.editor.appendPlainText('Keep this entry');w.daily_button.click()
                self.wait(lambda:not w.job and not w.dirty)
                self.assertEqual(w.doc['path'],path);self.assertIn('Keep this entry',w.book.read(path)['text'])
                with patch.object(QInputDialog,'getItem',return_value=(tr('Projekt'),True)),patch.object(QInputDialog,'getText',return_value=('Template project',True)):
                    choose_template(w)
                self.wait(lambda:not w.job and w.doc['title']=='Template project')
                self.assertIn(tr('Nächste Schritte'),w.doc['text'])
                self.assertEqual(len(w.book.scan()['notes']),2)
            finally:
                self.wait(lambda:not w.job and not w.poller and not w.live_preview.job)
                w.close();self.wait(lambda:not w.job);w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
