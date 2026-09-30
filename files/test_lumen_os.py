import tempfile
import unittest
from pathlib import Path


class LumenOSTest(unittest.TestCase):
    def test_persistent_tasks_changes_and_conflict_safe_undo(self):
        from lumen_store import Store
        from lumen_actions import execute, undo
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); work = root / 'work'; work.mkdir()
            store = Store(root / 'state')
            task = store.create_task('Bericht', directory=str(work), roots=[str(work)],
                                     steps=[{'action': 'write', 'path': str(work / 'result.md'), 'text': 'Ergebnis'}])
            self.assertEqual(Store(root / 'state').task(task)['title'], 'Bericht')
            with self.assertRaises(PermissionError):
                execute(store, task, store.task(task)['steps'][0])
            store.update_task(task, approved=True, status='running')
            execute(store, task, store.task(task)['steps'][0])
            self.assertEqual((work / 'result.md').read_text(), 'Ergebnis')
            change = store.changes(task)[0]
            (work / 'result.md').write_text('Extern geändert')
            with self.assertRaises(ValueError): undo(store, change['id'])
            self.assertEqual((work / 'result.md').read_text(), 'Extern geändert')
            (work / 'result.md').write_text('Ergebnis')
            (work / 'result.md').chmod(0o644)
            with self.assertRaises(ValueError): undo(store, change['id'])
            (work / 'result.md').chmod(0o600)
            undo(store, change['id'])
            self.assertFalse((work / 'result.md').exists())
            store.update_task(task, status='cancelled')
            with self.assertRaises(PermissionError): execute(store, task, store.task(task)['steps'][0])
            store.update_task(task, status='running')
            lease = store.acquire(task)
            store.recover()
            self.assertEqual(store.task(task)['status'], 'running')
            import os
            os.close(lease)
            Store(root / 'state').recover()
            self.assertEqual(store.task(task)['status'], 'interrupted')
            with self.assertRaises(PermissionError):
                execute(store, task, {'action': 'write', 'path': str(root / 'outside'), 'text': 'x'})
            (work / 'escape').symlink_to(root, target_is_directory=True)
            with self.assertRaises((PermissionError, OSError)):
                execute(store, task, {'action': 'write', 'path': str(work / 'escape' / 'outside'), 'text': 'x'})

    def test_workflow_due_once_pause_and_restart(self):
        from lumen_store import Store
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'state')
            flow = store.save_workflow('Ordner öffnen', [{'action': 'open', 'path': tmp}], [tmp],
                                      trigger='interval', interval=60, enabled=True, approved=True, now=100)
            self.assertEqual(store.enqueue_due(now=159), [])
            tasks = store.enqueue_due(now=160)
            self.assertEqual(len(tasks), 1)
            self.assertEqual(store.enqueue_due(now=160), [])
            self.assertTrue(store.task(tasks[0])['approved'])
            self.assertEqual(store.enqueue_due(now=220), [])
            with self.assertRaises(PermissionError):
                store.save_workflow('Ungeprüft', [{'action':'diagnose'}], [tmp], enabled=True)
            with self.assertRaises(BlockingIOError):
                lease = store.acquire(tasks[0])
                try: store.acquire(tasks[0])
                finally:
                    import os
                    os.close(lease)
            store.set_workflow_enabled(flow, False)
            self.assertEqual(Store(Path(tmp) / 'state').enqueue_due(now=300), [])

    def test_knowledge_roots_and_memories(self):
        from lumen_store import Store
        from lumen_knowledge import index_root, search
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); shared = root / 'shared'; shared.mkdir()
            (shared / 'invoice.txt').write_text('Rechnung Monitor 500 Franken')
            (shared / 'passwords.txt').write_text('Monitor geheim')
            (shared / '.secret.txt').write_text('Monitor Passwort')
            (root / 'private.txt').write_text('Monitor Geheimnis')
            (shared / 'escape.txt').symlink_to(root / 'private.txt')
            store = Store(root / 'state')
            index_root(store, str(shared))
            rows = search(store, 'Monitor')
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['path'], str(shared / 'invoice.txt'))
            self.assertIn('Rechnung', rows[0]['snippet'])
            memory = store.save_memory('Arbeitsplatz', 'Monitor links', source='Von mir')
            self.assertEqual(store.memories()[0]['id'], memory)
            store.delete_memory(memory)
            store.remove_root(str(shared / '..' / 'shared'))
            self.assertEqual(search(store, 'Monitor'), [])
            self.assertEqual(store.memories(), [])

    def test_migration_preserves_originals_newer_files_and_symlinks(self):
        from lumen_migrate import copy_missing
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); old=root/'old';new=root/'new';old.mkdir();new.mkdir()
            (old/'report.md').write_text('old');(old/'missing.md').write_text('keep')
            (new/'report.md').write_text('new');(old/'link').symlink_to(root)
            copy_missing(old,new);copy_missing(old,new)
            self.assertEqual((new/'report.md').read_text(),'new')
            self.assertEqual((new/'missing.md').read_text(),'keep')
            self.assertTrue((old/'missing.md').exists());self.assertFalse((new/'link').exists())

    def test_model_policy_rejects_cloud_and_honors_limits(self):
        from lumen_models import select_model
        providers = [{'id': 'local', 'options': {'baseURL': 'http://127.0.0.1:11434/v1'}, 'models': {'small': {}}},
                     {'id': 'cloud', 'options': {'baseURL': 'https://example.com'}, 'models': {'big': {}}}]
        self.assertEqual(select_model({'privacy': 'local', 'local_model': 'local/small'}, providers), 'local/small')
        with self.assertRaises(ValueError):
            select_model({'privacy': 'local', 'local_model': 'cloud/big'}, providers)
        with self.assertRaises(ValueError):
            select_model({'privacy': 'local', 'local_model': 'local/small'}, [])



class LumenIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()

    def test_native_pages_workflow_result_and_source_context(self):
        import importlib.util
        import os
        import time
        from unittest.mock import patch
        from PyQt5.QtCore import QSettings
        from PyQt5.QtTest import QTest
        from lumen_knowledge import index_root
        spec = importlib.util.spec_from_file_location('lumen_desktop_test', Path(__file__).resolve().parents[1] / 'agent-app/main.py')
        desktop = importlib.util.module_from_spec(spec); spec.loader.exec_module(desktop)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp + '/state'}):
            settings = QSettings(tmp + '/desktop.ini', QSettings.IniFormat)
            with patch.object(desktop, 'QSettings', return_value=settings): window = desktop.LumenWindow(tmp)
            window.chat.backend.refresh_sessions = lambda: None
            try:
                window.show()
                for index in range(8): window.show_page(index); QTest.qWait(15)
                self.assertEqual(window.file_window.window(), window)
                space = window.workspace
                space.store.set_setting('modelPolicy', {'gpu_limit': 100})
                flow = space.store.save_workflow('Bericht', [{'action': 'write', 'path': tmp+'/bericht.md', 'text': 'Prüfung bestanden'}], [tmp], trigger='interval', interval=60, enabled=True, approved=True, now=0)
                space.tick()
                deadline = time.monotonic()+10
                while space.processes and time.monotonic() < deadline: QTest.qWait(20)
                self.assertFalse(space.processes)
                self.assertEqual(Path(tmp+'/bericht.md').read_text(), 'Prüfung bestanden')
                self.assertEqual(space.store.tasks()[0]['status'], 'completed')
                index_root(space.store, tmp)
                space.query.setText('bestanden'); space.search()
                self.assertEqual(space.results.count(), 1)
                space.results.setCurrentRow(0); space.use_source()
                self.assertIn('bericht.md', window.chat.composer.toPlainText())
                self.assertEqual(window.chat.paths, [tmp+'/bericht.md'])
                self.assertFalse(window.chat.backend.busy)
            finally:
                window.close(); window.deleteLater(); QTest.qWait(30)

    def test_local_policy_blocks_prompt_before_remote_submission(self):
        import os
        from unittest.mock import patch
        from assistant_backend import OpenCodeBackend
        from lumen_store import Store
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp+'/state'}):
            Store().set_setting('modelPolicy', {'privacy':'local','local_model':'remote/model','timeout_seconds':60})
            backend = OpenCodeBackend(tmp); calls = []; failed = []
            backend.failed.connect(failed.append); backend.ensure_server = lambda cb: cb()
            def request(method, path, body=None, callback=None, **kwargs):
                calls.append((method,path))
                if path == '/config': callback({'provider': {'remote': {'options': {'baseURL':'https://example.com'}}}})
                elif path == '/config/providers': callback({'providers':[{'id':'remote','models':{'model':{}}}]})
            backend.request = request
            backend.send('Privat bleiben')
            self.assertTrue(failed)
            self.assertFalse(any(method == 'POST' for method, path in calls))
            self.assertFalse(backend.busy); backend.shutdown()


if __name__ == '__main__':
    unittest.main()
