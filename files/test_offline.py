import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from lumen_store import Store
from lumen_offline import pin, sync, PREFIX


class OfflineTest(unittest.TestCase):
    def test_three_way_conflict_delete_and_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'state'); remote = Path(tmp) / 'nas'; remote.mkdir()
            (remote / 'photo.txt').write_text('first'); (remote / 'empty').mkdir()
            item = pin(store, 'smb://example.test/photos'); local = Path(item['local'])
            sync(store, item['id'], remote)
            self.assertEqual((local / 'photo.txt').read_text(), 'first')
            self.assertTrue((local / 'empty').is_dir()); (remote / 'empty').rmdir()
            sync(store, item['id'], remote); self.assertFalse((local / 'empty').exists())
            (local / 'photo.txt').write_text('on laptop'); (remote / 'photo.txt').write_text('on NAS')
            result = sync(store, item['id'], remote); conflict = result['conflicts'][0]
            self.assertEqual((remote / 'photo.txt').read_text(), 'on NAS')
            # An obsolete choice is refused after a fresh remote edit.
            (remote / 'photo.txt').write_text('later NAS')
            result = sync(store, item['id'], remote, {'photo.txt': dict(conflict, use='local')})
            self.assertTrue(result['conflicts'])
            result = sync(store, item['id'], remote, {'photo.txt': dict(result['conflicts'][0], use='local')})
            self.assertFalse(result['conflicts']); self.assertEqual((remote / 'photo.txt').read_text(), 'on laptop')
            backups = store.directory / 'offline' / item['id'] / 'replaced'
            self.assertIn('later NAS', [p.read_text() for p in backups.iterdir()])
            (local / 'photo.txt').unlink(); sync(store, item['id'], remote)
            self.assertFalse((remote / 'photo.txt').exists())
            (local / 'new.txt').write_text('new'); remote.rmdir()
            with self.assertRaises(ValueError): sync(store, item['id'], remote)
            self.assertEqual((local / 'new.txt').read_text(), 'new')
            remote.mkdir(); (remote / 'link').symlink_to(local / 'new.txt')
            with self.assertRaises(ValueError): sync(store, item['id'], remote)
            self.assertNotIn('new.txt', store.setting(PREFIX + item['id'])['base'])

    def test_disconnected_replaced_root_never_advances_sync_baseline(self):
        import lumen_offline
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'state'); remote=Path(tmp)/'nas'; remote.mkdir(); (remote/'a.txt').write_text('original')
            item=pin(store,'smb://example.test/files'); sync(store,item['id'],remote)
            local=Path(item['local']); (local/'a.txt').write_text('offline edit')
            original=store.setting(PREFIX+item['id'])['base'].copy(); replace=lumen_offline.replace_file
            def replaced(*args,**kwargs):
                replace(*args,**kwargs); remote.rename(Path(tmp)/'disconnected'); remote.mkdir()
            with patch.object(lumen_offline,'replace_file',side_effect=replaced):
                with self.assertRaises(ValueError): sync(store,item['id'],remote)
            self.assertEqual(store.setting(PREFIX+item['id'])['base'],original)
            self.assertEqual((local/'a.txt').read_text(),'offline edit')

    def test_worker_and_native_folder_view(self):
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QSettings
        from app import Window
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp + '/state'}):
            remote = Path(tmp) / 'nas'; remote.mkdir(); (remote / 'example.txt').write_text('hello')
            window = Window(tmp, QSettings(tmp + '/files.ini', QSettings.IniFormat))
            controller = window.offline; controller.timer.stop()
            item = pin(controller.store, 'smb://example.test/folder')
            controller.active = item; controller.choices = {}; controller.connected(item['remote'], str(remote))
            deadline = time.monotonic() + 10
            while controller.active and time.monotonic() < deadline: app.processEvents(); time.sleep(.01)
            self.assertIsNone(controller.active)
            self.assertEqual((Path(item['local']) / 'example.txt').read_text(), 'hello')
            controller.show(); app.processEvents()
            self.assertEqual(controller.dialog.list.count(), 1)
            controller.dialog.open_local(); self.assertEqual(window.current_path, item['local'])
            window.close(); app.processEvents()
            # The delayed initial refresh must not restart a closed controller.
            with patch('offline_ui.folders',side_effect=AssertionError('Closed controller read its database')):
                controller.refresh()
