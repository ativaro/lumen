import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QWizard
from PySide6.QtTest import QTest
from backup_setup_ui import NetworkPicker, export_key, BackupWizard
from tools_data import Library


class SetupUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def test_network_selection_invalidates_and_credentials_do_not_cross_hosts(self):
        calls = []
        picker = NetworkPicker(lambda args, done, fail: calls.append((args, done, fail)))
        self.addCleanup(picker.close)
        picker.uri.setText('smb://one/share'); picker.user.setText('test'); picker.password.setText('synthetic')
        picker.perform('test'); calls[-1][1](dict(path='/synthetic/mount', uri='smb://one/share', network_id='saved'))
        self.assertEqual(picker.password.text(), '')
        self.assertEqual(picker.selection['network_id'], 'saved')
        picker.uri.setText('smb://two/share')
        self.assertEqual(picker.selection, {}); self.assertEqual(picker.user.text(), '')
        picker.perform('test'); self.assertEqual(calls[-1][0]['network_id'], '')
        calls[-1][2]('Offline'); self.assertEqual(picker.status.text(), 'Offline')

    def test_key_export_is_private_and_outside_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); target = root/'backup'; target.mkdir()
            with self.assertRaises(ValueError): export_key(target/'key', str(target), 'SYNTHETIC')
            linked = root/'linked'; linked.symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError): export_key(linked/'key', str(target), 'SYNTHETIC')
            path = root/'key'; export_key(path, str(target), 'SYNTHETIC')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.read_text(), 'SYNTHETIC')

    def wait(self, wizard):
        deadline = time.monotonic()+30
        QTest.qWait(25)
        while wizard.job and time.monotonic()<deadline: QTest.qWait(10)
        self.assertIsNone(wizard.job)

    def wizard(self, root, execute):
        self.enterContext(patch('backup_setup_ui.execute', side_effect=execute))
        wizard = BackupWizard(Library('vault', root))
        wizard.show(); self.addCleanup(wizard.close); self.wait(wizard)
        return wizard

    def test_checked_target_invalidates_on_edit_and_failed_server_does_not_advance(self):
        calls = []
        target = dict(server='https://example.invalid', device_id='synthetic')
        def execute(lib, args, job):
            calls.append(dict(args))
            if args['op']=='setup_inventory':
                return dict(files=[], lumen=[], vault=[], servers=[dict(label='Test server', server_target=target)])
            if args.get('server_target'): raise ValueError('Server offline')
            return dict(path=args['path'], existing=False, tested=True)
        with tempfile.TemporaryDirectory() as root:
            wizard = self.wizard(root, execute); wizard.next()
            wizard.target.setText('/synthetic/one'); wizard.next(); self.wait(wizard)
            self.assertEqual(wizard.currentId(), 2)
            wizard.back(); wizard.target.setText('/synthetic/two')
            self.assertEqual(wizard.destination, {})
            wizard.kind.setCurrentIndex(2); wizard.next(); self.wait(wizard)
            self.assertEqual(wizard.currentId(), 1)
            self.assertIn('offline', wizard.page(1).status.text())
            self.assertEqual(calls[-1]['server_target'], target)

    def test_finish_retry_reuses_prepared_plan_and_does_not_reconfigure(self):
        calls = []; attempts = []
        def execute(lib, args, job):
            calls.append(dict(args))
            if args['op']=='setup_inventory': return dict(files=[dict(path='/synthetic/source',label='Source')], lumen=[], vault=[], servers=[])
            if args['op']=='test_target': return dict(path=args['path'], existing=False)
            if args['op']=='configure': return dict(id='a'*32, prepared=True)
            if args['op']=='finish_setup':
                attempts.append(True)
                if len(attempts)==1: raise ValueError('Offline')
                return dict(verified=True)
        with tempfile.TemporaryDirectory() as root:
            wizard = self.wizard(root, execute); wizard.next(); wizard.target.setText('/synthetic/destination')
            wizard.next(); self.wait(wizard); wizard.saved.setChecked(True); wizard.next(); wizard.accept(); self.wait(wizard)
            self.assertEqual(wizard.plan_id, 'a'*32); self.assertFalse(wizard.completed)
            self.assertFalse(wizard.button(QWizard.WizardButton.BackButton).isEnabled())
            wizard.accept(); self.wait(wizard)
            self.assertTrue(wizard.completed); self.assertEqual(wizard.key.text(), '')
            self.assertEqual(sum(c['op']=='configure' for c in calls), 1)
            self.assertEqual(len(attempts), 2)

    def test_cancel_waits_for_worker_and_keeps_a_returned_prepared_plan(self):
        def execute(lib, args, job):
            if args['op']=='setup_inventory': return dict(files=[], lumen=[], vault=[], servers=[])
            time.sleep(.12)
            return dict(id='b'*32, prepared=True)
        with tempfile.TemporaryDirectory() as root:
            wizard = self.wizard(root, execute)
            wizard.work(dict(op='configure'), lambda _: self.fail('Cancelled setup must not start backup'))
            wizard.close(); self.assertIsNotNone(wizard.job); self.assertTrue(wizard.isVisible()); self.wait(wizard)
            self.assertEqual(wizard.plan_id, 'b'*32); self.assertFalse(wizard.isVisible())
            self.assertEqual(wizard.key.text(), '')

    def test_network_destination_and_only_selected_remote_sources_are_configured(self):
        calls = []
        def execute(lib, args, job):
            calls.append(dict(args))
            if args['op']=='setup_inventory': return dict(files=[], lumen=[], vault=[], servers=[])
            if args['op']=='network': return dict(path='/mount/target', uri='smb://nas/target', network_id='target-access')
            if args['op']=='configure': return dict(id='c'*32, prepared=True)
            return dict(verified=True)
        with tempfile.TemporaryDirectory() as root:
            wizard = self.wizard(root, execute)
            wizard.append_source('files', '/mount/source', 'NAS source')
            wizard.remotes = [dict(path='/mount/source', uri='smb://nas/source', network_id='source-access'),
                              dict(path='/mount/unselected', uri='smb://nas/unselected', network_id='other')]
            wizard.next(); wizard.kind.setCurrentIndex(1)
            wizard.next(); self.assertEqual(wizard.currentId(), 1)
            wizard.network.uri.setText('smb://nas/target'); wizard.network.perform('test'); self.wait(wizard)
            wizard.next(); wizard.saved.setChecked(True); wizard.next(); wizard.accept(); self.wait(wizard)
            configured = next(c for c in calls if c['op']=='configure')
            self.assertEqual(configured['network_uri'], 'smb://nas/target')
            self.assertEqual(configured['network_id'], 'target-access')
            self.assertEqual(configured['remote_sources'], wizard.remotes[:1])

    def test_system_close_keeps_setup_window_and_worker_alive(self):
        from unittest.mock import Mock
        from PySide6.QtGui import QCloseEvent
        from system_window import SystemWindow
        window = Mock(); event = QCloseEvent()
        SystemWindow.closeEvent(window, event)
        self.assertFalse(event.isAccepted())
        window.backups.setup_dialog.raise_.assert_called_once()
        window.backups.setup_dialog.activateWindow.assert_called_once()
        window.backups.setup_dialog.reject.assert_not_called()

    def test_prepared_plan_can_resume_after_reopening_system_page(self):
        from tools_vault import Vault
        with tempfile.TemporaryDirectory() as tmp:
            page = Vault(Path(tmp), embedded=True); self.addCleanup(page.close); page.show()
            key = page.library.create('Pending', repository='/synthetic/repo', sources=[], setup_pending=True)
            page.focus_record(key); self.assertTrue(page.resume_setup.isVisible())
            def finish(library, identity, job):
                self.assertEqual(identity, key); library.update(identity, setup_pending=False)
                return dict(verified=True)
            with patch('backup_setup.finish_setup', side_effect=finish) as resume:
                page.resume_setup.click(); self.wait(page); resume.assert_called_once()
            self.assertEqual(page.current, key); self.assertFalse(page.resume_setup.isVisible())

    def test_real_wizard_backup_and_adoption(self):
        import backup_setup
        import vault_data as vault
        from vault_service import execute
        program = os.environ.get('LUMEN_TEST_RESTIC') or vault.binary()
        if not program: self.skipTest('Restic required')
        passwords = {}
        def secret(app, identity, value=None):
            if value is not None: passwords[identity] = value
            return passwords[identity]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root/'source'; source.mkdir(); target = root/'target'; target.mkdir()
            (source/'example.txt').write_text('SYNTHETIC WIZARD CONTENT')
            self.enterContext(patch('vault_data.binary', return_value=program))
            self.enterContext(patch('vault_data.secret', side_effect=secret))
            self.enterContext(patch('backup_setup.inventory', return_value=dict(
                files=[dict(path=str(source), label='Synthetic')], lumen=[], vault=[], servers=[])))
            schedule = self.enterContext(patch('vault_data.schedule'))
            wizard = self.wizard(root/'tools', execute)
            wizard.next(); wizard.target.setText(str(target)); wizard.next(); self.wait(wizard)
            wizard.key.setText('SYNTHETIC WIZARD KEY'); wizard.saved.setChecked(True)
            wizard.schedule.setCurrentIndex(2); wizard.next(); wizard.accept(); self.wait(wizard)
            self.assertTrue(wizard.completed)
            plan = wizard.library.get(wizard.plan_id)
            self.assertFalse(plan['setup_pending']); self.assertGreater(plan['last_restore_probe'], 0)
            self.assertNotIn(b'SYNTHETIC WIZARD KEY', wizard.library.db.read_bytes())
            schedule.assert_called_once(); wizard.accept()
            adopted = self.wizard(root/'recovery', execute)
            adopted.next(); adopted.target.setText(plan['repository']); adopted.next(); self.wait(adopted)
            self.assertTrue(adopted.destination['existing']); self.assertEqual(adopted.key.text(), '')
            self.assertFalse(adopted.saved.isVisible()); self.assertFalse(adopted.schedule.isEnabled())
            adopted.key.setText('SYNTHETIC WIZARD KEY'); adopted.next()
            with patch('vault_data.run') as run:
                adopted.accept(); self.wait(adopted); run.assert_not_called()
            self.assertTrue(adopted.completed); self.assertFalse(adopted.isVisible())
            self.assertEqual(adopted.library.get(adopted.plan_id)['sources'], [])
            schedule.assert_called_once()
