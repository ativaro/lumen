"""Focused regressions from an independent loss/replay/lifetime review."""
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget
from lumen_store import Store
from tools_data import Library
from tools_ui import Job, ToolWindow
from interop_targets import apply
from interop_undo import undo


class ReviewExtraTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {'LUMEN_TOOLS_DATA': str(self.root), 'LUMEN_DATA': str(self.root/'state')})
        env.start(); self.addCleanup(env.stop)
        self.store = Store(self.root/'state'); self.job = Job(lambda _:None)

    def pump(self, predicate):
        until = time.monotonic()+3
        while time.monotonic() < until:
            self.app.processEvents()
            if predicate(): return
            time.sleep(.005)
        self.fail('Bounded Qt operation did not finish')

    def test_controller_teardown_ignores_focus_and_events_after_state_is_cleared(self):
        from PySide6.QtCore import QEvent
        from interop_ui import Controller
        window=ToolWindow('workbench','Test','Test','document',self.root);control=Controller(window)
        try:
            del control.window
            control.remember_focus(None,window)
            self.assertFalse(control.eventFilter(window,QEvent(QEvent.FocusOut)))
        finally:
            control.timer.stop();window.close();window.deleteLater();self.app.processEvents()

    def test_undo_preserves_task_description_edited_after_import(self):
        payload = dict(title='Task', text='Original description', source_url='lumen://object/'+'a'*32)
        ref = apply('inbox.task', payload, dict(token='edited-task', title='Task', mode='copy'), self.job, self.root, self.store)
        library = Library('inbox', self.root)
        with library.connect() as db:
            db.execute('UPDATE interop_task_details SET body=? WHERE task=?', ('User description after import', ref['id']))
        with self.assertRaises(ValueError): undo('inbox.task', 'edited-task', self.job, self.root, self.store)
        with library.connect() as db:
            self.assertEqual(db.execute('SELECT body FROM interop_task_details WHERE task=?', (ref['id'],)).fetchone()[0], 'User description after import')


    def test_failed_async_wissen_save_releases_controller_and_preserves_request(self):
        from interop_ui import Controller
        class FailedSave(ToolWindow):
            book = True; conflict = False
            def __init__(self, root):
                super().__init__('wissen', 'Save test', 'Test', 'document', root); self.errors = []
            def error(self, value): self.errors.append(str(value))
            def job_failed(self, value): self.conflict = True; self.error(value)
            def save_note(self, after):
                def fail(job): raise ValueError('Synthetic external edit')
                self.work('Saving', fail, lambda _:after())
        window = FailedSave(self.root); control = Controller(window); request = {'path': str(self.root/'incoming.md')}
        try:
            with patch.object(control, 'deliver') as delivered:
                control.enqueue(request); control.process(); control.timer.stop()
                self.pump(lambda: window.job is None)
                self.app.processEvents()
                self.assertFalse(control.running)
                self.assertIn(request, control.queue)
                delivered.assert_not_called()
        finally:
            control.timer.stop()
            if window.job: window.job.wait(1000)
            window.close(); window.deleteLater(); self.app.processEvents()

    def test_live_dialog_waits_for_cancelled_worker_before_return(self):
        from interop_live import show_live
        window = QWidget(); window.library = Library('workbench', self.root); window.current = window.library.create('Project')
        release = threading.Event(); cancelled = threading.Event(); observed = []
        def read(library, key, job, store):
            if job.cancelled.wait(2): cancelled.set()
            release.wait(2); job.check()
            return []
        def close():
            dialog = QApplication.activeModalWidget(); dialog.reject()
            def while_running():
                observed.append(bool(dialog.isVisible() and dialog.job and dialog.job.isRunning()))
                release.set()
            QTimer.singleShot(20, while_running)
        try:
            QTimer.singleShot(0, close)
            with patch('interop_live.live_notes', side_effect=read): show_live(window)
            self.assertTrue(cancelled.is_set()); self.assertEqual(observed, [True])
        finally:
            release.set(); window.close(); window.deleteLater(); self.app.processEvents()


if __name__ == '__main__': unittest.main()
