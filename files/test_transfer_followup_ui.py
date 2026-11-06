import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QProcess, QSettings, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


class FollowupUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = tempfile.TemporaryDirectory()
        root = cls.profile.name
        cls.environment = patch.dict(os.environ, {
            'QT_QPA_PLATFORM': 'offscreen', 'LUMEN_DATA': root + '/state',
            'LUMEN_TOOLS_DATA': root + '/tools', 'LUMEN_LANGUAGE': 'de',
            'XDG_CONFIG_HOME': root + '/config', 'XDG_STATE_HOME': root + '/xdg-state',
            'XDG_CACHE_HOME': root + '/cache', 'XDG_DATA_HOME': root + '/data',
            'DBUS_SESSION_BUS_ADDRESS': 'unix:path=' + root + '/no-host-bus',
        })
        cls.environment.start()
        from app import create_app
        cls.app = QApplication.instance() or create_app('graphite')

    @classmethod
    def tearDownClass(cls):
        cls.environment.stop()
        cls.profile.cleanup()

    def setUp(self):
        from app import Window
        import lumen_transfers as transfers
        from transfer_copy import execute
        self.root = Path(self.profile.name)
        self.source = self.root / ('source-' + self._testMethodName)
        self.source.write_bytes(b'x' * 2 * 1024**2)
        self.target = self.root / ('target-' + self._testMethodName)
        self.target.mkdir()
        self.window = Window(str(self.target), QSettings(str(self.root / 'settings.ini'), QSettings.IniFormat))
        self.window.error = lambda text: self.fail(text)
        self.window.resize(1120, 860)
        self.window.show()
        self.addCleanup(self.window.close)
        self.panel = self.window.transfer_panel
        self.panel.show()
        value = transfers.create(self.panel.store, 'copy', [str(self.source)], str(self.target))
        with self.assertRaises(OSError):
            execute(self.panel.store, value, lambda *_: (_ for _ in ()).throw(OSError('disconnect')))
        transfers.update(self.panel.store, value['id'], status='failed', errors=['disconnect'])
        self.identity = value['id']
        self.panel.show_transfer(self.identity)

    def test_checkbox_snooze_and_disable_are_per_transfer_without_copying(self):
        import lumen_transfers as transfers
        def finish(process, *args):
            QTimer.singleShot(0, lambda: process.finished.emit(0, QProcess.NormalExit))
        self.assertFalse(self.panel.followup.isChecked())
        with patch.object(QProcess, 'start', finish), patch.object(transfers, 'start') as copy:
            QTest.mouseClick(self.panel.followup, Qt.LeftButton)
            QTest.qWait(30)
            self.assertTrue(self.panel.selected()['followup']['enabled'])
            self.assertTrue(self.panel.snooze.isEnabled())
            QTest.mouseClick(self.panel.snooze, Qt.LeftButton)
            self.assertIn('Nächste Prüfung', self.panel.followup_status.text())
            QTest.mouseClick(self.panel.followup, Qt.LeftButton)
            self.assertFalse(self.panel.selected()['followup']['enabled'])
            copy.assert_not_called()
        self.assertFalse((self.target / self.source.name).exists())

    def test_timer_failure_is_visible_and_does_not_arm_followup(self):
        errors = []
        self.window.error = errors.append
        def finish(process, *args):
            QTimer.singleShot(0, lambda: process.finished.emit(1, QProcess.NormalExit))
        with patch.object(QProcess, 'start', finish):
            QTest.mouseClick(self.panel.followup, Qt.LeftButton)
            QTest.qWait(30)
        self.assertFalse(self.panel.selected().get('followup', {}).get('enabled', False))
        self.assertTrue(errors)

    def test_activation_selects_existing_ticket_without_restart_or_transfer(self):
        from app import activate_files
        import lumen_transfers as transfers
        self.panel.hide()
        with patch.object(transfers, 'start') as copy, patch.object(self.window, 'new_tab') as tab:
            activate_files(self.window, {'transfer': self.identity})
            self.assertEqual(self.panel.selected()['id'], self.identity)
            self.assertTrue(self.panel.isVisible())
            copy.assert_not_called()
            tab.assert_not_called()
        with self.assertRaises(ValueError):
            activate_files(self.window, {'transfer': '../not-a-ticket'})
        with self.assertRaises(ValueError):
            self.panel.show_transfer('f' * 32)

    def test_deeplink_older_than_two_hundred_tickets_stays_selected(self):
        import lumen_transfers as transfers
        for _ in range(205):
            value = transfers.create(self.panel.store, 'copy', [str(self.source)], str(self.target))
            transfers.update(self.panel.store, value['id'], status='completed')
        self.panel.show_transfer(self.identity)
        self.assertEqual(self.panel.selected()['id'], self.identity)
        self.assertEqual(self.panel.list.topLevelItemCount(), 200)
        self.panel.refresh()
        self.assertEqual(self.panel.selected()['id'], self.identity)

    def test_transfer_cli_rejects_other_activation_modes_before_starting(self):
        from app import main
        for extra in (['/tmp'], ['--settings'], ['--select'], ['--ref', 'not-a-reference']):
            with self.assertRaises(SystemExit) as result:
                main(['--transfer', self.identity, *extra])
            self.assertEqual(result.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
