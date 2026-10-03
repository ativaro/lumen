import tempfile
from pathlib import Path
import unittest
from PySide6.QtCore import Qt, QMimeData, QPoint, QPointF, QCoreApplication, QEvent
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from interop_data import Registry
import interop_drag as drag
from tools_workbench import Workbench


class DragTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        self.registry = Registry(self.root)
        self.payload = dict(title='Ein Gedanke', text='Nur gewählter Text', paths=[], source=dict(app='wissen', kind='note', id='note.md', title='Ein Gedanke'))

    def test_mime_contains_only_url_and_snapshot_is_validated(self):
        mime = drag.make_mime(self.payload, self.registry)
        self.assertEqual(mime.formats(), ['text/plain']); self.assertNotIn('gewählter', mime.text())
        self.assertEqual(drag.payload_from_mime(mime, self.registry)['text'], self.payload['text'])
        for value in ['file:///etc/passwd', 'lumen://object/'+('f'*32), mime.text()+'\ntrailing']:
            invalid = QMimeData(); invalid.setText(value)
            with self.assertRaises(ValueError): drag.payload_from_mime(invalid, self.registry)

    def test_native_editor_drop_calls_review_callback_without_inserting_text_or_writing_destination(self):
        window = Workbench(self.root); key = window.library.create('Projekt', notes='Unverändert', resources=[], questions=[]); window.focus_record(key)
        received = []; drag.install_drop_filter(window, received.append)
        try:
            mime = drag.make_mime(self.payload, self.registry); viewport = window.notes.viewport()
            enter = QDragEnterEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
            QApplication.sendEvent(viewport, enter); self.assertTrue(enter.isAccepted())
            drop = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
            QApplication.sendEvent(viewport, drop); QTest.qWait(10)
            self.assertEqual(received[0]['text'], self.payload['text']); self.assertEqual(window.notes.toPlainText(), 'Unverändert')
            self.assertEqual(window.library.get(key)['notes'], 'Unverändert')
        finally:
            window.close(); window.deleteLater(); QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == '__main__': unittest.main()
