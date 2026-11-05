import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import desktop_settings as desktop


class DesktopSettingsTest(unittest.TestCase):
    def launch_accelerator(self):
        from PySide6.QtGui import QKeySequence
        meta, alt, other = [QKeySequence(k)[0].toCombined() for k in ('Meta', 'Alt+Space', 'Meta+Shift+O')]
        class Accel:
            def __init__(self):
                self.keys = {('lumen-toggle.desktop', '_launch'): [meta],
                             ('org.kde.krunner.desktop', '_launch'): [alt],
                             ('lumen-ask.desktop', '_launch'): [other]}
                self.fail_once = False
            def shortcut(self, action): return self.keys.get(tuple(action[:2]), [])
            def getGlobalShortcutsByKey(self, key):
                return [[name, name, component, component, 'default', 'Default'] for (component, name), keys in self.keys.items() if key in keys]
            def doRegister(self, action): self.keys.setdefault(tuple(action[:2]), [])
            def setShortcut(self, action, keys, flags):
                assert int(flags) == 6
                if self.fail_once and list(keys) == [meta]: self.fail_once = False; return []
                self.keys[tuple(action[:2])] = list(map(int, keys)); return keys
        return Accel(), meta, alt, other

    def test_launch_keys_move_to_start_and_lumen_and_restore(self):
        entry = Path(__file__).resolve().parents[1] / 'data/applications/lumen-ask.desktop'
        self.assertIn('X-KDE-Shortcuts=Alt+Space,Meta+Shift+O', entry.read_text())
        accel, meta, alt, other = self.launch_accelerator()
        saved = {}
        def capture(name, value): saved.update(value); return Path('/backup.json')
        with patch.object(desktop, 'accelerator', return_value=accel), patch.object(desktop, 'backup', side_effect=capture), patch.object(desktop, 'run', return_value=''):
            desktop.configure_launch_shortcuts()
            self.assertEqual(accel.keys[('lumen-apps.desktop', '_launch')], [meta])
            self.assertEqual(accel.keys[('lumen-toggle.desktop', '_launch')], [])
            self.assertEqual(accel.keys[('org.kde.krunner.desktop', '_launch')], [])
            self.assertEqual(accel.keys[('lumen-ask.desktop', '_launch')], [other, alt])
            desktop.restore_launch_shortcuts(saved)
            self.assertEqual(accel.keys[('lumen-toggle.desktop', '_launch')], [meta])
            self.assertEqual(accel.keys[('org.kde.krunner.desktop', '_launch')], [alt])
            self.assertEqual(accel.keys[('lumen-ask.desktop', '_launch')], [other])

    def test_launch_keys_preserve_foreign_bindings_and_recover_failures(self):
        accel, meta, alt, other = self.launch_accelerator()
        accel.keys[('foreign.desktop', '_launch')] = [meta]
        with patch.object(desktop, 'accelerator', return_value=accel), patch.object(desktop, 'backup') as backup, patch.object(desktop, 'run') as run:
            with self.assertRaises(ValueError): desktop.configure_launch_shortcuts()
            backup.assert_not_called(); run.assert_not_called()
        del accel.keys[('foreign.desktop', '_launch')]; before = dict(accel.keys); accel.fail_once = True
        with patch.object(desktop, 'accelerator', return_value=accel), patch.object(desktop, 'backup', return_value=Path('/backup.json')), patch.object(desktop, 'run', return_value=''):
            with self.assertRaises(RuntimeError): desktop.configure_launch_shortcuts()
        self.assertEqual({k: accel.keys[k] for k in before}, before)

    def test_refresh_never_deletes_live_shortcut_components(self):
        from unittest.mock import Mock
        bus = Mock()
        bus.name_has_owner.return_value = True
        with patch.object(desktop, 'run') as run, \
                patch.object(desktop, 'accelerator', side_effect=AssertionError('Do not mutate live shortcuts')), \
                patch('dbus.SessionBus', return_value=bus):
            desktop.refresh_shortcuts({})
        run.assert_called_once_with(['kbuildsycoca6', '--noincremental'])

    def test_panel_changes_are_scoped_and_validate_before_execution(self):
        panel = dict(id=98, screen=0, location='top', height=36, floating=True,
                     hiding='none', widgets=[])
        with tempfile.TemporaryDirectory() as tmp, patch.object(desktop, 'panels', side_effect=lambda: [dict(panel)]), \
                patch.object(desktop, 'run') as run, patch.object(desktop, 'backup', return_value=Path(tmp) / 'backup.json'):
            def apply(argv):
                if 'p.height = 40' in argv[-1]: panel['height'] = 40
            run.side_effect = apply
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
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()

    def tearDown(self):
        from lumen_qt import is_deleted
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtTest import QTest
        # Dispose Qt objects while the interpreter and GUI event loop still exist.
        for widget in self.app.topLevelWidgets():
            if not is_deleted(widget):
                widget.close()
                widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QTest.qWait(20)

    def test_four_themes_persist_and_restyle_open_native_surfaces(self):
        from app import Window
        from appearance import DEFAULT_DESIGN, DESIGNS, apply_design, normalize_design
        from settings_dialog import SettingsDialog
        from PySide6.QtCore import QSettings, Qt
        from PySide6.QtGui import QPalette
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QDialog, QPushButton, QVBoxLayout
        self.assertEqual(DEFAULT_DESIGN, 'glass')
        self.assertEqual(normalize_design('studio'), 'atelier')
        self.assertEqual(normalize_design('lumen'), 'graphite')
        self.assertEqual(normalize_design('unknown'), 'glass')
        def luminance(color):
            channels = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
                        for v in (color.redF(), color.greenF(), color.blueF())]
            return sum(a * b for a, b in zip(channels, (.2126, .7152, .0722)))
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'LUMEN_DATA': tmp + '/state'}):
            settings = QSettings(tmp + '/assistant.ini', QSettings.IniFormat)
            files = QSettings(tmp + '/files.ini', QSettings.IniFormat)
            dialog = SettingsDialog(files_settings=files, assistant_settings=settings, page=3, load_system=False)
            dialog.perform = lambda action, data, callback: callback({'desktop': True})
            self.assertEqual(dialog.appearance.checkedButton().property('design'), 'glass')
            gallery = QDialog(); gallery.setObjectName('gallery')
            layout = QVBoxLayout(gallery); action = QPushButton('Speichern'); action.setObjectName('primary'); layout.addWidget(action)
            gallery.show(); dialog.show()
            try:
                for _, name in DESIGNS:
                    choice = dialog.theme_buttons[name]; choice.setFocus(); QTest.keyClick(choice, Qt.Key_Space)
                    QTest.mouseClick(dialog.apply_appearance, Qt.LeftButton); QTest.qWait(30)
                    self.assertEqual(settings.value('appearance', DEFAULT_DESIGN), name)
                    self.assertEqual(self.app.property('lumenDesign'), name)
                    self.assertEqual(gallery.palette().color(QPalette.Window), self.app.palette().color(QPalette.Window))
                    palette = self.app.palette()
                    for foreground, background in [(QPalette.Text, QPalette.Base), (QPalette.ButtonText, QPalette.Button),
                            (QPalette.Dark, QPalette.Window), (QPalette.Dark, QPalette.AlternateBase),
                            (QPalette.HighlightedText, QPalette.Highlight)]:
                        light, dark = sorted((luminance(palette.color(foreground)), luminance(palette.color(background))))
                        self.assertGreaterEqual((dark + .05) / (light + .05), 4.5, (name, foreground, background))
                dialog.done(0)
                reopened = SettingsDialog(files_settings=files, assistant_settings=settings, page=3, load_system=False)
                self.assertEqual(reopened.appearance.checkedButton().property('design'), 'midnight')
                reopened.close()
                window = Window(tmp, files)
                self.assertEqual(window.palette().color(QPalette.Highlight), self.app.palette().color(QPalette.Highlight))
                window.close()
            finally:
                gallery.close(); dialog.close()
                apply_design(self.app, DEFAULT_DESIGN)

    def test_topbar_layout_applies_immediately_and_preserves_theme(self):
        from settings_dialog import SettingsDialog
        from PySide6.QtCore import QSettings
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'LUMEN_DATA':tmp+'/state'}):
            settings=QSettings(tmp+'/assistant.ini',QSettings.IniFormat)
            settings.setValue('appearance','atelier')
            files=QSettings(tmp+'/files.ini',QSettings.IniFormat)
            dialog=SettingsDialog(files_settings=files,assistant_settings=settings,page=3,load_system=False)
            try:
                self.assertEqual(dialog.topbar_layout.currentData(),'classic')
                for layout in ('band','deck','context','classic'):
                    dialog.topbar_layout.setCurrentIndex(dialog.topbar_layout.findData(layout))
                    self.assertEqual(settings.value('topbar/layout'),layout)
                    self.assertEqual(settings.value('appearance'),'atelier')
                reopened=SettingsDialog(files_settings=files,assistant_settings=settings,page=3,load_system=False)
                self.assertEqual(reopened.topbar_layout.currentData(),'classic')
                reopened.close()
            finally:dialog.close()

    def test_preferences_apply_to_files_and_new_windows_without_system_writes(self):
        from app import Window
        from settings_dialog import SettingsDialog
        from PySide6.QtCore import QSettings
        from PySide6.QtTest import QTest
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

    def test_server_inbox_uses_device_permissions_instead_of_the_retired_cache_toggle(self):
        from settings_dialog import SettingsDialog
        from PySide6.QtCore import QSettings
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'LUMEN_DATA': tmp+'/state'}):
            assistant = QSettings(tmp+'/assistant.ini', QSettings.IniFormat)
            assistant.setValue('mcpInboxRead',True)
            files = QSettings(tmp+'/files.ini', QSettings.IniFormat)
            dialog = SettingsDialog(files_settings=files, assistant_settings=assistant, load_system=False)
            from PySide6.QtWidgets import QPushButton,QCheckBox
            from lumen_i18n import tr
            page=dialog.stack.widget(9)
            self.assertFalse(page.findChildren(QCheckBox))
            button = next(b for b in page.findChildren(QPushButton) if b.text()==tr('Gerätefreigaben auf dem Server öffnen'))
            with patch('server_notes_app.open_device_permissions',return_value=True) as opened:button.click()
            opened.assert_called_once_with()
            self.assertTrue(assistant.value('mcpInboxRead',False,type=bool))
            dialog.close()

    def test_document_workshop_is_opt_in_and_stale_actions_cannot_open_it(self):
        from app import Window
        from settings_dialog import SettingsDialog
        from document_workshop_ui import open_workshop
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QMenu
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'LUMEN_DATA': tmp+'/state'}):
            files = QSettings(tmp+'/files.ini', QSettings.IniFormat)
            assistant = QSettings(tmp+'/assistant.ini', QSettings.IniFormat)
            window = Window(tmp, files)
            dialog = SettingsDialog(window, files, assistant, load_system=False)
            self.assertFalse(dialog.document_workshop.isChecked())
            self.assertFalse(files.contains('documentWorkshopEnabled'))
            menu = QMenu(window); window.add_workshop_action(menu)
            self.assertFalse(menu.actions())
            with patch('document_workshop_ui.DocumentWorkshop') as workshop, patch('lumen_setup.executable') as executable:
                open_workshop(window)
                workshop.assert_not_called(); executable.assert_not_called()
                dialog.document_workshop.setChecked(True); dialog.save_files()
                paths = [tmp+'/document.pdf']
                window.add_workshop_action(menu, paths); self.assertEqual(len(menu.actions()),1)
                executable.return_value = True
                menu.actions()[0].trigger(); workshop.assert_called_once_with(paths,window)
                workshop.reset_mock(); executable.reset_mock()
                reopened = SettingsDialog(window, QSettings(files.fileName(),QSettings.IniFormat), assistant, load_system=False)
                self.assertTrue(reopened.document_workshop.isChecked())
                reopened.document_workshop.setChecked(False); reopened.save_files()
                menu.actions()[0].trigger(); workshop.assert_not_called(); executable.assert_not_called()
                fresh = QMenu(window); window.add_workshop_action(fresh)
                self.assertFalse(fresh.actions())
                reopened.reject()
            dialog.reject(); window.close()

    def test_lumen_preferences_preserve_explicit_read_and_fix_actions(self):
        from assistant import ChatPanel
        from settings_dialog import SettingsDialog
        from PySide6.QtCore import QSettings
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
        from PySide6.QtCore import QSettings
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
        from PySide6.QtCore import QSettings
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
        from PySide6.QtCore import QSettings
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
