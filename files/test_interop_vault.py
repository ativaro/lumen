import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from lumen_store import Store
from tools_data import Library
from tools_ui import Job
import interop_vault as interop
import vault_data as vault


class VaultInteropTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tools = self.root/'tools'
        self.store = Store(self.root/'state')
        self.repo = self.root/'repository'; self.repo.mkdir()
        self.library = Library('vault', self.tools)
        self.plan = self.library.create('Test', repository=str(self.repo), sources=[])
        self.job = Job(lambda _: None)

    def test_discovery_handoff_deduplication_and_boundaries(self):
        notebook = self.root/'notes'; notebook.mkdir(); (notebook/'a.md').write_text('# Saved')
        self.store.set_setting('knowledge/notebook', str(notebook))
        reader = Library('reader', self.tools)
        rows = interop.payload_sources(dict(source=dict(app='wissen')), self.tools, self.store)
        self.assertIn(str(notebook), [r['path'] for r in rows])
        plan = interop.merge_sources(self.library, self.plan, rows, 'lumen://object/'+'a'*32)
        again = interop.merge_sources(self.library, self.plan, rows, 'lumen://object/'+'a'*32)
        self.assertEqual(plan['sources'], again['sources'])
        self.assertEqual(len(again['interop_sources']), 1)
        self.assertEqual(len(again['app_sources']), len(rows))
        with self.assertRaises(ValueError): interop.merge_sources(self.library, self.plan, [str(self.root)])
        self.assertEqual(interop.coverage([notebook/'a.md'], self.tools)[0]['plans'][0]['state'], 'planned')
        other = interop.payload_sources(dict(source=dict(app='reader')), self.tools, self.store)
        self.assertEqual(other[0]['path'], str(reader.root))

    def test_online_database_copy_includes_committed_wal_and_assets(self):
        reader = Library('reader', self.tools)
        connection = sqlite3.connect(reader.db)
        self.addCleanup(connection.close)
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA wal_autocheckpoint=0')
        connection.execute("INSERT INTO records VALUES ('sample','Saved','{}',0,1)"); connection.commit()
        (reader.assets/'picture.txt').write_text('asset')
        rows = [r for r in interop.discover_sources(self.tools, self.store) if r['app'] == 'reader']
        plan = interop.merge_sources(self.library, self.plan, rows)
        with interop.prepared_sources(plan, self.job) as (sources, excludes, manifest):
            bundle = Path(sources[-1]); saved = bundle/'tools/reader/library.sqlite'
            with closing(sqlite3.connect(saved)) as db:
                self.assertEqual(db.execute('SELECT title FROM records').fetchone()[0], 'Saved')
            self.assertEqual((bundle/'tools/reader/assets/picture.txt').read_text(), 'asset')
            self.assertIn(str(reader.root), excludes)
            self.assertEqual(manifest['consistency'], 'committed-databases-and-saved-files')
        self.assertFalse(bundle.exists())

    def test_symlink_and_change_during_copy_fail_without_success(self):
        notebook = self.root/'notes'; notebook.mkdir(); note = notebook/'a.md'; note.write_text('before')
        target = self.root/'copy'
        original = interop._stamp
        def altered(path):
            if target.exists(): note.write_text('after')
            return original(path)
        with patch('interop_vault._stamp', side_effect=altered), self.assertRaises(ValueError):
            interop._copy_source(notebook, target, self.job)
        (notebook/'escape').symlink_to(self.root/'state', target_is_directory=True)
        with self.assertRaises(ValueError): interop._files(notebook)

    def test_cancel_cleans_staging(self):
        reader = Library('reader', self.tools)
        rows = [r for r in interop.discover_sources(self.tools, self.store) if r['app'] == 'reader']
        plan = interop.merge_sources(self.library, self.plan, rows)
        self.job.cancelled.set()
        with self.assertRaises(Exception):
            with interop.prepared_sources(plan, self.job): self.fail('cancelled preparation yielded')

    def test_real_application_backup_and_isolated_verified_restore(self):
        program = os.environ.get('LUMEN_TEST_RESTIC') or vault.binary()
        if not program: self.skipTest('Restic is optional')
        reader = Library('reader', self.tools)
        book = reader.create('Example', page=12, notes=[dict(page=4, text='Remember')], asset='book.txt')
        (reader.assets/'book.txt').write_text('Book content')
        secrets = {}
        def keyring(_namespace, key, value=None):
            if value is not None: secrets[key] = value
            return secrets[key]
        with patch('vault_data.secret', side_effect=keyring), patch('vault_data.binary', return_value=program):
            key = vault.create(self.library, 'Application test', str(self.repo), [str(reader.root)], 'test-password-123456789', self.job)
            interop.merge_sources(self.library, key, [r for r in interop.discover_sources(self.tools, self.store) if r['app'] == 'reader'])
            saved = vault.run(self.library, key, 'backup', self.job)
            self.assertTrue(saved['snapshot_id'])
            self.assertEqual(self.library.get(key)['backup_consistency'], 'committed-databases-and-saved-files')
            versions = interop.file_versions(self.library, key, reader.assets/'book.txt', self.job)
            self.assertEqual(len(versions['versions']), 1)
            self.assertTrue(versions['versions'][0]['path'].endswith('/tools/reader/assets/book.txt'))
            reader.update(book, page=15)
            snapshot = vault.run(self.library, key, 'snapshots', self.job)[0]['id']
            target = vault.run(self.library, key, 'restore', self.job, snapshot=snapshot, destination=str(self.root))
            self.assertEqual(reader.get(book)['page'], 15)
            self.assertEqual(interop.coverage([reader.db], self.tools)[0]['plans'][-1]['state'], 'changed')
            bundles = interop.restored_bundles(target); self.assertEqual(len(bundles), 1)
            restored = Library('reader', Path(bundles[0]['root'])/'tools')
            self.assertEqual(restored.get(book)['page'], 12)
            self.assertEqual(restored.get(book)['notes'][0]['text'], 'Remember')
            self.assertEqual(restored.asset('book.txt').read_text(), 'Book content')
            with patch('subprocess.Popen') as launch:
                interop.open_restored(bundles[0], 'reader')
                self.assertEqual(launch.call_args.kwargs['env']['LUMEN_TOOLS_DATA'], str(Path(bundles[0]['root'])/'tools'))

    def test_restore_manifest_cannot_open_path_outside_restored_directory(self):
        restored = self.root/'restored'; restored.mkdir()
        (restored/interop.MANIFEST).write_text(json.dumps(dict(version=1, sources=[dict(app='reader', slot='../tools')])) )
        self.assertEqual(interop.restored_bundles(restored), [])
        outside = restored/'linked'; outside.symlink_to(self.tools, target_is_directory=True)
        (restored/interop.MANIFEST).write_text(json.dumps(dict(version=1, sources=[dict(app='reader', slot='linked')])))
        self.assertEqual(interop.restored_bundles(restored), [])
        with self.assertRaises(ValueError): interop.open_restored(dict(root=str(restored)), 'reader')

    def test_project_handoff_reports_missing_files_and_restores_links(self):
        from interop_data import Registry
        workbench = Library('workbench', self.tools)
        document = self.root/'document.md'; document.write_text('# Resource')
        missing = self.root/'missing.txt'
        key = workbench.create('Project', resources=[dict(kind='file', target=str(document), title='Document'),
                                                     dict(kind='file', target=str(missing), title='Missing')])
        registry = Registry(self.tools)
        url = registry.register(dict(app='files', kind='file', id=str(document), path=str(document), title='Document'))
        payload = dict(source=dict(app='workbench', id=key))
        rows = interop.payload_sources(payload, self.tools, self.store)
        self.assertTrue(next(row for row in rows if row['path'] == str(missing))['missing'])
        plan = interop.merge_sources(self.library, self.plan, [row for row in rows if not row.get('missing')])
        findings = interop.preflight(plan)
        self.assertEqual([(row['path'], row['reason']) for row in findings], [(str(missing), 'missing')])
        with interop.prepared_sources(plan, self.job) as (sources, _, manifest):
            bundle = Path(sources[-1]); recovered_doc = bundle/'recovered.md'; recovered_doc.write_text('# Resource')
            restored = dict(root=str(bundle), sources=[dict(row, restored=str(bundle/row['slot'])) for row in manifest['sources']],
                            external=[dict(path=str(document), restored=str(recovered_doc))])
            interop.relocate_restored(restored)
            self.assertEqual(Registry(bundle/'tools').resolve(url)['path'], str(recovered_doc))
            self.assertEqual(Library('workbench', bundle/'tools').get(key)['resources'][0]['target'], str(recovered_doc))
            self.assertEqual(registry.resolve(url)['path'], str(document))
            self.assertEqual(workbench.get(key)['resources'][0]['target'], str(document))
            interop.relocate_restored(restored)
            self.assertEqual(Registry(bundle/'tools').resolve(url)['path'], str(recovered_doc))
            escaped = dict(root=str(bundle), sources=[dict(app='workbench', kind='library', path=str(workbench.root), restored=str(workbench.root))])
            with self.assertRaises(ValueError): interop.relocate_restored(escaped)

    def test_reviewed_note_import_preserves_images_history_and_detects_conflicts(self):
        from wissen_data import Notebook, encode
        from PIL import Image
        live = self.root/'live'; live.mkdir()
        self.store.set_setting('knowledge/notebook', str(live))
        book = Notebook(self.store)
        current = book.write('note.md', '# Current\n\nNewer thoughts', '')
        restored = self.root/'restored-notebook'; restored.mkdir(); (restored/'attachments').mkdir()
        Image.new('RGB', (8, 8), 'blue').save(restored/'attachments/photo.png')
        note = restored/'note.md'; note.write_bytes(encode('# Recovered\n\nOlder thoughts ![Picture](attachments/photo.png)', created=1600000000))
        comparison = interop.note_comparison(note, restored, self.store)
        self.assertEqual(comparison['current']['hash'], current['hash'])
        result = interop.import_restored_note(comparison, self.store, current['hash'], self.job)
        self.assertEqual(result['path'], str(live/'note.md'))
        imported = book.read('note.md')
        self.assertEqual(imported['created'], current['created'])
        self.assertIn('# Recovered', imported['text'])
        self.assertNotIn('attachments/photo.png', imported['text'])
        self.assertEqual(len(list((live/'attachments').iterdir())), 1)
        self.assertEqual(len(book.versions('note.md')), 1)
        after_review = interop.note_comparison(note, restored, self.store)
        book.write('note.md', '# Edited during review', imported['hash'])
        with self.assertRaises(ValueError):
            interop.import_restored_note(after_review, self.store, imported['hash'], self.job)
        self.assertEqual(book.read('note.md')['text'], '# Edited during review')
        self.assertEqual(len(list((live/'attachments').iterdir())), 1)
        book.remove('note.md', book.read('note.md')['hash'])
        interop.import_restored_note(interop.note_comparison(note, restored, self.store), self.store, '', self.job)
        self.assertEqual(book.read('note.md')['created'], 1600000000)

    def test_note_import_rejects_escaped_images_and_changed_recovered_file(self):
        from wissen_data import Notebook
        live = self.root/'live'; live.mkdir(); self.store.set_setting('knowledge/notebook', str(live))
        restored = self.root/'restored'; restored.mkdir(); note = restored/'note.md'
        note.write_text('# Recovered\n\n![Escape](../outside.png)')
        comparison = interop.note_comparison(note, restored, self.store)
        with self.assertRaises(ValueError): interop.import_restored_note(comparison, self.store, '', self.job)
        self.assertFalse((live/'note.md').exists())
        note.write_text('# Changed after review')
        with self.assertRaises(ValueError): interop.import_restored_note(comparison, self.store, '', self.job)

    def test_versions_use_snapshot_manifest_not_current_plan_mapping(self):
        document = self.root/'old-notebook/note.md'
        node = '/tmp/staged/Lumen-Anwendungen/notebook/note.md'
        manifest_path = '/tmp/staged/Lumen-Anwendungen/'+interop.MANIFEST
        def operation(_library, _identity, action, _job, **kw):
            if action == 'snapshots': return [dict(id='a'*64, time='2026-10-03T12:00:00Z')]
            if action == 'files': return [dict(type='file', path=node, size=10), dict(type='file', path=manifest_path, size=100)]
            if action == 'manifest': return dict(version=1, sources=[dict(path=str(document.parent), slot='notebook')])
            self.fail(action)
        with patch('vault_data.run', side_effect=operation):
            versions = interop.file_versions(self.library, self.plan, document, self.job)
        self.assertEqual(versions['versions'][0]['path'], node)

    def test_failed_open_app_flush_prevents_snapshot_command(self):
        reader=Library('reader',self.tools);self.library.update(self.plan,sources=[str(reader.root)])
        with patch('vault_data.verify'),patch('vault_data.secret',return_value='synthetic'),patch('vault_data.command') as command,patch('interop_flush.flush_for_plan',side_effect=ValueError('Synthetic conflict')):
            with self.assertRaisesRegex(ValueError,'Synthetic conflict'):vault.run(self.library,self.plan,'backup',self.job)
            command.assert_not_called()
        self.assertNotIn('last_backup',self.library.get(self.plan))


class VaultNativeHandoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls):
        # Dispose Qt-owned windows while Python signal callbacks are still alive.
        from PySide6.QtCore import QCoreApplication, QEvent
        cls.app.closeAllWindows()
        for widget in cls.app.topLevelWidgets(): widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        cls.app.processEvents()

    def test_existing_plan_native_handoff_and_cancel(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QListWidget
        from tools_vault import Vault
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repository = root/'repo'; repository.mkdir()
            window = Vault(root/'tools'); self.addCleanup(window.close)
            source = root/'note.md'; source.write_text('# Note')
            key = window.library.create('Reviewed', repository=str(repository), sources=[])
            window.focus_record(key)
            payload = dict(source=dict(app='files', path=str(source)), paths=[str(source)])
            def accept():
                dialog = QApplication.activeModalWidget()
                self.assertEqual(dialog.findChild(QListWidget).count(), 1)
                dialog.accept()
            completed = []
            QTimer.singleShot(0, accept)
            with patch('vault_data.run') as backup:
                self.assertTrue(interop.receive_sources(window, payload, done=completed.append))
                backup.assert_not_called()
            self.assertEqual(completed[0]['id'], key)
            self.assertEqual(window.library.get(key)['sources'], [str(source)])
            QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
            self.assertFalse(interop.receive_sources(window, payload, done=completed.append))
            self.assertEqual(len(completed), 1)

    def test_created_plan_receipt_survives_registry_failure_without_second_review(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QDialog
        from tools_vault import Vault
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repository = root/'repo'; repository.mkdir()
            window = Vault(root/'tools'); self.addCleanup(window.close)
            source = root/'note.md'; source.write_text('# Note')
            payload = dict(source=dict(app='files', path=str(source)), paths=[str(source)])
            token = 'a'*32
            def create(prefill_sources, on_done, source_ref, handoff):
                key = vault.create(window.library, 'Reviewed', repository, [row['path'] for row in prefill_sources],
                                   'temporary-secret-only', Job(lambda _:None), app_sources=prefill_sources,
                                   source_ref=source_ref, handoff=handoff)
                on_done(key)
                return True
            QTimer.singleShot(0, lambda: QApplication.activeModalWidget().accept())
            with patch.object(window, 'create', side_effect=create), patch('vault_data.command', return_value='{"id":"synthetic"}'), patch('vault_data.secret'):
                with self.assertRaisesRegex(RuntimeError, 'Registry write failed'):
                    interop.receive_sources(window, payload, token=token,
                        done=lambda ref: (_ for _ in ()).throw(RuntimeError('Registry write failed')))
            self.assertEqual(len(window.library.all()), 1)
            source.unlink()  # A replay acknowledges the durable mutation, not a new source review.
            completed = []
            with patch.object(window, 'create', side_effect=AssertionError('No duplicate plan')), patch.object(QDialog, 'exec', side_effect=AssertionError('No repeated review')):
                self.assertTrue(interop.receive_sources(window, payload, token=token, done=completed.append))
            self.assertEqual(completed[0]['id'], window.library.all()[0]['id'])
            with self.assertRaises(ValueError):
                interop.receive_sources(window, dict(payload, title='Changed request'), token=token)

    def test_merged_plan_and_receipt_are_durable_together(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); library = Library('vault', root/'tools')
            repository = root/'repo'; repository.mkdir(); source = root/'note.md'; source.write_text('note')
            key = library.create('Reviewed', repository=str(repository), sources=[])
            interop.merge_sources(library, key, [str(source)], token='b'*32, signature='same')
            self.assertEqual(interop.handoff_receipt(library, 'b'*32, 'same')['id'], key)
            self.assertEqual(library.get(key)['sources'], [str(source)])
            library.archive(key)
            with self.assertRaises(ValueError): interop.handoff_receipt(library, 'b'*32, 'same')

    def test_file_versions_dialog_works_with_plain_files_parent(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QWidget, QListWidget, QPushButton
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); library = Library('vault', root/'tools')
            document = root/'selected.txt'; document.write_text('Document')
            key = library.create('Selected backup', sources=[str(document)], repository=str(root/'repo'))
            parent = QWidget(); failures = []
            def perform(_parent, _title, function, done):
                done(dict(versions=[dict(time='2026-10-03T12:00:00Z', size=8, snapshot='a'*64, plan=key, path=str(document))], next_offset=None))
            def inspect():
                dialog = QApplication.activeModalWidget()
                try:
                    more = next(button for button in dialog.findChildren(QPushButton) if button.text() == 'Weitere Sicherungsstände laden')
                    more.click()
                    self.assertEqual(dialog.findChild(QListWidget).count(), 1)
                    self.assertFalse(more.isEnabled())
                except Exception as error: failures.append(error)
                finally: dialog.reject()
            QTimer.singleShot(0, inspect)
            with patch('interop_vault._run_job', side_effect=perform): interop.show_file_versions(parent, document, root/'tools')
            parent.close(); self.assertFalse(failures, failures)

    def test_standalone_worker_delivers_after_finishing(self):
        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QWidget
        parent = QWidget(); loop = QEventLoop(); completed = []
        def done(value): completed.append(value); loop.quit()
        runner = interop._run_job(parent, 'Synthetic job', lambda job: 42, done)
        timeout = QTimer(); timeout.setSingleShot(True); timeout.timeout.connect(loop.quit); timeout.start(3000)
        loop.exec(); timeout.stop()
        self.assertEqual(completed, [42]); parent.close()

    def test_detected_project_gap_is_reviewed_before_manual_backup(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication,QMessageBox
        from tools_vault import Vault
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);workbench=Library('workbench',root)
            workbench.create('Project',resources=[dict(kind='file',title='Missing',target=str(root/'missing.txt'))])
            window=Vault(root)
            key=window.library.create('Reviewed',repository=str(root/'repo'),sources=[str(workbench.root)],app_sources=[dict(app='workbench',path=str(workbench.root),slot='tools/workbench',kind='library')])
            window.focus_record(key)
            QTimer.singleShot(0,lambda:QApplication.activeModalWidget().done(QMessageBox.Cancel))
            with patch.object(window,'work') as work:window.action('backup');work.assert_not_called()
            window.close()

    def test_task_handoff_explicitly_offers_selective_inbox_backup(self):
        import inbox_data
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication,QCheckBox
        from tools_vault import Vault
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);inbox_data.store(root);repository=root/'repo';repository.mkdir()
            window=Vault(root);key=window.library.create('Inbox locals',repository=str(repository),sources=[]);window.focus_record(key)
            def accept():
                dialog=QApplication.activeModalWidget();self.assertTrue(dialog.findChild(QCheckBox).isChecked());dialog.accept()
            QTimer.singleShot(0,accept)
            interop.receive_sources(window,dict(source=dict(app='inbox',kind='task',id='synthetic',title='Task')))
            self.assertEqual(window.library.get(key)['app_sources'][0]['kind'],'inbox-local');window.close()


if __name__ == '__main__': unittest.main()
