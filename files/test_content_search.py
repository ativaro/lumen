import sys
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from content_search import query_groups, parse_groups, find_passage, scan, folder_fd


class ContentSearchTest(unittest.TestCase):
    def test_core_passages_equal_the_python_passages_for_pictures_and_captions(self):
        # The document core matches files; find_passage still matches recognised pictures and captions.
        texts = ['Kopf\n\fDie Rechnungen vom März\nfür den Monitorarm',
                 'ÄPFEL und Birnen' + ' füllen' * 80 + ' am Ende eine Rechnung',
                 'eine neue  \n rechnung ohne Monitor', 'ab_rechnung und xrechnung', 'Ǆwort Rechnungsbetrag ſonst']
        groups = [[['rechnung'], ['monitor', 'bildschirm']], [['äpfel'], ['rechnung']], [['neue rechnung']], [['rechnung']], [['ǆwort'], ['rechnung']]]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for number, text in enumerate(texts): (root / f'{number}.txt').write_text(text)
            for group in groups:
                found = {Path(e['path']).name: (e['snippet'], e['page'], e['line']) for e in scan(root, group) if e['type'] == 'hit'}
                for number, text in enumerate(texts):
                    passage = find_passage(text, group)
                    self.assertEqual(found.get(f'{number}.txt'), passage and (passage['snippet'], passage['page'], passage['line']), (group, number))

    def test_question_terms_alternatives_and_actual_passage(self):
        groups = query_groups('Die Rechnungen für meinen Monitor')
        self.assertEqual(groups, [['rechnung'], ['monitor']])
        content = 'Erste Seite ohne Treffer.\fRechnung Nr. 18\nProdukt: Monitor 27 Zoll, CHF 499.00.'
        result = find_passage(content, groups)
        self.assertEqual(result['page'], 2)
        self.assertIn('Monitor 27 Zoll', result['snippet'])
        self.assertNotIn('Erste Seite', result['snippet'])
        self.assertTrue(all(part in content for part in result['snippet'].split(' … ')))
        expanded = parse_groups('{"groups":[["Rechnung", "Beleg"],["Monitor", "Bildschirm"]]}')
        self.assertIsNotNone(find_passage('Beleg für den Bildschirm', expanded))
        self.assertIsNone(find_passage('Rechnung für eine Tastatur', expanded))
        self.assertEqual(query_groups('"Projekt Alfa" Rechnung'), [['projekt alfa'], ['rechnung']])
        for word in ('Straße', 'Maße', 'GRÖẞE'):
            self.assertIsNotNone(find_passage('Die ' + word.lower(), query_groups(word)))
            self.assertIsNotNone(find_passage(word, parse_groups(json.dumps({'groups': [[word]]}))))
        for response in ('not json', '{"groups":[]}', '{"groups":[[".*"]]}', '{"groups":["Monitor"]}'):
            with self.assertRaises(ValueError):
                parse_groups(response)

    def test_local_scan_hidden_symlinks_binary_limits_and_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'sub').mkdir()
            (root / 'sub/scan.txt').write_text('Rechnung für Monitor 27 Zoll. CHF 499.')
            (root / '.private.txt').write_text('Rechnung Monitor geheim')
            (root / 'wrong.txt').write_text('Rechnung für Schuhe')
            (root / 'binary.txt').write_bytes(b'Rechnung Monitor\0binary')
            (root / 'link.txt').symlink_to(root / '.private.txt')
            (root / 'sub/loop').symlink_to(root, target_is_directory=True)
            os.mkfifo(root / 'pipe.txt')
            events = list(scan(root, query_groups('Rechnung Monitor'), False))
            hits = [event for event in events if event['type'] == 'hit']
            self.assertEqual([Path(hit['path']).name for hit in hits], ['scan.txt'])
            self.assertIn('CHF 499', hits[0]['snippet'])
            self.assertEqual(events[-1]['type'], 'done')
            more = list(scan(root, query_groups('Monitor'), True, max_hits=1))
            self.assertEqual(more[-1]['limit'], 'Trefferlimit')
            limited = list(scan(root, query_groups('absent'), True, max_entries=1))[-1]
            self.assertEqual((limited['visited'], limited['limit']), (1, 'Eintragslimit'))
            (root / 'large.txt').write_text('Rechnung Monitor ' + 'x' * (1024 * 1024 + 1))
            summary = list(scan(root, query_groups('Monitor'), False))[-1]
            self.assertGreaterEqual(summary['partial'], 1)
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('content_search.py')), '--scan'],
                                    input=json.dumps({'root': str(root), 'groups': [['rechnung'], ['monitor']], 'hidden': False}),
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout.splitlines()[-1])['type'], 'done')

    def test_replaced_directory_cannot_escape_pinned_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'scope'
            outside = Path(tmp) / 'outside'
            root.mkdir()
            outside.mkdir()
            (root / 'child').mkdir()
            descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                (root / 'child').rmdir()
                (root / 'child').symlink_to(outside, target_is_directory=True)
                with self.assertRaises(OSError):
                    folder_fd(descriptor, Path('child'))
            finally:
                os.close(descriptor)


