"""Notes follow live themes without changing content or edit history."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QEvent, QUrl
from PySide6.QtGui import QPalette, QTextCursor, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from appearance import apply_design


class NotesThemeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')

    def wait(self,check):
        for _ in range(400):
            QTest.qWait(20)
            if check():return
        self.fail('Notes did not finish loading')

    def test_live_palette_icons_and_unsaved_document(self):
        from tools_wissen import Wissen
        from notes_design import icon
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ,LUMEN_DATA=root+'/state',XDG_CONFIG_HOME=root+'/config'):
            apply_design(self.app,'glass');w=Wissen(Path(root)/'tools');w.show()
            try:
                self.wait(lambda:w.book and not w.job and not w.poller);w.poll_timer.stop()
                note=w.book.create('Theme check','## Heading\n\n| Name | State |\n|---|---|\n| First | Open |\n\n> [!warning]\n> Protected section\n\nTail')
                w.scanned(w.book.scan());w.show_note(note)
                rich=w.rich_editor;rich.moveCursor(QTextCursor.End);rich.insertPlainText(' draft')
                before=w.document_text();steps=rich.document().availableUndoSteps()
                icons={glyph:icon(glyph) for glyph in ('bold','save')}
                self.assertTrue(rich.codec.opaque)
                for theme in ('glass','atelier','graphite','midnight','clear','system','glass'):
                    with self.subTest(theme=theme):
                        apply_design(self.app,theme);QTest.qWait(30)
                        palette=self.app.palette()
                        for widget in (w,w.centralWidget()):
                            self.assertEqual(widget.palette().color(QPalette.Window),palette.color(QPalette.Window))
                        self.assertEqual(rich.palette().color(QPalette.Base),palette.color(QPalette.Base))
                        self.assertEqual(rich.palette().color(QPalette.Text),palette.color(QPalette.Text))
                        self.assertEqual(w.document_text(),before)
                        self.assertEqual(rich.document().availableUndoSteps(),steps)
                        for glyph,role in [('bold',QPalette.Text),('save',QPalette.HighlightedText)]:
                            image=icons[glyph].pixmap(24,24).toImage()
                            colors=[image.pixelColor(x,y) for x in range(image.width()) for y in range(image.height()) if image.pixelColor(x,y).alpha()>245]
                            self.assertTrue(colors)
                            expected=palette.color(role).getRgb()[:3]
                            # Antialiased premultiplied pixels can round a channel by one.
                            self.assertTrue(all(max(abs(a-b) for a,b in zip(c.getRgb()[:3],expected))<=1 for c in colors))
                        for key in rich.codec.opaque:
                            card=rich.document().resource(QTextDocument.ImageResource,QUrl(key))
                            self.assertEqual(card.pixelColor(0,0),rich.palette().alternateBase().color())
                        if os.environ.get('LUMEN_NOTES_SCREENSHOTS'):
                            w.grab().save(str(Path(os.environ['LUMEN_NOTES_SCREENSHOTS'])/('notes-'+theme+'.png')))
                rich.undo();self.assertNotIn(' draft',w.document_text())
                rich.redo();self.assertEqual(w.document_text(),before)
                w.save_note();self.wait(lambda:not w.job and not w.dirty)
            finally:
                self.wait(lambda:not w.job and not w.poller and not w.live_preview.job)
                w.close();self.wait(lambda:not w.isVisible());w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
