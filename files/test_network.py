import unittest

from network import normalize_url, remote_path


class NetworkAddressTest(unittest.TestCase):
    def test_cleanup_only_dead_known_mounts(self):
        from unittest.mock import patch
        from network_cleanup import cleanup, mount_records
        text = '20 1 0:2 / /run/user/1000/kio-fuse-one rw - fuse.kio-fuse kio-fuse rw,user_id=1000,group_id=1000'
        records = mount_records(text, 1000)
        self.assertEqual(len(records), 1)
        self.assertEqual(mount_records(text, 2000), {})
        with patch('network_cleanup.mounts', return_value=records), patch('network_cleanup.probe', return_value=False) as probe, patch('network_cleanup.subprocess.run') as run:
            cleanup(['/run/user/1000/kio-fuse-one/smb/server'])
            run.assert_not_called()
            probe.return_value = True
            cleanup(['/run/user/1000/kio-fuse-other/smb/server'])
            run.assert_not_called()
            cleanup(['/run/user/1000/kio-fuse-one/smb/server'])
            self.assertEqual(run.call_args.args[0], ['fusermount3', '-u', '--', '/run/user/1000/kio-fuse-one'])
        with patch('network_cleanup.mounts', side_effect=[records, {}]), patch('network_cleanup.probe', return_value=True), patch('network_cleanup.subprocess.run') as run:
            cleanup(['/run/user/1000/kio-fuse-one/smb/server']); run.assert_not_called()

    def test_normalizes_protocols_unc_and_unicode(self):
        cases = {
            r'\\nas\Freigabe\Bilder': 'smb://nas/Freigabe/Bilder',
            'smb://nas': 'smb://nas/',
            'sftp://alice@host:2222/Bilder': 'sftp://alice@host:2222/Bilder',
            'https://cloud.example/remote.php/dav/files/alice/': 'webdavs://cloud.example/remote.php/dav/files/alice/',
            'dav://host/folder': 'webdav://host/folder',
            'nfs://host/export': 'nfs://host/export',
        }
        for text, expected in cases.items():
            self.assertEqual(normalize_url(text), expected)
        self.assertIn('%23', normalize_url('smb://nas/Foto%23eins'))
        self.assertIn('%C3', normalize_url('smb://nas/Grüße'))

    def test_rejects_credentials_and_unsupported_addresses(self):
        for value in ['smb://user:secret@host/share', 'sftp://user:se%63ret@host/',
                      'smb:///share', 'javascript://host/file', 'file:///tmp',
                      'smb://host:70000/share', 'smb://host:0/share',
                      'smb://host/share?password=secret', 'smb://host/share#part',
                      'smb://host/share\n', 'server/share']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_url(value)

    def test_remote_paths_keep_url_escaping_and_mount_boundaries(self):
        mappings = {'/run/user/1000/kio-fuse-test/smb/nas/share': 'smb://nas/share'}
        self.assertEqual(remote_path('/run/user/1000/kio-fuse-test/smb/nas/share/Sub #1/a?.txt', mappings),
                         'smb://nas/share/Sub%20%231/a%3F.txt')
        self.assertIsNone(remote_path('/run/user/1000/kio-fuse-test/smb/nas/share-other', mappings))
        self.assertIsNone(remote_path('/tmp/local', mappings))


class NetworkRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()

    def wait_until(self, condition, seconds=15):
        import time
        from PyQt5.QtTest import QTest
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(15)
        self.assertTrue(condition(), 'Network operation timed out')

    def test_smb_dialog_accepts_server_and_listing_rejects_missing_folder(self):
        import tempfile
        from network import ConnectDialog, Network
        from PyQt5.QtWidgets import QDialog, QLineEdit
        dialog = ConnectDialog(address='smb://nas/')
        dialog.validate()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(dialog.url, 'smb://nas/')
        self.assertEqual(dialog.findChildren(QLineEdit), [dialog.address])
        dialog.address.setText('smb://alice@nas/Fotos 2026'); dialog.validate()
        self.assertEqual(dialog.url, 'smb://alice@nas/Fotos%202026')
        dialog.deleteLater()
        with tempfile.TemporaryDirectory() as tmp:
            network = Network(); errors = []; connected = []
            network.failed.connect(errors.append); network.connected.connect(lambda *args: connected.append(args))
            network.check_listing('smb://nas/Fotos', tmp + '/missing')
            self.wait_until(lambda: network.probe is None)
            self.assertTrue(errors); self.assertFalse(connected)
            network.check_listing('smb://nas/Fotos', tmp)
            self.wait_until(lambda: network.probe is None)
            self.assertEqual(len(connected), 1)
            network.close(); network.deleteLater()

    def test_smb_native_authentication_precedes_mount_and_cancel_prevents_late_mount(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from PyQt5.QtTest import QTest
        from network import Network
        with tempfile.TemporaryDirectory() as tmp:
            helper = Path(tmp) / 'kioclient'
            helper.write_text('#!/bin/sh\nexit 0\n'); helper.chmod(0o755)
            network = Network(); errors = []; network.failed.connect(errors.append)
            with patch('network.shutil.which', return_value=str(helper)), patch.object(network, 'mount_url') as mount:
                network.mount('smb://nas/')
                self.assertEqual(network.probe.arguments(), ['--interactive', '--desktopfile', 'lumen-files', 'ls', 'smb://nas/'])
                self.wait_until(lambda: network.probe is None)
                mount.assert_called_once_with('smb://nas/')
                mount.reset_mock()
                network.mount('smb://alice@nas/Fotos')
                self.assertEqual(network.probe.arguments()[-2:], ['ls', 'smb://alice@nas/Fotos'])
                self.wait_until(lambda: network.probe is None)
                mount.assert_called_once_with('smb://alice@nas/Fotos')
                mount.reset_mock()
                helper.write_text('#!/bin/sh\nexit 1\n')
                network.mount('smb://alice@nas/Fotos')
                self.wait_until(lambda: network.probe is None)
                self.assertTrue(errors); mount.assert_not_called()
                errors.clear(); helper.write_text('#!/bin/sh\nexec sleep 2\n')
                network.mount('smb://alice@nas/Fotos'); network.cancel(); QTest.qWait(30)
                self.assertFalse(errors); mount.assert_not_called()
            with patch('network.shutil.which', return_value=None), patch.object(network, 'mount_url') as mount:
                network.mount('smb://alice@nas/Fotos')
                self.assertIn('kde-cli-tools', errors[-1]); mount.assert_not_called()
            network.close(); network.deleteLater()

    def test_saved_smb_server_browses_shares_without_address_dialog(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from PyQt5.QtCore import QSettings
        from PyQt5.QtTest import QTest
        from app import Window
        from file_spaces import Catalog
        from lumen_store import Store
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); server = root / 'server'; share = server / 'Fotos 2026'
            share.mkdir(parents=True)
            settings = QSettings(str(root / 'settings.ini'), QSettings.IniFormat)
            settings.setValue('network_servers', ['smb://nas/'])
            catalog = Catalog(Store(root / 'state'))
            window = Window(tmp, settings, catalog)
            errors = []; window.error = lambda *args: errors.append(args)
            def mounted(address):
                path = str(server if address == 'smb://nas/' else share)
                window.network.mounts[path] = address
                window.network.connected.emit(address, path)
            try:
                with patch('app.ConnectDialog') as dialog, patch.object(window.network, 'mount', side_effect=mounted) as mount:
                    window.connect_server(window.saved_servers()[0])
                    self.assertEqual(window.current_location, 'smb://nas/')
                    self.wait_until(lambda: window.proxy.rowCount(window.view.rootIndex()) == 1)
                    window.open_index(window.proxy.index(0, 0, window.view.rootIndex()))
                    self.assertEqual(window.current_location, 'smb://nas/Fotos%202026')
                    mount.assert_called_with('smb://nas/Fotos%202026')
                    window.up()
                    self.assertEqual(window.current_location, 'smb://nas/')
                    window.history(-1)
                    self.assertEqual(window.current_location, 'smb://nas/Fotos%202026')
                    dialog.assert_not_called()
                library = catalog.save_library(None, 'Server', [{'label': 'NAS', 'location': 'smb://nas/'}])
                self.assertEqual(library['sources'][0]['location'], 'smb://nas/')
                self.assertFalse(errors, errors)
            finally:
                window.close(); window.deleteLater(); QTest.qWait(100)

    def test_real_webdav_connection_navigation_preview_and_transfer(self):
        import tempfile
        import threading
        from functools import partial
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
        from pathlib import Path
        from urllib.parse import quote, urlsplit
        from xml.sax.saxutils import escape
        from app import Window
        from file_spaces import Catalog, LIBRARY
        from lumen_store import Store
        from PyQt5.QtCore import QSettings
        from PyQt5.QtTest import QTest

        class DAV(SimpleHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_PROPFIND(self):
                length = int(self.headers.get('Content-Length', 0))
                self.rfile.read(length)
                path = Path(self.translate_path(self.path))
                if not path.exists():
                    self.send_error(404)
                    return
                children = [path]
                if self.headers.get('Depth') != '0' and path.is_dir():
                    children += list(path.iterdir())
                body = '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'
                for child in children:
                    relative = child.relative_to(self.directory).as_posix()
                    href = '/' if relative == '.' else '/' + relative
                    if child.is_dir() and not href.endswith('/'):
                        href += '/'
                    body += (f'<d:response><d:href>{escape(quote(href))}</d:href><d:propstat><d:prop>'
                             f'<d:displayname>{escape(child.name)}</d:displayname>'
                             f'<d:resourcetype>{"<d:collection/>" if child.is_dir() else ""}</d:resourcetype>'
                             f'<d:getcontentlength>{child.stat().st_size if child.is_file() else 0}</d:getcontentlength>'
                             '<d:getlastmodified>Mon, 28 Sep 2026 12:00:00 GMT</d:getlastmodified>'
                             '</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>')
                data = (body + '</d:multistatus>').encode()
                self.send_response(207)
                self.send_header('Content-Type', 'application/xml; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_OPTIONS(self):
                self.send_response(200)
                self.send_header('DAV', '1')
                self.send_header('Allow', 'OPTIONS, GET, HEAD, PROPFIND, PUT, MKCOL, MOVE, DELETE')
                self.send_header('Content-Length', '0')
                self.end_headers()

            def do_MKCOL(self):
                Path(self.translate_path(self.path)).mkdir()
                self.send_response(201)
                self.end_headers()

            def do_PUT(self):
                if self.headers.get('Transfer-Encoding', '').lower() == 'chunked':
                    data = bytearray()
                    while True:
                        size = int(self.rfile.readline().split(b';')[0], 16)
                        if not size:
                            self.rfile.readline()
                            break
                        data.extend(self.rfile.read(size))
                        self.rfile.read(2)
                else:
                    data = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                Path(self.translate_path(self.path)).write_bytes(data)
                self.send_response(201)
                self.end_headers()

            def do_MOVE(self):
                target = Path(self.translate_path(urlsplit(self.headers['Destination']).path))
                if target.exists():
                    self.send_error(412)
                    return
                Path(self.translate_path(self.path)).rename(target)
                self.send_response(201)
                self.end_headers()

            def do_DELETE(self):
                path = Path(self.translate_path(self.path))
                path.rmdir() if path.is_dir() else path.unlink()
                self.send_response(204)
                self.end_headers()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shared = root / 'shared'
            shared.mkdir()
            (shared / 'Notes.txt').write_text('Read from the network preview.')
            (shared / 'Sub #1').mkdir()
            (shared / 'Sub #1' / 'report.txt').write_text('Nested network search')
            server = ThreadingHTTPServer(('127.0.0.1', 0), partial(DAV, directory=str(shared)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            address = f'webdav://127.0.0.1:{server.server_port}/'
            settings = QSettings(str(root / 'settings.ini'), QSettings.IniFormat)
            catalog = Catalog(Store(root / 'state'))
            window = Window(tmp, settings, catalog)
            errors = []
            window.error = lambda *args: errors.append(args)
            window.show()
            try:
                window.connect_server(address, remember=True)
                self.wait_until(lambda: window.connection_request is None)
                self.assertFalse(errors, errors)
                self.assertEqual(window.current_location, address)
                self.assertEqual(settings.value('network_servers', [], type=list), [address])
                mounted = Path(window.current_path)
                self.assertEqual((mounted / 'Notes.txt').read_text(), 'Read from the network preview.')
                self.wait_until(lambda: window.proxy.rowCount(window.view.rootIndex()) >= 2)
                window.preview.show_path(mounted / 'Notes.txt')
                self.wait_until(lambda: window.preview.proc is None)
                self.assertIn('network preview', window.preview.text.toPlainText())
                window.search.setText('report')
                self.wait_until(lambda: window.results.rowCount() == 1 and window.search_job is None)
                self.assertEqual(window.results.item(0).text(), 'report.txt')
                window.navigate(mounted / 'Sub #1')
                self.wait_until(lambda: window.connection_request is None)
                self.assertEqual(window.current_location, address + 'Sub%20%231')
                window.up()
                self.wait_until(lambda: window.connection_request is None)
                self.assertEqual(window.current_location, address)
                window.history(-1)
                self.wait_until(lambda: window.connection_request is None)
                self.assertEqual(window.current_location, address + 'Sub%20%231')
                window.history(1)
                self.wait_until(lambda: window.connection_request is None)
                self.assertEqual(window.current_location, address)
                (root / 'upload.txt').write_text('Upload through Lumen')
                window.run_operation('copy', [str(root / 'upload.txt')], str(mounted))
                self.wait_until(lambda: window.file_job is None)
                self.assertFalse(errors, errors)
                self.assertEqual((shared / 'upload.txt').read_text(), 'Upload through Lumen')
                (root / 'upload.txt').write_text('Must not replace the existing remote file')
                window.run_operation('copy', [str(root / 'upload.txt')], str(mounted))
                self.wait_until(lambda: window.file_job is None)
                self.assertEqual(len(errors), 1)
                self.assertEqual((shared / 'upload.txt').read_text(), 'Upload through Lumen')
                errors.clear()
                tree = root / 'upload-folder'
                tree.mkdir()
                (tree / 'child.txt').write_text('Recursive upload')
                window.run_operation('copy', [str(tree)], str(mounted))
                self.wait_until(lambda: window.file_job is None)
                self.assertFalse(errors, errors)
                self.assertEqual((shared / 'upload-folder/child.txt').read_text(), 'Recursive upload')
                (root / 'move-me.txt').write_text('Move without loss')
                window.run_operation('move', [str(root / 'move-me.txt')], str(mounted))
                self.wait_until(lambda: window.file_job is None)
                self.assertFalse(errors, errors)
                self.assertEqual((shared / 'move-me.txt').read_text(), 'Move without loss')
                self.assertFalse((root / 'move-me.txt').exists())
                window.run_operation('copy', [str(mounted / 'Notes.txt')], tmp)
                self.wait_until(lambda: window.file_job is None)
                self.assertEqual((root / 'Notes.txt').read_text(), 'Read from the network preview.')
                library = catalog.save_library(None, 'PC und Netz', [
                    {'label': 'PC', 'location': tmp}, {'label': 'Netz', 'location': address}])
                window.navigate(LIBRARY + library['id'])
                self.wait_until(lambda: window.spaces.pending == 0)
                self.assertFalse(window.spaces.errors, window.spaces.errors)
                notes = [window.results.item(i, 4).text() for i in range(window.results.rowCount())
                         if window.results.item(i).text() == 'Notes.txt']
                self.assertEqual(set(notes), {'PC', 'Netz'})
                from unittest.mock import patch
                with patch('assistant_backend.OpenCodeBackend.refresh_sessions'), patch('assistant_backend.OpenCodeBackend.send') as send:
                    window.ask_lumen('open', [])
                    window.assistant.backend.new_conversation(str(mounted))
                    window.assistant.paths = [str(mounted / 'Notes.txt')]
                    room = catalog.save_room(None, 'Netzraum', window.spaces.capture())
                    self.assertEqual(room['state']['chat']['directory'], address)
                    window.assistant.backend.new_conversation(tmp)
                    window.spaces.open_room(room)
                    self.wait_until(lambda: window.spaces.active_room is not None and window.spaces.pending == 0)
                    self.assertEqual(window.spaces.reference(window.assistant.paths[0]), address + 'Notes.txt')
                    self.assertEqual(window.spaces.reference(window.assistant.backend.directory), address)
                    send.assert_not_called()
                window.navigate(tmp)
                # User moves elsewhere while a connect reply is in flight: no late navigation or saving.
                window.connect_server(address + 'Sub%20%231', remember=True)
                window.navigate(tmp)
                QTest.qWait(150)
                self.assertEqual(window.current_location, tmp)
                self.assertEqual(settings.value('network_servers', [], type=list), [address])
                window.new_tab(address)
                self.wait_until(lambda: window.connection_request is None)
                self.assertEqual(window.current_location, address)
                self.assertEqual(window.tabs.count(), 2)
                window.close_tab(1)
                self.assertEqual(window.current_location, tmp)
                window.connect_server(address + 'missing')
                self.wait_until(lambda: window.connection_request is None)
                self.assertTrue(errors)
                self.assertEqual(window.current_location, tmp)
                self.assertEqual(window.current_path, tmp)
                window.connect_server(address)
                self.wait_until(lambda: window.connection_request is None)
                window.close()
                window.deleteLater()
                QTest.qWait(50)
                window = Window(settings=settings, catalog=catalog)
                window.error = lambda *args: errors.append(args)
                window.show()
                self.wait_until(lambda: window.connection_request is None)
                self.assertEqual(window.current_location, address)
                self.assertEqual(window.saved_servers(), [address])
            finally:
                window.close()
                window.deleteLater()
                QTest.qWait(100)
                server.shutdown()
                server.server_close()
                thread.join(2)

    def test_connect_dialog_never_accepts_or_saves_password_urls(self):
        from network import ConnectDialog
        from PyQt5.QtWidgets import QDialog
        dialog = ConnectDialog()
        dialog.address.setText('sftp://alice:secret@host/home/alice')
        dialog.validate()
        self.assertNotEqual(dialog.result(), QDialog.Accepted)
        self.assertIsNone(dialog.url)
        self.assertIn('Passwort', dialog.error.text())
        self.assertNotIn('secret', dialog.error.text())
        dialog.address.setText('nas.local/Team')
        dialog.validate()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(dialog.url, 'smb://nas.local/Team')
        dialog.deleteLater()


if __name__ == '__main__':
    unittest.main()