def ended(pid):
    """The process is gone or a zombie; one reaped between the two looks has ended too."""
    try: return Path(f'/proc/{pid}/stat').read_text().split()[2] == 'Z'
    except (FileNotFoundError, ProcessLookupError): return True


class ContentSearchUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()

    def wait(self, condition, seconds=10):
        from PySide6.QtTest import QTest
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(condition(), 'Content search timed out')

    def test_native_text_pdf_synonyms_errors_and_folders(self):
        from assistant_backend import OpenCodeBackend
        from content_search_dialog import ContentSearchDialog
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPainter, QPdfWriter
        state = {'requests': [], 'messages': [], 'invalid': False}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                self.respond('GET')

            def do_POST(self):
                self.respond('POST')

            def respond(self, method):
                path = self.path.split('?')[0]
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or 'null')
                if path == '/event':
                    self.send_error(404); return
                state['requests'].append((path, body))
                data = {}
                if path == '/config':
                    data = {'model': 'synthetic/search'}
                elif path == '/session':
                    data = {'id': 'ses_search'} if method == 'POST' else []
                elif path.endswith('/prompt_async'):
                    text = 'invalid' if state['invalid'] else '{"groups":[["rechnung","beleg"],["monitor","bildschirm"]]}'
                    state['messages'] = [{'info': {'role': 'assistant', 'parentID': body['messageID'], 'finish': 'stop', 'time': {'completed': 1}},
                                          'parts': [{'type': 'text', 'text': text}]}]
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
            (root / 'scan.txt').write_text('Rechnung Monitor. Interne Nummer SECRET-781. <img src="file:///never-load">')
            (root / 'shoe.txt').write_text('Schuhe in Größe 42')
            writer = QPdfWriter(str(root / 'invoice.pdf'))
            painter = QPainter(writer)
            painter.drawText(100, 300, 'Einleitung ohne Produkte')
            writer.newPage()
            painter.drawText(100, 300, 'Rechnung Bildschirm CHF 499.00')
            painter.end()
            del writer
            backend = OpenCodeBackend(root, server_url=f'http://127.0.0.1:{server.server_port}')
            dialog = ContentSearchDialog(root, backend=backend)
            dialog.show()
            try:
                dialog.query.setText('Die Rechnung für meinen Monitor')
                dialog.start()
                self.wait(lambda: dialog.completed and not dialog.proc)
                self.assertEqual(dialog.results.topLevelItemCount(), 1)
                dialog.results.setCurrentItem(dialog.results.topLevelItem(0))
                self.assertIn('<img src=', dialog.passage.toPlainText())
                dialog.expand_button.click()
                self.wait(lambda: not dialog.expanding and not dialog.proc and dialog.results.topLevelItemCount() == 2)
                prompt = next(body for path, body in state['requests'] if path.endswith('/prompt_async'))
                self.assertEqual(prompt['tools'], {'*': False})
                self.assertEqual(len(prompt['parts']), 1)
                self.assertNotIn('SECRET-781', json.dumps(prompt))
                self.assertNotIn(tmp, json.dumps(prompt))
                pdf = next(dialog.results.topLevelItem(row) for row in range(2)
                           if dialog.results.topLevelItem(row).text(0) == 'invoice.pdf')
                self.assertEqual(pdf.data(0, Qt.UserRole)['page'], 2)
                dialog.results.setCurrentItem(pdf)
                self.wait(lambda: dialog.preview.pages == 2 and not dialog.preview.pixmap.isNull())
                self.assertEqual(dialog.preview.page, 2)
                state['invalid'] = True
                dialog.expand()
                self.wait(lambda: dialog.error.isVisible() and not dialog.expanding)
                self.assertEqual(dialog.results.topLevelItemCount(), 2)
                self.assertTrue(dialog.expand_button.isEnabled())
                # New local query must replace prior results; no stale model answer is applied.
                dialog.query.setText('Schuhe')
                dialog.edited()
                dialog.start()
                self.wait(lambda: dialog.completed and not dialog.proc)
                self.assertEqual(dialog.results.topLevelItemCount(), 1)
                self.assertEqual(dialog.results.topLevelItem(0).text(0), 'shoe.txt')
                dialog.results.setCurrentItem(dialog.results.topLevelItem(0))
                folders = []
                dialog.folderRequested.connect(folders.append)
                dialog.open_folder()
                self.assertEqual(folders, [str(root)])
            finally:
                dialog.reject()
                server.shutdown()
                server.server_close()

    def test_cancel_kills_scanner_and_pdf_decoder_and_ignores_old_hits(self):
        from content_search_dialog import ContentSearchDialog
        from PySide6.QtTest import QTest
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = root / 'bin'
            fake_bin.mkdir()
            marker = root / 'decoder.pid'
            # A stand-in document core whose reader child would outlive a scanner that is not killed as a group.
            fake = fake_bin / 'lumen-document'
            fake.write_text('#!/usr/bin/python3\nimport os,subprocess,sys,time\n'
                            'child=subprocess.Popen([sys.executable,"-c","import os,time;from pathlib import Path;'
                            'Path(os.environ[\'LUMEN_TEST_DECODER_PID\']).write_text(str(os.getpid()));time.sleep(30)"])\n'
                            'time.sleep(30)\n')
            fake.chmod(0o755)
            (root / 'blocked.pdf').write_bytes(b'PDF test')
            with patch.dict(os.environ, {'LUMEN_BIN_DIR': str(fake_bin), 'LUMEN_TEST_DECODER_PID': str(marker)}):
                dialog = ContentSearchDialog(root)
                dialog.show()
                try:
                    dialog.query.setText('Monitor')
                    dialog.start()
                    old_proc = dialog.proc
                    self.wait(marker.exists)
                    child_pid = int(marker.read_text())
                    dialog.cancel()
                    self.assertIsNone(dialog.proc)
                    self.assertFalse(dialog.cancel_button.isVisible())
                    QTest.qWait(100)
                    self.assertTrue(ended(child_pid))
                    # Callback from a previous process cannot add results to the current query.
                    dialog.read_results(old_proc)
                    self.assertEqual(dialog.results.topLevelItemCount(), 0)
                    marker.unlink()
                    dialog.start()
                    self.wait(marker.exists)
                    child_pid = int(marker.read_text())
                    os.kill(int(dialog.proc.processId()), 9)
                    self.wait(lambda: dialog.proc is None and dialog.error.isVisible())
                    QTest.qWait(100)
                    self.assertTrue(ended(child_pid))
                finally:
                    dialog.reject()


if __name__ == '__main__':
    unittest.main()
