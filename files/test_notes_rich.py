import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from PySide6.QtCore import Qt, QEvent, QUrl, QTimer
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from notes_rich_codec import Codec, SafeDocument
from notes_editor import NotesEditor
from notes_rich_editor import RichEditor


class RichTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def test_untouched_import_is_byte_exact_and_other_blocks_survive_edit(self):
        samples=[r['text'] for r in json.loads(Path(__file__).with_name('notes_compatibility.json').read_text())]
        samples += ['<!-- secret comment -->\n\nText','[link][id]\n\n[id]: https://example.org\n',
                    '> [!warning]\n> Custom\n\nTail', '```py\nx = "a  b"\n```\n\nTail',
                    '| A | B |\n|---|---|\n| 1 | 2 |\n\nTail', '<custom>Keep</custom>\n\nTail']
        for raw in samples:
            with self.subTest(raw=raw):
                codec=Codec(raw);doc=SafeDocument();doc.setMarkdown(codec.rendered)
                self.assertEqual(codec.encode(doc),raw)
                cursor=QTextCursor(doc);cursor.movePosition(QTextCursor.End);cursor.insertBlock();cursor.insertText('Fresh')
                encoded=codec.encode(doc)
                self.assertIn('Fresh',encoded)
                self.assertNotIn('lumen-preserved:',encoded);self.assertNotIn('lumen-wiki:',encoded)
                if '<!--' in raw:self.assertIn('<!-- secret comment -->',encoded)
                if 'custom' in raw:self.assertIn('custom',encoded)
                if '```' in raw:self.assertIn(raw[raw.index('```'):raw.index('```',raw.index('```')+3)+3],encoded)

    def make_editor(self,text):
        source=NotesEditor();source.setPlainText(text)
        rich=RichEditor(SimpleNamespace(editor=source,book=None,doc=None))
        self.addCleanup(rich.deleteLater);self.addCleanup(source.deleteLater)
        return source,rich

    def test_rich_format_undo_and_unicode_roundtrip(self):
        source,rich=self.make_editor('Grüße 🌍')
        rich.selectAll();rich.wrap('**')
        self.assertEqual(rich.toPlainText(),'Grüße 🌍');self.assertEqual(source.toPlainText(),'**Grüße 🌍**')
        rich.wrap('*');self.assertIn('Grüße 🌍',source.toPlainText())
        rich.undo();rich.undo();self.assertEqual(source.toPlainText(),'Grüße 🌍')
        rich.selectAll();rich.wrap('u');self.assertEqual(source.toPlainText(),'<u>Grüße 🌍</u>')
        rich.load_source();self.assertEqual(rich.toPlainText(),'Grüße 🌍')
        rich.selectAll();rich.wrap('u');self.assertEqual(source.toPlainText(),'Grüße 🌍')

    def test_wiki_links_and_external_source_updates(self):
        source,rich=self.make_editor('[[Plan|Bauplan]]\n\nKeep')
        self.assertIn('Bauplan',rich.toPlainText());self.assertNotIn('[[',rich.toPlainText())
        rich.moveCursor(QTextCursor.End);rich.insertPlainText('!')
        self.assertIn('[[Plan|Bauplan]]',source.toPlainText())
        source.appendPlainText('External');self.assertIn('External',rich.toPlainText())
        source.undo();self.assertNotIn('External',rich.toPlainText())

    def test_heading_table_tasks_and_no_external_resource_reads(self):
        source,rich=self.make_editor('Heading\n\nBody')
        rich.moveCursor(QTextCursor.Start);rich.paragraph_style('## ')
        self.assertTrue(source.toPlainText().startswith('## Heading'))
        rich.paragraph_style('');self.assertFalse(source.toPlainText().startswith('#'))
        rich.moveCursor(QTextCursor.End);rich.toggle_checkbox();self.assertIn('- [ ] Body',source.toPlainText())
        rich.toggle_checkbox();self.assertIn('- [x] Body',source.toPlainText())
        rich.undo();rich.undo();rich.moveCursor(QTextCursor.End);rich.insert_table()
        self.assertIn('|',source.toPlainText())
        self.assertIsNone(rich.document().loadResource(QTextDocument.ImageResource,QUrl('file:///etc/passwd')))
        self.assertIsNone(rich.document().loadResource(QTextDocument.ImageResource,QUrl('https://example.org/a.png')))

    def test_protected_section_edit_is_undoable(self):
        source,rich=self.make_editor('<!-- keep -->\n\nTail')
        key=next(iter(rich.codec.opaque))
        def accept():
            dialog=QApplication.activeModalWidget()
            dialog.findChild(NotesEditor).setPlainText('<!-- changed -->\n')
            dialog.accept()
        QTimer.singleShot(40,accept);rich.edit_protected(key)
        self.assertIn('<!-- changed -->',source.toPlainText())
        rich.undo();self.assertEqual(source.toPlainText(),'<!-- keep -->\n\nTail')
        rich.redo();self.assertIn('<!-- changed -->',source.toPlainText())

    def wait(self,check):
        for _ in range(900):
            QTest.qWait(20)
            if check():return
        self.fail('Notes timed out')

    def test_native_toolbar_save_tags_reopen_and_conflict(self):
        from tools_wissen import Wissen
        from note_tags import tags
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'LUMEN_DATA':root+'/state','XDG_CONFIG_HOME':root+'/config'}):
            w=Wissen(Path(root)/'tools');w.resize(1180,850);w.show()
            try:
                self.wait(lambda:w.book and not w.job and not w.poller);w.poll_timer.stop()
                note=w.book.create('Test','Grüße 🌍\n\n[[Plan|Bauplan]]\n\n<!-- keep -->')
                w.scanned(w.book.scan());w.show_note(note)
                self.assertTrue(w.rich_editor.isVisible());self.assertFalse(w.editor.isVisible())
                self.assertFalse(w.live_preview.preview.isVisible())
                cursor=w.rich_editor.textCursor();cursor.movePosition(QTextCursor.Start);cursor.movePosition(QTextCursor.EndOfBlock,QTextCursor.KeepAnchor);w.rich_editor.setTextCursor(cursor)
                QTest.mouseClick(w.editor_tools.widgetForAction(w.format_actions['bold']),Qt.LeftButton)
                self.assertIn('**Grüße 🌍**',w.document_text());self.assertNotIn('**',w.rich_editor.toPlainText())
                w.note_tags.change('wichtig',True)
                self.assertIn('wichtig',tags(w.document_text()))
                before=w.document_text();w.save_note();self.wait(lambda:not w.job and not w.dirty)
                self.assertEqual(w.book.read(note['path'])['text'],before)
                w.show_note(w.book.read(note['path']));self.assertIn('Bauplan',w.rich_editor.toPlainText())
                w.rich_editor.moveCursor(QTextCursor.End);QTest.keyClicks(w.rich_editor,' unsaved')
                self.assertTrue(w.dirty)
                w.conflict=True;w.save_note();self.assertTrue(w.recovery.isVisible())
                self.assertEqual(w.book.read(note['path'])['text'],before)
                w.conflict=False;w.save_note();self.wait(lambda:not w.job and not w.dirty)
                w.toggle_view();self.wait(lambda:w.views.currentIndex()==1 and not w.job)
                w.toggle_view();self.assertTrue(w.rich_editor.isVisible())
                w.source_mode.setChecked(True);self.assertTrue(w.editor.isVisible())
                w.source_mode.setChecked(False);self.assertTrue(w.rich_editor.isVisible())
                from PIL import Image
                image=Path(root)/'sample.png';Image.new('RGB',(12,12),'red').save(image)
                path=w.book.add_image(image)
                picture=w.book.create('Picture','![Bild]('+path+')')
                w.scanned(w.book.scan());w.show_note(picture)
                self.wait(lambda:path in w.live_preview.images and not w.live_preview.job)
                resource=w.rich_editor.document().resource(QTextDocument.ImageResource,QUrl.fromLocalFile(str(w.book.root/path)))
                self.assertFalse(resource.isNull())
            finally:
                self.wait(lambda:not w.job and not w.poller and not w.live_preview.job)
                w.close();self.wait(lambda:not w.job);w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
