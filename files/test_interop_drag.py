import tempfile
from pathlib import Path
import unittest
from PySide6.QtCore import Qt, QMimeData, QPoint, QPointF, QCoreApplication, QEvent
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from interop_data import Registry
import interop_drag as drag


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



if __name__ == '__main__': unittest.main()
