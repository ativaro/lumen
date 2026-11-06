"""Moved native pages keep their existing store and avoid a duplicate chat."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QWidget
from lumen_store import Store


class DetailToolsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()

    def test_independent_pages_share_existing_records(self):
        from lumen_workspace import Workspace
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/'state')
            flow = store.save_workflow('Keep trigger', [{'action':'open','path':tmp}], [tmp],
                                      trigger='directory', watch=tmp, interval=300, enabled=False, approved=True)
            host = QWidget()
            pages = [Workspace(host, store, [section]) for section in ('flows', 'knowledge', 'models', 'tasks')]
            self.assertFalse(hasattr(host, 'chat'))
            self.assertEqual(pages[0].flows.item(0).data(256)['id'], flow)
            self.assertFalse(hasattr(pages[0], 'tasks_page'))
            with patch('lumen_detail_routes.launch') as launch:
                pages[1].to_chat('Selected source', [tmp+'/source.txt'])
                self.assertEqual(launch.call_args.args[1], ['--prompt','Selected source','--file',tmp+'/source.txt'])
            for page in pages:
                self.assertTrue(page.can_close()); page.shutdown()
            host.close()



    def test_populated_task_page_routes_ai_controls_and_keeps_native_controls(self):
        from lumen_workspace import Workspace
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/'state'); host = QWidget()
            task = store.create_task('Resume existing task', directory=tmp, status='paused')
            store.update_task(task, result='Existing answer', session='same-session')
            workspace = Workspace(host, store, ('tasks',))
            workspace.select_task(task)
            self.assertEqual(workspace.task_title.text(), 'Resume existing task')
            with patch('lumen_detail_routes.task_action') as action:
                workspace.run_task(task); action.assert_called_with(task,'run')
                workspace.open_task_conversation(task); action.assert_called_with(task,'conversation')
            workspace.stop_task('cancelled')
            self.assertEqual(store.task(task)['status'], 'cancelled')
            workspace.shutdown(); host.close()

    def test_models_share_settings_and_do_not_launch_a_backend_on_open(self):
        import os
        from PySide6.QtCore import QSettings
        from settings_dialog import SettingsDialog
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LUMEN_DATA=tmp+'/state'):
            prefs=QSettings(tmp+'/prefs.ini',QSettings.IniFormat)
            dialog=SettingsDialog(assistant_settings=prefs,files_settings=QSettings(tmp+'/files.ini',QSettings.IniFormat),load_system=False)
            try:
                page=dialog.resource_workspace
                self.assertIsNone(page.model_backend)
                page.model_controls['model'].setCurrentText('provider/selected')
                page.save_models()
                self.assertEqual(prefs.value('model'), 'provider/selected')
                self.assertEqual(dialog.model.currentData(), 'provider/selected')
                dialog.save(prefs, {'model':'provider/other'})
                self.assertEqual(page.model_controls['model'].currentText(), 'provider/other')
                self.assertEqual(page.store.setting('modelPolicy')['model'], 'provider/other')
            finally: dialog.close(); dialog.deleteLater()

    def test_legacy_page_targets_and_compact_app_expansion(self):
        from lumen_detail_routes import open_page
        from search_home import SearchHome
        from lumen_apps import catalogue
        with patch('lumen_detail_routes.launch') as launch:
            for page, executable in [(1,'lumen-system'),(3,'lumen-files'),(4,'lumen-system'),(5,'lumen-wissen'),(6,'lumen-workbench'),(7,'lumen-settings'),(8,'lumen-workbench'),(10,'lumen-wissen'),(11,'lumen-companion'),(12,'lumen-workbench')]:
                self.assertTrue(open_page(page)); self.assertEqual(launch.call_args.args[0],executable)
            self.assertFalse(open_page(0))
        home=SearchHome(); home.launch_app('apps')
        self.assertEqual({row['id'] for row in home.apps}, {row[0] for row in catalogue()}-{'lumen'}|{'apps'})
        home.launch_app('apps'); self.assertEqual(len(home.apps),6); home.shutdown()
