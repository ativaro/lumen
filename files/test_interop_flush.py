import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from PyQt5.QtCore import QTimer
from PyQt5.QtNetwork import QLocalServer
from PyQt5.QtWidgets import QApplication, QWidget, QDialog
from tools_data import Library, Cancelled
from tools_ui import Job
import interop_flush as flush


class FlushTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.library = Library('reader', self.root)
        self.server = QLocalServer(); self.addCleanup(self.server.close)
        self.name = flush.server_name(self.library.root)
        self.assertTrue(self.server.listen(self.name)); self.addCleanup(lambda: QLocalServer.removeServer(self.name))
        self.window = QWidget(); self.addCleanup(self.window.close)
        self.window.name = 'reader'; self.window.job = None; self.window.engine = None
        self.window.save = lambda: None
        def accept():
            connection = self.server.nextPendingConnection(); buffer = bytearray()
            connection.disconnected.connect(connection.deleteLater)
            def read():
                buffer.extend(bytes(connection.readAll()))
                if b'\n' not in buffer: return
                connection.readyRead.disconnect(read)
                flush.serve_flush(self.window, connection, json.loads(buffer.split(b'\n', 1)[0]), timeout_ms=500)
            connection.readyRead.connect(read); read()
        self.server.newConnection.connect(accept)

    def request(self):
        result = {}
        def work():
            try: result['value'] = flush.request_flush(self.library.root, Job(lambda _: None), timeout=1)
            except Exception as error: result['error'] = error
        thread = threading.Thread(target=work); thread.start()
        deadline = time.monotonic()+3
        while thread.is_alive() and time.monotonic() < deadline:
            self.app.processEvents(); thread.join(.01)
        self.assertFalse(thread.is_alive(), 'bounded flush did not return')
        if 'error' in result: raise result['error']
        return result['value']

    def test_acknowledgement_follows_actual_synchronous_save(self):
        output = self.root/'saved.txt'
        self.window.save = lambda: output.write_text('flushed')
        result = self.request()
        self.assertEqual(output.read_text(), 'flushed')
        self.assertEqual(result['app'], 'reader'); self.assertGreater(result['flushed_at'], 0)

    def test_wissen_waits_for_asynchronous_note_write(self):
        self.server.close(); self.window.name = 'wissen'; self.library = Library('wissen', self.root)
        self.assertTrue(self.server.listen(flush.server_name(self.library.root)))
        self.window.dirty = True; self.window.conflict = False; self.window.poller = None
        def save(after):
            self.window.job = object(); self.window.writing = True
            def finish(): self.window.job = None; self.window.dirty = False; after()
            QTimer.singleShot(60, finish)
        self.window.save_note = save
        result = self.request(); self.assertEqual(result['app'], 'wissen'); self.assertFalse(self.window.dirty)

    def test_busy_conflict_modal_and_save_failure_abort(self):
        self.window.job = object()
        with self.assertRaisesRegex(ValueError, 'Vorgang'): self.request()
        self.window.job = None; self.window.conflict = True
        with self.assertRaisesRegex(ValueError, 'Notizkonflikt'): self.request()
        self.window.conflict = False
        dialog = QDialog(self.window); dialog.setModal(True); dialog.show(); self.app.processEvents()
        with self.assertRaisesRegex(ValueError, 'Dialog'): self.request()
        dialog.close()
        def failing(): raise ValueError('Synthetic disk full')
        self.window.save = failing
        with self.assertRaisesRegex(ValueError, 'disk full'): self.request()

    def test_unreachable_live_window_is_not_silently_skipped(self):
        self.server.close()
        (self.library.root/'window.lock').write_text(str(os.getpid())+'\nlocalhost\ntest\n')
        with self.assertRaisesRegex(ValueError, 'nicht erreichbar'):
            flush.request_flush(self.library.root, Job(lambda _: None), timeout=.2)
        (self.library.root/'window.lock').unlink()
        self.assertIsNone(flush.request_flush(self.library.root, Job(lambda _: None), timeout=.2))

    def test_only_relevant_apps_are_asked_and_errors_abort_barrier(self):
        Library('radio', self.root)
        plan = dict(sources=[str(self.library.root)])
        with patch('interop_flush.request_flush', return_value=dict(app='reader', flushed_at=1)) as request:
            result = flush.flush_for_plan(self.root, plan, Job(lambda _: None))
        self.assertEqual(result, [dict(app='reader', flushed_at=1)])
        self.assertEqual(request.call_args.args[0], self.library.root)
        with patch('interop_flush.request_flush', side_effect=ValueError('Busy')):
            with self.assertRaisesRegex(ValueError, 'Lumen Reader: Busy'):
                flush.flush_for_plan(self.root, plan, Job(lambda _: None))


if __name__ == '__main__': unittest.main()
