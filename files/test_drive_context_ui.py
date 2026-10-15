import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
from uuid import uuid4

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from app import Window, create_app
import drive_browser as browser


class DriveContextUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or create_app()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.env=patch.dict(os.environ,LUMEN_DATA=self.tmp.name+'/store',LUMEN_TOOLS_DATA=self.tmp.name+'/tools')
        self.env.start();self.addCleanup(self.env.stop)
        self.window=Window(self.tmp.name,QSettings(self.tmp.name+'/settings.ini',QSettings.IniFormat))
        self.addCleanup(self.window.close)
        self.config=dict(server='https://staging.invalid',token='account-a')
        self.user=str(uuid4());self.family=str(uuid4())

    def test_account_switch_during_second_inventory_never_renders_previous_account(self):
        pending=[]
        with patch.object(self.window.drive,'work',side_effect=lambda fn,done,**kw:pending.append((fn,done))), patch.object(browser.lumen_connect,'read_config',return_value=self.config) as config, patch.object(browser.lumen_connect,'request',return_value=dict(id=self.user,can_create=True)), patch.object(browser.sync,'inventory',return_value=dict(folders={},files={self.family:dict(family=self.family,id=str(uuid4()),name='Account A',folder_id=None,trashed=False,size=1,mime='text/plain')})):
            self.window.drive.navigate(browser.ROOT,identity=dict(server=self.config['server'],account=self.user))
            result=pending[0][0](SimpleNamespace(check=lambda:None))
            config.return_value=dict(self.config,token='account-b')
            with self.assertRaises(ValueError):pending[0][1](result)
            self.assertEqual(self.window.drive.model.rowCount(),0)
            self.assertFalse(self.window.drive.cache['files'])

    def test_late_reference_result_does_not_override_newer_navigation(self):
        pending=[]
        ref=dict(app='files',kind='drive_file',id=self.family,title='Original',locator=dict(server=self.config['server'],account=self.user))
        with patch.object(self.window.drive,'work',side_effect=lambda fn,done,**kw:pending.append((fn,done))), patch.object(browser.lumen_connect,'read_config',return_value=self.config):
            self.window.drive.follow_reference(ref)
            self.window.drive.navigate(browser.ROOT)
            self.window.drive.model.appendRow(browser.QStandardItem('New selection'))
            pending[0][1]((self.config,[dict(folder_id=str(uuid4()))]))
            self.assertEqual(self.window.current_location,browser.location())
            self.assertEqual(self.window.drive.model.item(0).text(),'New selection')
            self.assertEqual(len(pending),2)

    def test_newer_link_wins_and_local_navigation_invalidates_pending_link(self):
        ref=dict(app='files',kind='drive_file',id=self.family,title='Original',locator=dict(server=self.config['server'],account=self.user))
        pending=[]
        with patch.object(self.window.drive,'work',side_effect=lambda fn,done,**kw:pending.append((fn,done))), patch.object(browser.lumen_connect,'read_config',return_value=self.config):
            self.window.drive.follow_reference(ref)
            self.window.drive.follow_reference(dict(ref,id=str(uuid4())))
            newer_folder=str(uuid4())
            pending[1][1]((self.config,[dict(folder_id=newer_folder)]))
            pending[0][1]((self.config,[dict(folder_id=str(uuid4()))]))
            self.assertEqual(self.window.current_location,browser.location(newer_folder))
            self.window.drive.follow_reference(ref)
            last=pending[-1]
            self.window.navigate(self.tmp.name)
            last[1]((self.config,[dict(folder_id=str(uuid4()))]))
            self.assertEqual(self.window.current_location,self.tmp.name)
            self.assertIs(self.window.proxy.sourceModel(),self.window.fs)

    def test_discuss_hands_bound_references_to_chat_without_local_uri_paths(self):
        folder=str(uuid4());path=browser.location(folder)
        self.window.drive.config=self.config;self.window.drive.profile=dict(id=self.user)
        self.window.drive.entries[path]=('folder',dict(id=folder,name='Original folder'))
        chat=SimpleNamespace(begin_context=Mock(),backend=SimpleNamespace(execution='local'))
        self.window.lumen_host=SimpleNamespace(chat=chat,show_page=Mock())
        with patch.object(browser.lumen_connect,'read_config',return_value=self.config):
            self.window.ask_lumen('open',[path])
        args,kwargs=chat.begin_context.call_args
        self.assertEqual(args,('open',[]));self.assertTrue(Path(kwargs['directory']).is_dir())
        context=kwargs['drive_context'];self.assertEqual(context['drive_references'][0]['id'],folder)
        self.assertNotIn(self.config['token'],str(context));self.assertTrue(context['objects'][0].startswith('lumen://object/'))

    def test_hidden_drive_preview_resumes_current_selection_on_real_toggle(self):
        from PySide6.QtCore import Qt,QItemSelectionModel,QModelIndex
        from PySide6.QtTest import QTest
        self.window.current_location=browser.ROOT;self.window.show()
        model=self.window.drive.model
        paths=[browser.ROOT+'/file/'+str(uuid4()) for _ in range(2)]
        for name,path in zip(('A.txt','B.txt'),paths):
            item=browser.QStandardItem(name);item.setData(path,Qt.UserRole);model.appendRow(item)
        self.window.proxy.setSourceModel(model);self.window.set_file_root(QModelIndex())
        def select(row):
            index=self.window.proxy.mapFromSource(model.index(row,0))
            self.window.view.selectionModel().select(index,QItemSelectionModel.ClearAndSelect|QItemSelectionModel.Rows)
            QTest.qWait(160)
        with patch.object(self.window.drive,'preview') as preview:
            select(0);preview.assert_called_once_with([paths[0]]);preview.reset_mock()
            QTest.mouseClick(self.window.preview_button,Qt.LeftButton)
            select(1);preview.assert_not_called()
            QTest.mouseClick(self.window.preview_button,Qt.LeftButton);QTest.qWait(160)
            preview.assert_called_once_with([paths[1]]);preview.reset_mock()
            self.window.preview.hide();self.window.reload_settings();QTest.qWait(160)
            preview.assert_called_once_with([paths[1]]);preview.reset_mock()
            self.window.ask_lumen('open',[]);QTest.qWait(160)
            select(0);preview.assert_not_called()
            self.window.assistant_dock.hide();QTest.qWait(160)
            preview.assert_called_once_with([paths[0]])

    def test_chat_submit_and_clear_keep_drive_context_separate_from_paths(self):
        from assistant import ChatPanel
        from lumen_context import ContextTools
        context=dict(drive_references=[dict(title='Selected')],objects=['lumen://object/'+'a'*32],intent='open')
        backend=SimpleNamespace(busy=False,preflight=lambda _:True,execution='local',send=Mock(return_value=False),directory=self.tmp.name)
        panel=SimpleNamespace(backend=backend,paths=[],drive_context=context,drive_context_scope=browser.sync.scope(self.config),error=SimpleNamespace(hide=lambda:None),action='',mode=SimpleNamespace(currentData=lambda:'plan'),context_tools=SimpleNamespace(learn=SimpleNamespace(isChecked=lambda:False)),show_error=Mock(),update_context=Mock())
        with patch.object(browser.lumen_connect,'read_config',return_value=self.config) as config:
            ChatPanel.submit(panel,'Discuss selected originals')
            self.assertEqual(backend.send.call_args.kwargs['context_data'],context)
            self.assertEqual(backend.send.call_args.args[1],[])
            backend.send.reset_mock();config.return_value=dict(self.config,token='new-account')
            ChatPanel.submit(panel,'Must not send old context')
            backend.send.assert_not_called();panel.show_error.assert_called_once()
        ContextTools.clear(SimpleNamespace(panel=panel))
        self.assertEqual(panel.drive_context,{})


if __name__=='__main__':unittest.main()
