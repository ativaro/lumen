"""Native app routes, settings and workflow edits under an isolated profile."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QPushButton
from lumen_apps import AppCenter, catalogue, launch, startup_preference
from work_pages import PlanDialog, StepDialog


class AppCenterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.app = QApplication.instance() or create_app()

    def test_routes_and_failed_launches(self):
        with patch('lumen_apps.QProcess.startDetached', return_value=(True, 42)) as start:
            for key, *_ in catalogue():
                launch(key)
                self.assertNotIn('sh', start.call_args.args[1])
            launch('wissen', area='lumen')
            self.assertEqual(start.call_args.args[1][-3:], ['wissen', '--area', 'lumen'])
            launch('apps'); self.assertEqual(start.call_args.args[1], ['--page', 'apps'])
        with patch('lumen_apps.QProcess.startDetached', return_value=(False, 0)):
            with self.assertRaises(OSError): launch('inbox')
        with self.assertRaises(ValueError): launch('files', area='lumen')
        with self.assertRaises(ValueError): launch('not-an-app')

    def test_companion_keeps_legacy_route_without_redundant_tile(self):
        center = AppCenter(); self.addCleanup(center.close)
        center.search.setText('Companion')
        cards = [card for card, _ in center.cards if not card.isHidden()]
        self.assertEqual(len(cards), 0)
        with patch('lumen_apps.QProcess.startDetached', return_value=(True, 42)) as start:
            launch('companion')
            self.assertTrue(start.call_args.args[0].endswith('/lumen-companion'))
            self.assertEqual(start.call_args.args[1], [])

    def test_catalogue_filter_and_settings_coverage(self):
        from settings_dialog import SettingsDialog
        center = AppCenter(); center.search.setText('Inbox')
        self.assertEqual(sum(not card.isHidden() for card, _ in center.cards), 1)
        center.search.setText('nothing-matches'); self.assertFalse(center.empty.isHidden())
        with tempfile.TemporaryDirectory() as tmp:
            prefs = QSettings(tmp+'/assistant.ini', QSettings.IniFormat)
            files = QSettings(tmp+'/files.ini', QSettings.IniFormat)
            dialog = SettingsDialog(assistant_settings=prefs, files_settings=files, application='inbox', load_system=False)
            self.assertEqual(set(dialog.app_pages), {item[0] for item in catalogue(include_utilities=True)})
            self.assertEqual(dialog.app_pages['search'], dialog.app_pages['lumen'])
            self.assertEqual(dialog.stack.currentIndex(), dialog.app_pages['inbox'])
            self.assertEqual(dialog.nav.currentRow(), 3)
            self.assertTrue(startup_preference('inbox', 'restoreSelection', prefs))
            dialog.save(prefs, {'apps/inbox/restoreSelection': False})
            self.assertFalse(startup_preference('inbox', 'restoreSelection', prefs))
            dialog.close()
        center.close()

    def test_workflow_editor_restores_trigger_and_reorders_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            flow = dict(name='Ordner prüfen', roots=[tmp], steps=[{'action':'open','path':tmp}, {'action':'diagnose'}],
                        trigger='directory', interval=420, watch=tmp, enabled=True, approved=True)
            dialog = PlanDialog(None, flow, workflow=True)
            self.assertEqual(dialog.trigger.currentData(), 'directory')
            self.assertEqual(dialog.interval.value(), 7)
            self.assertEqual(dialog.watch.currentText(), tmp)
            self.assertTrue(dialog.enable.isChecked()); self.assertFalse(dialog.approve.isChecked())
            dialog.save(); self.assertIsNone(dialog.value)
            dialog.steps.setCurrentRow(1); dialog.move_step(-1)
            self.assertEqual(dialog.steps.item(0).data(Qt.UserRole)['action'], 'diagnose')
            self.assertNotIn('"action"', dialog.step_preview.toPlainText())
            dialog.approve.setChecked(True); dialog.save()
            self.assertEqual(dialog.value['steps'][0]['action'], 'diagnose')
            self.assertEqual(dialog.value['watch'], tmp)
            self.assertTrue(dialog.value['enabled'])
            edit = StepDialog(None, flow['steps'][0]); self.assertEqual(edit.step(), flow['steps'][0]); edit.close()
            dialog.close()

    def test_wissen_activation_waits_for_io_or_ai(self):
        from tools_wissen import Wissen
        window = Mock()
        window.area = 'user'; window.area_buttons = {}; window.engine = None; window.dirty = True
        window.job = object(); window.poller = None
        Wissen.switch_area(window, 'lumen')
        self.assertEqual(window.pending_area, 'lumen'); window.save_note.assert_not_called()
        window.job = None; window.engine = Mock(busy=True)
        Wissen.switch_area(window, 'lumen'); self.assertEqual(window.pending_area, 'lumen')
        window.engine = None
        Wissen.switch_area(window, 'lumen'); window.save_note.assert_called_once()
        with self.assertRaises(ValueError): Wissen.switch_area(window, 'invalid')


    def test_edit_workflow_keeps_identity_and_scope(self):
        from types import SimpleNamespace
        from work_pages import WorkPages
        from lumen_store import Store
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/'state')
            key = store.save_workflow('Alt', [{'action':'open','path':tmp}], [tmp], approved=True)
            values = dict(name='Neu', steps=[{'action':'diagnose'}], roots=[tmp], trigger='interval', interval=300, watch='', enabled=True, approved=True)
            window = SimpleNamespace(chat=SimpleNamespace(backend=SimpleNamespace(directory=tmp)))
            pages = SimpleNamespace(window=window, store=store, refresh_flows=Mock())
            dialog = Mock(value=values); dialog.exec.return_value = True
            with patch('work_pages.PlanDialog', return_value=dialog):
                WorkPages.flow_dialog(pages, store.workflows()[0], workflow=key)
            rows = store.workflows(); self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['id'], key); self.assertEqual(rows[0]['interval'], 300)
            self.assertEqual(rows[0]['roots'], [tmp]); self.assertTrue(rows[0]['approved'])


if __name__ == '__main__': unittest.main()
