"""Source actions bind to current native identities and preserve changes."""
import os
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest
from lumen_memory import Memory
from lumen_store import Store
from assistant_backend import OpenCodeBackend
from memory_sources_ui import MemorySources


class SourceUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.app = QApplication.instance() or create_app()

    def test_open_correct_forget_and_session_reset(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, LUMEN_DATA=temp):
            memory=Memory(Store());memory.configure(True,False)
            note=memory.remember('Antwortlänge','Kurze Antworten',kind='preference')
            source=dict(id=note['id'],revision=note['hash'],path=note['path'],title=note['title'],source_kind='memory',origin='Lumen')
            backend=OpenCodeBackend(temp);control=MemorySources(backend)
            snapshot=dict(version=1,phase='prepared',sources=[source])
            try:
                control.receive(snapshot);self.assertTrue(control.isHidden())
                control.receive(dict(snapshot,phase='submitted'));self.assertFalse(control.isHidden())
                control.populate();self.assertEqual(len(control.menu.actions()),1)
                with patch('interop_open.launch') as launch:
                    control.open_source(source)
                    launch.assert_called_once_with('wissen',[str(memory.book.root/note['path']),'--area','lumen'])
                changed=memory.write(note['path'],'# Antwortlänge\nAusführliche Antworten',note['hash'])
                with patch.object(control,'error') as error:
                    control.forget(source);error.assert_called_once()
                    self.assertTrue((memory.book.root/note['path']).exists())
                current=dict(source,revision=changed['hash'])
                control.receive(dict(snapshot,phase='submitted',sources=[current]))
                with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):control.forget(current)
                for _ in range(200):
                    QTest.qWait(20)
                    if backend.memory and not backend.memory.jobs:break
                self.assertEqual(memory.scan()['notes'],[])
                self.assertTrue(control.isHidden())
                control.receive(dict(snapshot,phase='submitted'));backend.sessionChanged.emit('other')
                self.assertTrue(control.isHidden())
            finally:
                backend.shutdown();control.close();control.deleteLater();backend.deleteLater()


if __name__=='__main__':unittest.main()
