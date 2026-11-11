"""Backups retain their library, references and operation guards inside System."""
import unittest
import os
import time
import shutil
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QDialog
from PySide6.QtTest import QTest
from PySide6.QtGui import QCloseEvent
import test_system_integration as integration


class SystemBackupsTest(unittest.TestCase):
    setUpClass = classmethod(integration.SystemIntegrationTest.setUpClass.__func__)
    setUp = integration.SystemIntegrationTest.setUp
    tearDown = integration.SystemIntegrationTest.tearDown

    def test_retained_plan_and_shared_library_without_scheduling_on_open(self):
        page = self.window.backups
        from tools_data import Library
        previous = Library('vault', self.root/'tools')
        key = previous.create('Existing plan', repository='/offline/backup', sources=['/synthetic/documents'], interval=86400)
        original = previous.get(key)
        with patch('vault_data.schedule') as schedule, patch('vault_data.run') as run:
            self.window.select('backups'); page.refresh(); page.focus_record(key)
            self.window.select('system'); self.window.select('backups')
            self.assertEqual(page.current, key)
            self.assertEqual(page.library.get(key), original)
            schedule.assert_not_called(); run.assert_not_called()
        self.assertFalse(page.sections.isVisible())

    def test_backup_job_prevents_close_without_implicit_cancel(self):
        page = self.window.backups; page.job = Mock()
        try:
            event = QCloseEvent(); self.window.closeEvent(event)
            self.assertFalse(event.isAccepted())
            self.assertIs(self.window.tabs.currentWidget(), page)
            page.job.cancel.assert_not_called()
        finally: page.job = None

    def test_archive_disables_schedule_and_preserves_repository(self):
        from PySide6.QtWidgets import QMessageBox
        page = self.window.backups
        key = page.library.create('Scheduled', repository='/offline/backup', sources=['/synthetic'], interval=86400)
        page.focus_record(key)
        def schedule(library, identity, interval, job):
            library.update(identity, interval=interval)
        with patch('tools_vault.QMessageBox.question', return_value=QMessageBox.No), patch('vault_data.schedule') as disable:
            page.archive(); disable.assert_not_called()
        with patch('tools_vault.QMessageBox.question', return_value=QMessageBox.Yes), patch('vault_data.schedule', side_effect=schedule) as disable:
            page.archive()
            deadline = time.monotonic()+5
            while page.job and time.monotonic()<deadline: QTest.qWait(10)
            self.assertIsNone(page.job)
            disable.assert_called_once()
        archived = page.library.all(archived=True)
        self.assertEqual([row['id'] for row in archived], [key])
        self.assertEqual(archived[0]['interval'], 0)
        self.assertEqual(archived[0]['repository'], '/offline/backup')

    def test_coverage_requires_matching_backup_sources(self):
        page = self.window.backups
        plan = dict(title='Coverage', repository='/offline', sources=['/a'], groups={'files':['/a']}, backup_groups={'files':['/a']}, backup_sources=['/a'])
        page.load(plan)
        self.assertIn('Wiederherstellungsprobe erfolgreich', page.details.text())
        page.load(dict(plan, sources=['/a','/b']))
        self.assertNotIn('Wiederherstellungsprobe erfolgreich', page.details.text())
        self.assertIn('nächste Sicherung ausstehend', page.details.text())

    def test_reference_routes_to_backup_controller(self):
        request = {'ref': 'lumen://synthetic-reference'}
        with patch('interop_ui.controller') as controller:
            self.window.activate_backup(request)
            controller.assert_called_once_with(self.window.backups)
            controller.return_value.enqueue.assert_called_once_with(request)
        self.assertIs(self.window.tabs.currentWidget(), self.window.backups)
        with self.assertRaises(ValueError): self.window.activate_backup([])

    def test_cancel_setup_preserves_existing_plans(self):
        page = self.window.backups
        with patch('vault_data.binary', return_value='/synthetic/restic'), patch('tools_vault.QDialog.exec', return_value=QDialog.Rejected):
            self.assertFalse(page.create())
        self.assertEqual(page.library.all(), [])
        self.assertIsNone(page.job)

    def test_real_object_reference_selects_existing_plan(self):
        from interop_data import Registry
        page = self.window.backups
        key = page.library.create('Linked plan', repository='/offline/backup', sources=['/synthetic/documents'], interval=0)
        url = Registry(page.library.root.parent).register(dict(app='vault', kind='record', id=key, title='Linked plan'))
        self.window.activate_backup({'ref': url})
        QTest.qWait(350)
        self.assertEqual(page.current, key)

    def test_launcher_keeps_secrets_and_backup_targets_separate(self):
        folder = self.root/'install/bin'; folder.mkdir(parents=True)
        shutil.copy2(Path(__file__).resolve().parents[1]/'bin/lumen-vault', folder/'lumen-vault')
        files = folder.parent/'files'; files.mkdir()
        for name in ('tools_app.py', 'vault_preview.py', 'vault_service.py'): (files/name).touch()
        python = folder/'lumen-python'; python.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n'); python.chmod(0o755)
        data = self.root/'appdata'; native = data/'lumen/vault-lab/bin/lumen-vault-lab'
        native.parent.mkdir(parents=True); native.write_text('#!/bin/sh\nprintf "native\\n%s\\n" "$@"\n'); native.chmod(0o755)
        def launch(*args):
            return subprocess.check_output([str(folder/'lumen-vault'), *args], env=dict(os.environ, XDG_DATA_HOME=str(data)), text=True).splitlines()
        system = folder/'lumen-system'; system.write_text('#!/bin/sh\necho system\nprintf "%s\\n" "$@"\n'); system.chmod(0o755)
        self.assertEqual(launch(), [str(files/'tools_app.py').replace('/files/', '/bin/../files/'), 'vault'])
        self.assertEqual(launch('--lab'), ['native', '--laboratory-only'])
        self.assertEqual(launch('--backups'), ['system', '--page', 'backups'])
        self.assertEqual(launch('--ref', 'lumen://example')[-3:], ['vault', '--ref', 'lumen://example'])
        self.assertTrue(launch('--backup-service')[0].endswith('/vault_service.py'))
        self.assertTrue(launch('--preview')[0].endswith('/vault_preview.py'))
        native.unlink()
        with self.assertRaises(subprocess.CalledProcessError): launch('--lab')

    def test_real_backup_and_selective_restore_in_system(self):
        import vault_data as vault
        from lumen_jobs import Job
        program = os.environ.get('LUMEN_TEST_RESTIC') or vault.binary()
        if not program: self.skipTest('A local restic binary is required')
        source, repo, restored = [self.root/name for name in ('source', 'repo', 'restored')]
        for folder in (source, repo, restored): folder.mkdir()
        (source/'sample.txt').write_text('SYNTHETIC CONTENT')
        (source/'other.txt').write_text('DO NOT RESTORE')
        keys = {}
        def secret(app, identity, value=None):
            if value is not None: keys[identity] = value
            return keys[identity]
        page = self.window.backups
        def wait():
            deadline = time.monotonic()+25
            while page.job and time.monotonic() < deadline: QTest.qWait(25)
            self.assertIsNone(page.job)
        try:
            with patch('vault_data.binary', return_value=program), patch('vault_data.secret', side_effect=secret):
                key = vault.create(page.library, 'Synthetic', str(repo), [str(source)], 'SYNTHETIC ONLY', Job(lambda _: None))
                self.window.select('backups'); page.focus_record(key)
                page.action('backup'); wait()
                self.assertIn('erfolgreich', page.status.text())
                page.action('snapshots'); wait()
                self.assertEqual(page.snapshots.topLevelItemCount(), 1)
                page.snapshots.setCurrentItem(page.snapshots.topLevelItem(0))
                with patch('tools_vault.QFileDialog.getExistingDirectory', return_value=str(restored)), patch('interop_vault.show_restored'):
                    page.restore_selected(page.selected(), str(source/'sample.txt')); wait()
                self.assertEqual(next(restored.rglob('sample.txt')).read_text(), 'SYNTHETIC CONTENT')
                self.assertFalse(list(restored.rglob('other.txt')))
                self.assertEqual((source/'sample.txt').read_text(), 'SYNTHETIC CONTENT')
                self.assertEqual(page.library.get(key)['interval'], 0)
        finally:
            if page.job:
                page.cancel(); wait()
