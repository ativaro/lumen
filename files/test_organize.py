import sys
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from organize import snapshot, parse_proposal, validate_moves, apply_moves, undo_moves, load_journal, sync_directory


class OrganizeTest(unittest.TestCase):
    def test_preview_apply_restart_undo_and_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'scan.txt'
            source.write_text('Rechnung Monitor September 2026')
            items = snapshot([source], root)
            rows = parse_proposal(json.dumps({'changes': [{'id': 0, 'target': 'Monitor.txt', 'reason': 'Inhalt'}]}), items)
            moves, errors = validate_moves(items, rows, root, 'rename')
            self.assertFalse(errors)
            self.assertTrue(source.exists())
            journal = root / 'undo.json'
            done, errors = apply_moves(moves, journal)
            self.assertFalse(errors)
            self.assertEqual(len(done), 1)
            self.assertEqual((root / 'Monitor.txt').read_text(), 'Rechnung Monitor September 2026')
            self.assertFalse(source.exists())
            self.assertTrue(load_journal(journal))
            restored, errors = undo_moves(journal)
            self.assertFalse(errors)
            self.assertEqual(len(restored), 1)
            self.assertTrue(source.exists())
            self.assertFalse(load_journal(journal))
            # Sorting keeps the original basename and creates only selected destinations.
            rows[0]['target'] = 'Rechnungen/2026/scan.txt'
            moves, errors = validate_moves(items, rows, root, 'sort')
            self.assertFalse(errors)
            done, errors = apply_moves(moves, journal)
            self.assertFalse(errors)
            source.write_text('New file occupying the old name')
            restored, errors = undo_moves(journal)
            self.assertFalse(restored)
            self.assertTrue(errors)
            self.assertEqual(source.read_text(), 'New file occupying the old name')
            self.assertTrue((root / rows[0]['target']).exists())
            self.assertTrue(load_journal(journal))

    def test_untrusted_targets_stale_files_and_responses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = root / 'a.txt', root / 'b.txt'
            a.write_text('A')
            b.write_text('B')
            items = snapshot([a, b], root)
            for target in ('../escape.txt', '/tmp/escape.txt', 'folder/../escape.txt', 'bad\nname.txt', 'a.py', 'b.txt'):
                moves, errors = validate_moves(items, [{'id': 0, 'target': target}], root, 'rename')
                self.assertTrue(errors, target)
            (root / 'link').symlink_to(root, target_is_directory=True)
            self.assertTrue(validate_moves(items, [{'id': 0, 'target': 'link/a.txt'}], root, 'sort')[1])
            self.assertTrue(validate_moves(items, [{'id': 0, 'target': 'same.txt'}, {'id': 1, 'target': 'same.txt'}], root, 'rename')[1])
            moves, conflicts = validate_moves(items, [{'id': 0, 'target': 'new/a.txt'},
                                                       {'id': 1, 'target': 'new/a.txt/b.txt'}], root, 'sort')
            self.assertEqual(set(conflicts), {0, 1})
            for value in ('not json', '{"changes":[]}', '{"changes":[{"id":200,"target":"x"}]}',
                          '{"changes":[{"id":0,"target":"x"},{"id":0,"target":"y"}]}'):
                with self.assertRaises(ValueError):
                    parse_proposal(value, items)
            a.write_text('Changed after preview')
            self.assertTrue(validate_moves(items, [{'id': 0, 'target': 'new.txt'}], root, 'rename')[1])
            with self.assertRaises(ValueError):
                snapshot([root / 'link'], root)

    def test_partial_cancel_undo_and_late_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [root / name for name in ('a.txt', 'b.txt')]
            for path in paths:
                path.write_text(path.name)
            items = snapshot(paths, root)
            rows = [{'id': index, 'target': 'new-' + path.name} for index, path in enumerate(paths)]
            moves, errors = validate_moves(items, rows, root, 'rename')
            journal = root / 'undo.json'
            stop = threading.Event()
            done, errors = apply_moves(moves, journal, stop.is_set, lambda *_: stop.set())
            self.assertEqual(len(done), 1)
            self.assertTrue(errors)
            restored, errors = undo_moves(journal)
            self.assertEqual(len(restored), 1)
            self.assertFalse(errors)
            self.assertTrue(all(path.exists() for path in paths))
            # A conflict after preview must not overwrite or consume the old undo journal.
            (root / 'new-a.txt').write_text('keep me')
            done, errors = apply_moves(moves, journal)
            self.assertFalse(done)
            self.assertTrue(errors)
            self.assertEqual((root / 'new-a.txt').read_text(), 'keep me')
            self.assertFalse(load_journal(journal))
            (root / 'new-a.txt').unlink()
            apply_moves(moves, journal)
            (root / 'new-b.txt').write_text('Edited after apply')
            restored, errors = undo_moves(journal)
            self.assertEqual(len(restored), 1)
            self.assertTrue(errors)
            self.assertEqual((root / 'new-b.txt').read_text(), 'Edited after apply')

    def test_undo_retains_intent_until_restored_directories_are_synced(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'a.txt'
            source.write_text('A')
            items = snapshot([source], root)
            moves, _ = validate_moves(items, [{'id': 0, 'target': 'Folder/a.txt'}], root, 'sort')
            journal = root / 'state' / 'undo.json'
            apply_moves(moves, journal)
            def fail_file_directory(path):
                if path != journal.parent:
                    raise OSError('Directory sync failed')
                sync_directory(path)
            with patch('organize.sync_directory', side_effect=fail_file_directory):
                done, errors = undo_moves(journal)
            self.assertTrue(errors)
            self.assertTrue(source.exists())
            self.assertEqual(load_journal(journal), moves)
            done, errors = undo_moves(journal)
            self.assertFalse(errors)
            self.assertFalse(load_journal(journal))


class OrganizeUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()

    def wait(self, condition):
        from PySide6.QtTest import QTest
        deadline = time.monotonic() + 12
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(condition(), 'Native action timed out')

    def test_network_dialog_teardown_in_real_event_loop(self):
        import subprocess
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'{}')
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        script = '''
import sys
from app import create_app
from assistant_backend import OpenCodeBackend
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog
app = create_app()
app.setQuitOnLastWindowClosed(False)
state = {'count': 0}
def next_dialog():
    dialog = QDialog()
    backend = OpenCodeBackend('/tmp', dialog, server_url=sys.argv[1])
    state['dialog'] = dialog
    dialog.show()
    def done(_):
        backend.shutdown()
        dialog.close()
        dialog.deleteLater()
        state['count'] += 1
        QTimer.singleShot(0, app.quit if state['count'] == 50 else next_dialog)
    backend.request('GET', '/health', callback=done)
next_dialog()
QTimer.singleShot(15000, app.quit)
app.exec()
assert state['count'] == 50, state['count']
'''
        try:
            result = subprocess.run([sys.executable, '-X', 'faulthandler', '-c', script,
                                     f'http://127.0.0.1:{server.server_port}'],
                                    cwd=Path(__file__).parent, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
        finally:
            server.shutdown()
            server.server_close()

    def test_native_preview_edit_deselect_apply_undo_and_invalid_reply(self):
        from assistant_backend import OpenCodeBackend
        from organize_dialog import OrganizeDialog
        from PySide6.QtCore import Qt
        state = {'requests': [], 'messages': [], 'invalid': False}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                self.respond('POST')

            def do_GET(self):
                self.respond('GET')

            def respond(self, method):
                path = self.path.split('?')[0]
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or 'null')
                state['requests'].append((path, body))
                data = {}
                if path == '/config':
                    data = {'model': 'test/model'}
                elif path == '/session':
                    data = {'id': 'ses_proposal'} if method == 'POST' else []
                elif path.endswith('/prompt_async'):
                    answer = json.dumps({'changes': [{'id': 0, 'target': 'Monitor.txt', 'reason': 'Rechnung'},
                                                     {'id': 1, 'target': 'Reise.txt', 'reason': 'Notiz'}]})
                    state['messages'] = [{'info': {'role': 'assistant', 'parentID': body['messageID'], 'time': {'completed': 1}},
                                          'parts': [{'type': 'text', 'text': 'invalid' if state['invalid'] else answer}]}]
                elif path.endswith('/message'):
                    data = state['messages']
                elif path in ('/permission', '/question'):
                    data = []
                raw = json.dumps(data).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [root / 'scan.txt', root / 'note.txt']
            paths[0].write_text('Rechnung Monitor 499 CHF')
            paths[1].write_text('Reise nach Bern')
            backend = OpenCodeBackend(root, server_url=f'http://127.0.0.1:{server.server_port}')
            dialog = OrganizeDialog(paths, root, 'rename', root / 'undo.json', backend=backend)
            dialog.show()
            try:
                dialog.generate_button.click()
                self.wait(lambda: dialog.table.rowCount() == 2 and not dialog.busy())
                self.assertTrue(all(path.exists() for path in paths))
                self.assertTrue(dialog.apply_button.isEnabled())
                sessions = [body for path, body in state['requests'] if path == '/session' and body]
                self.assertEqual(sessions[0]['permission'], [{'permission': '*', 'pattern': '*', 'action': 'deny'}])
                prompt = next(body for path, body in state['requests'] if path.endswith('/prompt_async'))
                self.assertEqual(prompt['tools'], {'*': False})
                self.assertEqual(prompt['agent'], 'plan')
                self.assertIn('499 CHF', prompt['parts'][0]['text'])
                dialog.table.item(0, 2).setText('../escape.txt')
                self.assertFalse(dialog.apply_button.isEnabled())
                dialog.table.item(0, 2).setText('Monitor-2026.txt')
                dialog.table.item(1, 0).setCheckState(Qt.Unchecked)
                self.assertEqual(len(dialog.moves), 1)
                dialog.apply_button.click()
                self.wait(lambda: not dialog.busy())
                self.assertTrue((root / 'Monitor-2026.txt').exists())
                self.assertTrue(paths[1].exists())
                self.assertFalse((root / 'Reise.txt').exists())
                previous_journal = dialog.journal.read_text()
                dialog.journal.write_text('[]')
                dialog.undo_button.click()
                self.wait(lambda: not dialog.busy())
                self.assertTrue(dialog.error.isVisible())
                self.assertTrue((root / 'Monitor-2026.txt').exists())
                dialog.journal.write_text(previous_journal)
                dialog.undo_button.click()
                self.wait(lambda: not dialog.busy())
                self.assertTrue(all(path.exists() for path in paths))
                self.assertFalse(load_journal(root / 'undo.json'))
            finally:
                dialog.reject()
            backend = OpenCodeBackend(root, server_url=f'http://127.0.0.1:{server.server_port}')
            dialog = OrganizeDialog(paths, root, 'rename', root / 'undo.json', backend=backend)
            dialog.show()
            try:
                state['invalid'] = True
                dialog.generate()
                self.wait(lambda: not dialog.busy() and dialog.error.isVisible())
                self.assertFalse(dialog.apply_button.isEnabled())
                self.assertTrue(dialog.generate_button.isEnabled())
                self.assertTrue(all(path.exists() for path in paths))
            finally:
                dialog.reject()
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
