"""Isolated user-visible contracts for projects, history, modes and transfers."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from lumen_store import Store
from file_spaces import Catalog
import lumen_history as history
import lumen_modes as modes
import lumen_transfers as transfers


class ModesActivityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.store = Store(self.root / 'state')



    def test_undo_setting_is_atomic_and_refuses_later_edits(self):
        self.store.set_setting('demo', {'value': 2})
        identity = history.record(self.store, 'Setting', 'store-setting', {'value': 1}, {'value': 2}, 'demo')
        self.store.set_setting('demo', {'value': 3})
        with self.assertRaises(ValueError): history.undo_record(self.store, identity)
        self.assertEqual(self.store.setting('demo'), {'value': 3})
        self.store.set_setting('demo', {'value': 2}); history.undo_record(self.store, identity)
        self.assertEqual(self.store.setting('demo'), {'value': 1})
        with self.assertRaises(ValueError): history.undo_record(self.store, identity)

    def test_move_undo_checks_contents_and_parent_symlinks(self):
        source = self.root / 'source'; target = self.root / 'target'
        source.write_text('before'); source.rename(target)
        identity = history.file_change(self.store, 'move', str(source), str(target))
        target.write_text('changed')
        with self.assertRaises(ValueError): history.undo_record(self.store, identity)
        self.assertEqual(target.read_text(), 'changed')
        target.unlink(); source.write_text('another'); source.rename(target)
        identity = history.file_change(self.store, 'move', str(source), str(target))
        history.undo_record(self.store, identity)
        self.assertEqual(source.read_text(), 'another'); self.assertFalse(target.exists())
        folder = self.root / 'folder'; folder.mkdir(); (folder / 'x').write_text('x')
        link = self.root / 'link'; link.symlink_to(folder, target_is_directory=True)
        with self.assertRaises(ValueError): history.fingerprint(link / 'x')

    def test_mode_partial_failure_and_guarded_undo(self):
        mode = dict(modes.DEFAULTS[0], audio='missing', layout='keep')
        current = ['old']
        with patch.object(modes, 'audio_snapshot', side_effect=ValueError('offline')), \
             patch.object(modes, 'dnd_snapshot', side_effect=lambda: current[0]), \
             patch.object(modes, 'dnd_write', side_effect=lambda v: current.__setitem__(0, v)):
            result = modes.apply_mode(self.store, mode)
            self.assertEqual(result['applied'], ['Benachrichtigungen']); self.assertEqual(len(result['errors']), 1)
            identity = history.entries(self.store)[0]['id']; after = current[0]
            current[0] = 'other'
            with self.assertRaises(ValueError): history.undo_record(self.store, identity)
            current[0] = after; history.undo_record(self.store, identity)
            self.assertEqual(current[0], 'old')
        original = modes.modes(self.store)[0]
        modes.save_mode(self.store, original, dict(original, name='First'))
        with self.assertRaises(ValueError): modes.save_mode(self.store, original, dict(original, name='Stale'))

    def test_supervised_copy_shared_ticket_and_no_overwrite(self):
        source = self.root / 'source'; source.write_bytes(b'x' * 900000)
        target = self.root / 'dest'; target.mkdir()
        value = transfers.create(self.store, 'copy', [str(source)], str(target))
        proc = transfers.start(self.store, value); proc.wait(timeout=10)
        final = self.store.setting(transfers.PREFIX + value['id'])
        self.assertEqual(final['status'], 'completed'); self.assertEqual(final['done'], [str(source)])
        self.assertEqual((target / source.name).read_bytes(), source.read_bytes())
        second = transfers.create(self.store, 'copy', [str(source)], str(target))
        transfers.start(self.store, second).wait(timeout=10)
        self.assertEqual(self.store.setting(transfers.PREFIX + second['id'])['status'], 'failed')
        self.assertTrue(any(v['kind'] == 'file-create' for v in history.entries(self.store)))

    def test_portable_directory_copy_reports_progress_and_preserves_symlinks(self):
        from core import copy_entry
        source = self.root / 'photos'; source.mkdir(); (source / 'empty').mkdir()
        (source / 'image').write_bytes(b'12345'); (source / 'link').symlink_to('image')
        target = self.root / 'nas'; target.mkdir(); progress = []
        destination = copy_entry(source, target, portable=True, progress=progress.append)
        self.assertEqual(sum(progress), 5); self.assertEqual((destination / 'image').read_bytes(), b'12345')
        self.assertTrue((destination / 'empty').is_dir()); self.assertTrue((destination / 'link').is_symlink())
        with self.assertRaises(FileExistsError): copy_entry(source, target, portable=True, progress=progress.append)

    def test_http_resume_restart_validator_and_destination_guard(self):
        content = b'hello-world-' * 40000
        behavior = {'etag': '"one"', 'ranges': True}; requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                offset = int(self.headers.get('Range', 'bytes=0-')[6:-1]); requests.append(offset)
                partial = bool(offset and behavior['ranges'])
                self.send_response(206 if partial else 200)
                self.send_header('ETag', behavior['etag'])
                if partial: self.send_header('Content-Range', f'bytes {offset}-{len(content)-1}/{len(content)}')
                else: offset = 0
                self.send_header('Content-Length', str(len(content) - offset)); self.end_headers()
                self.wfile.write(content[offset:])
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_port}/file'
        for index, etag, ranges, success in [(0, '"one"', True, True), (1, '"changed"', True, False), (2, '"changed"', False, True)]:
            behavior.update(etag=etag, ranges=ranges)
            target = self.root / ('download-' + str(index))
            value = transfers.create(self.store, 'download', [url], str(target))
            part = target.with_name('.lumen-download-' + value['id'] + '.part'); part.write_bytes(content[:10000])
            value = transfers.update(self.store, value['id'], validator='"one"', partial=history.fingerprint(part))
            if success:
                transfers.download(self.store, value); self.assertEqual(target.read_bytes(), content)
                with self.assertRaises(FileExistsError): transfers.download(self.store, value)
            else:
                with self.assertRaises(ValueError): transfers.download(self.store, value)
                self.assertFalse(target.exists()); self.assertEqual(part.stat().st_size, 10000)
        self.assertEqual(requests, [10000, 10000, 10000])

    def test_cancel_before_start_preserves_source_and_becomes_paused(self):
        source = self.root / 'file'; source.write_text('keep')
        destination = self.root / 'dest'; destination.mkdir()
        value = transfers.create(self.store, 'copy', [str(source)], str(destination))
        transfers.pause(self.store, value['id'])
        transfers.start(self.store, value).wait(timeout=10)
        result = self.store.setting(transfers.PREFIX + value['id'])
        self.assertEqual(result['status'], 'paused'); self.assertTrue(source.exists())
        self.assertFalse((destination / source.name).exists())

    def test_preferences_undo_preserves_types_and_rejects_conflict(self):
        from PySide6.QtCore import QSettings
        path = str(self.root / 'preferences.ini'); settings = QSettings(path, QSettings.IniFormat)
        settings.setValue('preview', True); settings.setValue('limit', 100); settings.sync()
        identity = history.record(self.store, 'Prefs', 'preferences', {'preview': False, 'limit': 50}, {'preview': True, 'limit': 100}, path)
        settings.setValue('limit', 200); settings.sync()
        with self.assertRaises(ValueError): history.undo_record(self.store, identity)
        self.assertTrue(settings.value('preview', type=bool))
        settings.setValue('limit', 100); settings.sync(); history.undo_record(self.store, identity)
        settings.sync(); self.assertFalse(settings.value('preview', type=bool)); self.assertEqual(settings.value('limit', type=int), 50)


class NativeModesActivityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()

    def wait(self, condition):
        from PySide6.QtTest import QTest
        deadline = time.monotonic() + 10
        while not condition() and time.monotonic() < deadline: QTest.qWait(20)
        self.assertTrue(condition())



if __name__ == '__main__': unittest.main()
