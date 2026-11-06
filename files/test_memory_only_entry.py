"""The retained native memory editor cannot become a second user-notebook app."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from lumen_store import Store
from lumen_memory import Memory, root as memory_root
from tools_wissen import Wissen


class MemoryEntryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.app=QApplication.instance() or create_app()

    def test_memory_editor_preserves_data_and_refuses_user_notebook_navigation(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,LUMEN_DATA=temp+'/state',LUMEN_TOOLS_DATA=temp+'/tools'):
            store=Store();memory=Memory(store);note=memory.remember('Preference','Keep memory data')
            window=Wissen(root=Path(temp)/'memory-view',memory_only=True)
            try:
                deadline=time.monotonic()+8
                while (window.job or not window.book) and time.monotonic()<deadline:QTest.qWait(20)
                self.assertIsNotNone(window.book);self.assertEqual(window.area,'lumen')
                self.assertEqual(window.book.root,memory_root(store));self.assertIn('Gedächtnis',window.windowTitle())
                self.assertFalse(store.setting('knowledge/notebook',''))
                self.assertEqual(memory.book.read(note['path'])['hash'],note['hash'])
                with self.assertRaises(ValueError):window.switch_area('user')
                with self.assertRaises(ValueError):window.open_section('sources')
                outside=Path(temp)/'outside.md';outside.write_text('Do not import')
                with self.assertRaises(ValueError):window.open_file(str(outside))
                labels=[a.text() for a in window.notebook_menu.actions()]
                self.assertNotIn('Meine Notizen',labels);self.assertNotIn('Neue Sammlung',labels);self.assertNotIn('Dokumentquellen',labels)
                self.assertFalse(hasattr(window,'sync_timer'));self.assertFalse(store.setting('knowledge/notebook',''))
                self.assertFalse(getattr(window,'interop_installed',False))
                from interop_ui import Controller
                from interop_context import receive_drop
                with patch('interop_ui.reviewed_send') as send:
                    with self.assertRaises(ValueError):receive_drop(window,dict(title='Do not import',paths=[str(outside)]))
                    send.assert_not_called()
                controller=Controller(window)
                for request in ({'handoff':'a'*32},{'ref':'lumen://object/'+'b'*32}):
                    with self.assertRaises(ValueError):controller.enqueue(request)
                    with self.assertRaises(ValueError):controller.deliver(request)
            finally:
                window.closing=True;window.after_job=None;window.poll_timer.stop()
                for job in (window.job,window.poller):
                    if job:job.cancelled.set();job.wait(5000)
                QTest.qWait(100)
                window.close();QTest.qWait(100);window.deleteLater();QTest.qWait(20)
