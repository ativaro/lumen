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

    def test_projects_retain_room_sources_pins_and_manual_flow_trigger(self):
        import os
        from tools_workbench import Workbench
        from lumen_projects import save_project, projects
        from file_spaces import Catalog
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, LUMEN_DATA=tmp+'/state', LUMEN_TOOLS_DATA=tmp+'/tools'):
            store = Store(); room = save_project(store, None, 'Existing room', [dict(label='Local', location=tmp)], [], ['https://example.org'], 'Continue here')
            saved = dict(room, pins=[dict(kind='chat', title='Pinned chat', chat=dict(directory=tmp, session='session-one'))])
            Catalog(store).put('room', saved, room)
            before = projects(store)
            flow = store.save_workflow('Keep schedule', [{'action':'open','path':tmp}], [tmp], trigger='directory',watch=tmp,interval=420,enabled=False,approved=True)
            with patch('projects_sync_ui.install'), patch('projects_runner.recover'):
                window = Workbench(tmp+'/tools')
            try:
                self.assertEqual([window.areas.tabText(i) for i in range(3)], ['Archiv und Serverabgleich','Projekte','Automationen'])
                window.open_section('rooms'); window.workplace.rooms.open(room['id'])
                self.assertEqual(window.workplace.project['pins'], saved['pins'])
                window.workplace.rooms.prompt.setText('Question remains a draft')
                with patch('lumen_detail_routes.room_action', return_value={'status':'Draft opened'}) as action:
                    window.workplace.rooms.discuss()
                    action.assert_called_once_with(room['id'], 'discuss', 'Question remains a draft')
                window.open_section('automations')
                self.assertEqual(window.automations.flows.item(0).data(256)['id'], flow)
                self.assertEqual(projects(store), before)
                self.assertEqual(store.tasks(), [])
                self.assertEqual(window.library.all(), [])
                with patch('lumen_detail_routes.room_action', side_effect=ValueError('Keep current draft')):
                    window.workplace.rooms.prompt.setText('Do not lose this question')
                    with self.assertRaises(ValueError): window.workplace.rooms.discuss()
                    self.assertEqual(window.workplace.rooms.prompt.text(), 'Do not lose this question')
            finally: window.close(); window.deleteLater()

    def test_room_bridge_pins_and_restores_the_same_conversation_without_losing_drafts(self):
        import importlib.util, json, os
        from lumen_projects import save_project, projects
        path = Path(__file__).resolve().parents[1]/'agent-app/main.py'
        spec = importlib.util.spec_from_file_location('detail_bridge_test',path)
        desktop = importlib.util.module_from_spec(spec); spec.loader.exec_module(desktop)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LUMEN_DATA=tmp+'/state',LUMEN_TOOLS_DATA=tmp+'/tools'), patch('desktop_backend.DesktopBackend.refresh_sessions'):
            window = desktop.LumenWindow(tmp); endpoint = desktop.DesktopActivation(); endpoint.window = window
            room = save_project(window.workspace.store,None,'Preserved room',[dict(label='Folder',location=tmp)],[],[],'Next step')
            def call(action,value=''):
                return json.loads(endpoint.RoomAction(json.dumps(dict(room=room['id'],action=action,value=value))))
            try:
                window.chat.backend.session = 'session-one'; window.chat.composer.setPlainText('Existing draft')
                self.assertNotIn('error',call('pin'))
                pin = projects(window.workspace.store)[0]['pins'][0]
                self.assertEqual(pin['chat'],dict(directory=tmp,session='session-one'))
                self.assertNotIn('error',call('capture'))
                captured = projects(window.workspace.store)[0]['state']['chat']
                self.assertEqual(captured['draft'],'Existing draft'); self.assertEqual(captured['session'],'session-one')
                self.assertIn('error',call('discuss','New question'))
                self.assertEqual(window.chat.composer.toPlainText(),'Existing draft')
                window.chat.composer.clear()
                with patch.object(window.chat.backend,'send') as send:
                    self.assertNotIn('error',call('discuss','Explain the sources'))
                    self.assertIn('Explain the sources',window.chat.composer.toPlainText())
                    self.assertIn(tmp,window.chat.paths); send.assert_not_called()
                self.assertIn('error',call('delete'))
                self.assertIn('error',json.loads(endpoint.RoomAction('[]')))
            finally:
                window.chat.composer.clear(); window.chat.paths=[]; window.close(); window.deleteLater()

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

    def test_files_activity_keeps_transfer_and_undo_views_without_room_duplication(self):
        import os
        from PySide6.QtCore import QSettings
        from app import Window
        from file_spaces import Catalog
        from lumen_projects import save_project, projects
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LUMEN_DATA=tmp+'/state',LUMEN_TOOLS_DATA=tmp+'/tools'):
            store=Store();room=save_project(store,None,'Keep room',[dict(label='Home',location=tmp)],[],[],'Keep')
            window=Window(tmp,QSettings(tmp+'/prefs.ini',QSettings.IniFormat),Catalog(store))
            try:
                window.show_workplace(1);page=window.workplace_dialog.page
                self.assertEqual(page.tabs.count(),2);self.assertFalse(hasattr(page,'rooms'))
                self.assertEqual(page.tabs.currentIndex(),0)
                window.show_workplace(2);self.assertEqual(page.tabs.currentIndex(),1)
                with patch('lumen_detail_routes.launch') as launch:
                    window.show_workplace();launch.assert_called_once_with('lumen-workbench',['--section','rooms'])
                self.assertEqual(projects(store),[room])
            finally:window.close();window.deleteLater()
