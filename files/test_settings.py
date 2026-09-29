import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import desktop_settings as desktop


class DesktopSettingsTest(unittest.TestCase):
    def test_panel_changes_are_scoped_and_validate_before_execution(self):
        panel = dict(id=98, screen=0, location='top', height=36, floating=True,
                     hiding='none', widgets=[])
        with tempfile.TemporaryDirectory() as tmp, patch.object(desktop, 'panels', return_value=[panel]), \
                patch.object(desktop, 'run') as run, patch.object(desktop, 'backup', return_value=Path(tmp) / 'backup.json'):
            desktop.change_panel({'id': 98, 'before': panel, 'changes': {'height': 40}})
            script = run.call_args.args[0][-1]
            self.assertIn('p.height = 40', script)
            self.assertNotIn('p.location =', script)
            self.assertNotIn('p.floating =', script)
            run.reset_mock()
            for changes in ({'height': -1}, {'height': True}, {'location': 'top;bad()'}, {'id': 121}):
                with self.assertRaises(ValueError):
                    desktop.change_panel({'id': 98, 'before': panel, 'changes': changes})
            with self.assertRaises(ValueError):
                desktop.change_panel({'id': 999, 'before': panel, 'changes': {'height': 40}})
            with self.assertRaises(ValueError):
                desktop.change_panel({'id': 98, 'before': {**panel, 'height': 50}, 'changes': {'height': 40}})
            run.assert_not_called()

    def test_service_scope_and_timer_failure_restores_file(self):
        with patch.object(desktop, 'run') as run:
            for scope, unit in [('user', 'sshd.service'), ('system', 'lumen-nightly.timer')]:
                with self.assertRaises(ValueError):
                    desktop.set_service({'scope': scope, 'unit': unit, 'enabled': False})
            run.assert_not_called()
            desktop.set_service({'scope': 'user', 'unit': 'lumen-digest.timer', 'enabled': False})
            self.assertEqual(run.call_args.args[0], ['systemctl', '--user', 'disable', '--now', 'lumen-digest.timer'])
        with tempfile.TemporaryDirectory() as tmp, patch.object(desktop, 'CONFIG', Path(tmp)), \
                patch.object(desktop, 'unit_state', return_value={'ActiveState': 'inactive'}), \
                patch.object(desktop, 'run', side_effect=RuntimeError('reload failed')):
            path = Path(tmp) / 'systemd/user/lumen-digest.timer.d/lumen-settings.conf'
            path.parent.mkdir(parents=True)
            path.write_text('original')
            with self.assertRaises(RuntimeError):
                desktop.set_schedule({'unit': 'lumen-digest.timer', 'time': '08:30'})
            self.assertEqual(path.read_text(), 'original')
            with self.assertRaises(ValueError):
                desktop.set_schedule({'unit': 'lumen-digest.timer', 'time': '08:00\nExecStart=evil'})

    def test_shortcut_refuses_conflicts_and_stale_settings(self):
        class Accel:
            def allMainComponents(self):
                return [['lumen-ask.desktop']]
            def allActionsForComponent(self, _):
                return [['lumen-ask.desktop', '_launch', 'Lumen', 'Lumen']]
            def shortcut(self, _):
                return [123]
            def isGlobalShortcutAvailable(self, *_):
                return False
            def setShortcut(self, *_):
                raise AssertionError('must not overwrite a conflict')
        with patch.object(desktop, 'accelerator', return_value=Accel()):
            with self.assertRaisesRegex(ValueError, 'belegt'):
                desktop.set_shortcut({'component': 'lumen-ask.desktop', 'before': [123], 'key': 456})
            with self.assertRaisesRegex(ValueError, 'geändert'):
                desktop.set_shortcut({'component': 'lumen-ask.desktop', 'before': [122], 'key': 456})


class NativeSettingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()

    def tearDown(self):
        from PyQt5 import sip
        from PyQt5.QtCore import QCoreApplication, QEvent
        from PyQt5.QtTest import QTest
        # Dispose Qt objects while the interpreter and GUI event loop still exist.
        for widget in self.app.topLevelWidgets():
            if not sip.isdeleted(widget):
                widget.close()
                widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QTest.qWait(20)

    def test_preferences_apply_to_files_and_new_windows_without_system_writes(self):
        from app import Window
        from settings_dialog import SettingsDialog
        from PyQt5.QtCore import QSettings
        from PyQt5.QtTest import QTest
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'start'
            folder.mkdir()
            files = QSettings(str(Path(tmp) / 'files.ini'), QSettings.IniFormat)
            assistant = QSettings(str(Path(tmp) / 'assistant.ini'), QSettings.IniFormat)
            files.setValue('favorites', [str(folder)])
            files.sync()
            before = Path(files.fileName()).read_bytes()
            window = Window(tmp, files)
            window.show()
            dialog = SettingsDialog(window, files, assistant, load_system=False)
            self.assertEqual(Path(files.fileName()).read_bytes(), before)
            self.assertEqual(assistant.allKeys(), [])
            dialog.preferencesChanged.connect(window.reload_settings)
            dialog.resume.setChecked(False)
            dialog.startdir.setText(str(folder))
            dialog.hidden.setChecked(True)
            dialog.preview.setChecked(False)
            dialog.limit.setValue(100)
            dialog.delay.setValue(450)
            dialog.save_files()
            QTest.qWait(50)
            self.assertTrue(window.hidden)
            self.assertTrue(window.preview.isHidden())
            self.assertEqual(window.debounce.interval(), 450)
            self.assertEqual(window.current_path, tmp)
            dialog.reject()
            window.close()
            other = Window(settings=files)
            self.assertEqual(other.current_path, str(folder))
            self.assertEqual(files.value('favorites', [], type=list), [str(folder)])
            other.close()

    def test_lumen_preferences_preserve_explicit_read_and_fix_actions(self):
        from assistant import ChatPanel
        from settings_dialog import SettingsDialog
        from PyQt5.QtCore import QSettings
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(str(Path(tmp) / 'assistant.ini'), QSettings.IniFormat)
            files = QSettings(str(Path(tmp) / 'files.ini'), QSettings.IniFormat)
            chat = ChatPanel(tmp, settings=settings)
            chat.backend.refresh_sessions = lambda: None
            chat.submit = lambda *_: None
            dialog = SettingsDialog(files_settings=files, assistant_settings=settings, load_system=False)
            dialog.preferencesChanged.connect(chat.reload_settings)
            dialog.workdir.setText(tmp)
            dialog.mode.setCurrentIndex(1)
            dialog.auto.setChecked(True)
            dialog.language.setText('Englisch')
            dialog.save_lumen()
            self.assertTrue(chat.dont_ask.isChecked())
            chat.new_conversation()
            self.assertEqual(chat.mode.currentData(), 'plan')
            chat.begin_context('fix')
            self.assertEqual(chat.mode.currentData(), 'build')
            chat.begin_context('explain')
            self.assertEqual(chat.mode.currentData(), 'plan')
            dialog.reject()
            chat.backend.shutdown()
            chat.close()

    def test_files_save_never_enables_auto_approval_in_an_existing_chat(self):
        from assistant import ChatPanel
        from settings_dialog import SettingsDialog
        from PyQt5.QtCore import QSettings
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(str(Path(tmp) / 'assistant.ini'), QSettings.IniFormat)
            files = QSettings(str(Path(tmp) / 'files.ini'), QSettings.IniFormat)
            chat = ChatPanel(tmp, settings=settings)
            settings.setValue('autoApproveTools', True)  # Another window changed its own choice.
            dialog = SettingsDialog(files_settings=files, assistant_settings=settings, load_system=False)
            dialog.preferencesChanged.connect(chat.reload_settings)
            dialog.delay.setValue(600)
            with patch.object(chat.backend, 'set_auto_approve') as approve:
                dialog.save_files()
                self.assertFalse(chat.dont_ask.isChecked())
                approve.assert_not_called()
            dialog.reject()
            chat.backend.shutdown()
            chat.close()

    def test_model_preference_reaches_proposal_without_unlocking_tools(self):
        from assistant_backend import OpenCodeBackend
        from PyQt5.QtCore import QSettings
        with tempfile.TemporaryDirectory() as tmp:
            backend = OpenCodeBackend(tmp, server_url='http://127.0.0.1:9')
            backend.settings = QSettings(str(Path(tmp) / 'assistant.ini'), QSettings.IniFormat)
            backend.settings.setValue('model', 'provider/model/version')
            requests = []
            def request(method, path, body=None, callback=None, **_):
                requests.append((method, path, body))
                if path == '/session':
                    callback({'id': 'ses_test'})
            backend.request = request
            backend.send('Suggest', proposal=True)
            body = next(body for _, path, body in requests if path.endswith('/prompt_async'))
            self.assertEqual(body['model'], {'providerID': 'provider', 'modelID': 'model/version'})
            self.assertEqual(body['tools'], {'*': False})
            backend.shutdown()

    def test_search_limit_applies_to_worker(self):
        from core import SearchWorker
        with tempfile.TemporaryDirectory() as tmp:
            for number in range(105):
                (Path(tmp) / f'entry{number}').touch()
            results, summaries = [], []
            worker = SearchWorker(tmp, 'entry', False, limit=100)
            worker.batch.connect(results.extend)
            worker.summary.connect(lambda count, limited, elapsed: summaries.append((count, limited)))
            worker.run()
            self.assertEqual(len(results), 100)
            self.assertEqual(summaries, [(100, True)])

    def test_settings_conflict_keeps_places_added_by_another_window(self):
        from settings_dialog import SettingsDialog
        from PyQt5.QtCore import QSettings
        with tempfile.TemporaryDirectory() as tmp:
            files = QSettings(str(Path(tmp) / 'files.ini'), QSettings.IniFormat)
            assistant = QSettings(str(Path(tmp) / 'assistant.ini'), QSettings.IniFormat)
            files.setValue('favorites', ['/old', '/keep'])
            dialog = SettingsDialog(files_settings=files, assistant_settings=assistant, load_system=False)
            files.setValue('favorites', ['/old', '/keep', '/new'])
            dialog.places.takeItem(0)
            dialog.hidden.setChecked(True)
            dialog.save_files()
            self.assertEqual(files.value('favorites'), ['/old', '/keep', '/new'])
            self.assertFalse(files.value('hidden', False, type=bool))
            self.assertIn('anderen Fenster', dialog.status.text())
            dialog.reject()


if __name__ == '__main__':
    unittest.main()
