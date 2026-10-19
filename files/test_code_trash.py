"""Recoverable removal through the real collection controls; no user data."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from code_library import Collection
from code_library_window import CollectionWindow
from lumen_store import Store


class TrashTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.app=QApplication.instance() or create_app()

    def window(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        window=CollectionWindow(Store(temporary.name));self.addCleanup(window.close)
        window.resize(960,800);window.show();window.activateWindow();QTest.qWait(20)
        return window

    def select(self,window,identity):
        for i in range(window.entries.topLevelItemCount()):
            row=window.entries.topLevelItem(i)
            if row.data(0,Qt.UserRole)==identity:
                window.entries.setCurrentItem(row);return row
        self.fail('Entry missing: '+identity)

    def test_clicked_selection_trashes_and_restores_all_kinds_preserving_files(self):
        from code_blocks import node,encode
        w=self.window();folder=w.store.directory/'original';folder.mkdir();source=folder/'source.txt';source.write_text('Keep original')
        values=[('app',{'html':'<p>Keep app</p>'}),('tool',{'prompt':'Keep prompt'}),('code',{'directory':str(folder),'draft_prompt':'Keep draft','session_id':'kept-session'}),('automation',{'flow':encode({'version':2,'nodes':[node('manual'),node('approval')]})}),('automation',{'editor':'routine','flow':encode({'version':3,'nodes':[node('manual',json.dumps({'kind':'text','text':'Keep source'})),node('approval')]})})]
        for index,(kind,value) in enumerate(values):
            with self.subTest(kind=kind,value=value):
                entry=w.collection.create(kind,'Keep '+str(index),value=value,project_id='kept-project');w.refresh();self.select(w,entry['id'])
                self.assertTrue(w.trash_selection.isVisible());self.assertEqual(w.trash_selection.text(),'In den Papierkorb')
                def confirm():
                    dialog=QApplication.activeModalWidget()
                    self.assertEqual(dialog.textFormat(),Qt.PlainText);self.assertIn(entry['title'],dialog.text())
                    self.assertEqual(dialog.button(QMessageBox.Yes).text(),'In den Papierkorb');self.assertEqual(dialog.button(QMessageBox.No).text(),'Abbrechen');self.assertEqual(dialog.defaultButton(),dialog.button(QMessageBox.No))
                    dialog.button(QMessageBox.Yes).click()
                QTimer.singleShot(10,confirm)
                QTest.mouseClick(w.trash_selection,Qt.LeftButton)
                self.assertTrue(w.collection.get(entry['id'])['archived']);self.assertFalse(any(w.entries.topLevelItem(i).data(0,Qt.UserRole)==entry['id'] for i in range(w.entries.topLevelItemCount())))
                w.categories.setCurrentRow(w.category_keys.index('archive'));self.select(w,entry['id']);self.assertEqual(w.trash_selection.text(),'Wiederherstellen')
                QTest.mouseClick(w.trash_selection,Qt.LeftButton)
                restored=w.collection.get(entry['id']);self.assertFalse(restored['archived']);self.assertEqual(restored['definition'],value);self.assertEqual(restored['project_id'],'kept-project');self.assertEqual(source.read_text(),'Keep original')
                w.categories.setCurrentRow(0)

    def test_cancel_stale_selection_and_keyboard_scope(self):
        w=self.window();entry=w.collection.create('tool','Selected',value={'prompt':'Keep'});w.refresh();self.select(w,entry['id'])
        with patch('code_trash.confirm',return_value=False):QTest.mouseClick(w.trash_selection,Qt.LeftButton)
        self.assertEqual(w.collection.get(entry['id'])['revision'],1)
        w.collection.update(entry['id'],1,title='New title')
        with patch('code_trash.confirm',return_value=True):QTest.mouseClick(w.trash_selection,Qt.LeftButton)
        self.assertFalse(w.collection.get(entry['id'])['archived']);self.assertIn('inzwischen',w.status.text())
        w.refresh();self.select(w,entry['id']);w.search.setFocus()
        with patch('code_trash.confirm') as question:QTest.keyClick(w.search,Qt.Key_Delete);self.assertFalse(question.called)
        w.entries.setFocus();QTest.qWait(10)
        with patch('code_trash.confirm',return_value=True):QTest.keyClick(w.entries,Qt.Key_Delete)
        self.assertTrue(w.collection.get(entry['id'])['archived'])
        w.categories.setCurrentRow(w.category_keys.index('archive'));w.trash_selection.setFocus();QTest.keyClick(w.trash_selection,Qt.Key_Space)
        self.assertFalse(w.collection.get(entry['id'])['archived'])

    def test_context_menu_binds_clicked_row_even_if_selection_changes(self):
        w=self.window();a=w.collection.create('tool','A');b=w.collection.create('tool','B');w.refresh();row=self.select(w,a['id'])
        point=w.entries.visualItemRect(row).center()
        def execute():
            menu=QApplication.activePopupWidget();self.select(w,b['id'])
            QTest.mouseClick(menu,Qt.LeftButton,pos=menu.actionGeometry(menu.actions()[0]).center())
        QTimer.singleShot(10,execute)
        with patch('code_trash.confirm',return_value=True):w.entries.customContextMenuRequested.emit(point)
        self.assertTrue(w.collection.get(a['id'])['archived']);self.assertFalse(w.collection.get(b['id'])['archived'])

    def test_open_coding_window_guard_and_regular_details_close(self):
        from code_session import CodingWindow
        w=self.window();folder=w.store.directory/'repo';folder.mkdir();(folder/'source.txt').write_text('kept')
        entry=w.collection.create('code','Project',value={'directory':str(folder),'draft_prompt':'Unsent'})
        with patch('assistant_backend.OpenCodeBackend.refresh_sessions'):
            w.open_entry(entry['id']);editor=w.coding_windows[entry['id']];QTest.qWait(40)
            w.refresh();self.select(w,entry['id'])
            with patch('code_trash.confirm') as question:QTest.mouseClick(w.trash_selection,Qt.LeftButton);self.assertFalse(question.called)
            self.assertFalse(w.collection.get(entry['id'])['archived']);self.assertIn('geöffnet',w.status.text())
            editor.chat.backend.busy=True;QTest.mouseClick(editor.collection_details,Qt.LeftButton);self.assertTrue(editor.isVisible())
            editor.chat.backend.busy=False;editor.chat.composer.setPlainText('New unsent draft');QTest.mouseClick(editor.collection_details,Qt.LeftButton);QTest.qWait(30)
            self.assertEqual(w.pages.currentIndex(),1);self.assertEqual(w.current['id'],entry['id']);self.assertEqual(w.collection.get(entry['id'])['definition']['draft_prompt'],'New unsent draft')
            with patch('code_trash.confirm',return_value=True):QTest.mouseClick(w.archive,Qt.LeftButton)
            self.assertTrue(w.collection.get(entry['id'])['archived']);self.assertEqual((folder/'source.txt').read_text(),'kept')

    def test_running_work_is_preserved_and_schedules_restore_paused(self):
        from code_blocks import node,encode
        from code_blocks_run import Runs
        from code_clock import default
        from code_triggers import Triggers
        w=self.window();entry=w.collection.create('tool','Running',value={'prompt':'Wait'});task=w.store.create_task('Running',prompt='Wait');w.collection.used(entry['id'],task);w.store.update_task(task,status='running')
        w.store.event(task,'code-library',entry['id']);newer=w.store.create_task('Newer');w.store.update_task(newer,status='completed');w.collection.used(entry['id'],newer)
        with self.assertRaisesRegex(ValueError,'laufenden'):w.collection.update(entry['id'],1,archived=True)
        self.assertEqual(w.store.task(task)['status'],'running');self.assertFalse(w.collection.get(entry['id'])['archived'])
        flow=w.store.save_workflow('Schedule',[],[str(w.store.directory)],prompt='Keep',approved=True,enabled=True)
        source={'kind':'text','text':'kept','trigger':{'kind':'clock','clock':{**default(),'kind':'interval','minutes':15}}}
        auto=w.collection.create('automation','Scheduled',value={'workflow_id':flow,'flow':encode({'version':3,'nodes':[node('manual',json.dumps(source)),node('filter_text','kept')]})})
        trigger=Triggers(w.collection);trigger.activate(auto['id'],100);runs=Runs(w.collection);run=runs.create(auto['id']);runs.resume(run['id'])
        with self.assertRaisesRegex(ValueError,'laufenden'):w.collection.update(auto['id'],1,archived=True)
        runs.control(run['id'],'cancel');w.refresh();self.select(w,auto['id'])
        queued=runs.create(auto['id'],event={'background':True})
        with self.assertRaisesRegex(ValueError,'laufenden'):w.collection.update(auto['id'],1,archived=True)
        runs.control(queued['id'],'cancel')
        with patch('code_trash.confirm',return_value=True):QTest.mouseClick(w.trash_selection,Qt.LeftButton)
        self.assertFalse(trigger.get(auto['id'])['enabled']);self.assertFalse(w.store.workflows()[0]['enabled']);self.assertTrue(w.store.workflows()[0]['approved'])
        w.categories.setCurrentRow(w.category_keys.index('archive'));QTest.mouseClick(w.trash_selection,Qt.LeftButton)
        self.assertFalse(trigger.get(auto['id'])['enabled']);self.assertFalse(w.store.workflows()[0]['enabled']);self.assertEqual(w.collection.get(auto['id'])['definition'],auto['definition'])

    def test_cancel_dirty_detail_and_automation_leaves_revision_and_trigger_unchanged(self):
        from code_blocks import node,encode
        from code_blocks_window import BlockWindow
        from code_clock import default
        from code_triggers import Triggers
        w=self.window();entry=w.collection.create('tool','Original',value={'prompt':'Keep'});w.open_entry(entry['id']);w.title.setText('Unsaved')
        with patch('code_trash.confirm',return_value=False):QTest.mouseClick(w.archive,Qt.LeftButton)
        self.assertEqual(w.collection.get(entry['id']),entry);self.assertTrue(w.dirty);self.assertEqual(w.title.text(),'Unsaved')
        w.loading=True;w.title.setText('Original');w.loading=False;w.dirty=False
        source={'kind':'text','text':'kept','trigger':{'kind':'clock','clock':{**default(),'kind':'interval','minutes':15}}}
        auto=w.collection.create('automation','Saved automation',value={'flow':encode({'version':3,'nodes':[node('manual',json.dumps(source)),node('filter_text','kept')]})});triggers=Triggers(w.collection);triggers.activate(auto['id'],100)
        editor=BlockWindow(w.collection,auto['id']);self.addCleanup(editor.deleteLater);editor.show();editor.title_edit.setFocus();editor.title_edit.selectAll();QTest.keyClicks(editor.title_edit,'Unsaved automation');before=triggers.get(auto['id'])
        with patch('code_trash.confirm',return_value=False):editor.archive()
        self.assertEqual(w.collection.get(auto['id']),auto);self.assertEqual(triggers.get(auto['id']),before);self.assertTrue(editor.dirty);self.assertEqual(editor.title_edit.text(),'Unsaved automation')
        editor.dirty=False;editor.done(0)

    def test_native_cancel_keeps_editor_and_target_unchanged(self):
        from PySide6.QtWidgets import QPushButton
        w=self.window();flow=w.store.save_workflow('Native',[{'action':'diagnose'}],[str(w.store.directory)],approved=True)
        entry=w.collection.create('automation','Native',value={'workflow_id':flow})
        def cancel():
            dialog=QApplication.activeModalWidget();more=next(b for b in dialog.findChildren(QPushButton) if b.text()=='Mehr')
            next(a for a in more.menu().actions() if a.text()=='In den Papierkorb').trigger()
            self.assertTrue(dialog.isVisible());self.assertEqual(w.collection.get(entry['id']),entry);dialog.reject()
        QTimer.singleShot(10,cancel)
        with patch('code_trash.confirm',return_value=False):w.open_native_flow(entry['id'])
        self.assertFalse(w.collection.get(entry['id'])['archived'])

    def test_dirty_detail_refusal_keeps_definition_revision_schedule_and_running_task(self):
        from code_flow import encode
        w=self.window();source=w.store.directory/'original.txt';source.write_text('Original')
        plan=dict(trigger='interval',minutes=15,watch='',cron='0 9 * * *',timezone='Europe/Zurich',steps=[{'title':'Keep','prompt':'Keep'}],condition='changed',outputs=['notify'],source_ids=[],service_ids=[])
        flow=w.store.save_workflow('Original',[],[str(w.store.directory)],trigger='interval',prompt='Keep',approved=True,enabled=True,code_plan=encode(plan))
        entry=w.collection.create('automation','Original',value={'flow':encode(plan),'workflow_id':flow,'directory':str(w.store.directory)})
        w.open_entry(entry['id']);w.title.setText('Unsaved title');before=w.store.workflows()[0];tasks=[]
        def confirm(*_):
            task=w.store.create_task('External run',prompt='Keep');w.store.event(task,'workflow',flow);w.store.update_task(task,status='running');tasks.append(task);return True
        with patch('code_trash.confirm',side_effect=confirm):QTest.mouseClick(w.archive,Qt.LeftButton)
        self.assertIn('laufenden',w.status.text());self.assertEqual(w.collection.get(entry['id']),entry);self.assertEqual(w.store.workflows()[0],before)
        self.assertEqual(w.store.task(tasks[0])['status'],'running');self.assertTrue(w.dirty);self.assertEqual(w.title.text(),'Unsaved title');self.assertEqual(source.read_text(),'Original')
        w.store.update_task(tasks[0],status='cancelled')
        with patch('code_trash.confirm',return_value=True):QTest.mouseClick(w.archive,Qt.LeftButton)
        saved=w.collection.get(entry['id']);self.assertTrue(saved['archived']);self.assertEqual(saved['title'],'Unsaved title');self.assertEqual(saved['revision'],entry['revision']+1);self.assertFalse(w.store.workflows()[0]['enabled'])

    def test_dirty_block_refusal_keeps_definition_revision_trigger_and_running_run(self):
        from code_blocks import node,encode
        from code_blocks_run import Runs
        from code_blocks_window import BlockWindow
        from code_clock import default
        from code_triggers import Triggers
        w=self.window();source=w.store.directory/'original.txt';source.write_text('Original')
        config={'kind':'text','text':'Original','trigger':{'kind':'clock','clock':{**default(),'kind':'interval','minutes':15}}}
        entry=w.collection.create('automation','Original',value={'flow':encode({'version':3,'nodes':[node('manual',json.dumps(config)),node('filter_text','Original')]})})
        triggers=Triggers(w.collection);editor=BlockWindow(w.collection,entry['id']);self.addCleanup(editor.deleteLater);editor.show();editor.title_edit.setFocus();editor.title_edit.selectAll();QTest.keyClicks(editor.title_edit,'Unsaved title')
        triggers.activate(entry['id'],100);before=triggers.get(entry['id']);runs=Runs(w.collection);active=[]
        def confirm(*_):
            run=runs.create(entry['id'],event={'background':True});runs.resume(run['id']);active.append(runs.get(run['id']));return True
        with patch('code_trash.confirm',side_effect=confirm),self.assertRaisesRegex(ValueError,'laufenden'):editor.archive()
        self.assertEqual(w.collection.get(entry['id']),entry);self.assertEqual(triggers.get(entry['id']),before);self.assertEqual(runs.get(active[0]['id']),active[0])
        self.assertTrue(editor.dirty);self.assertEqual(editor.title_edit.text(),'Unsaved title');self.assertEqual(source.read_text(),'Original')
        runs.control(active[0]['id'],'cancel')
        with patch('code_trash.confirm',return_value=True):editor.archive()
        saved=w.collection.get(entry['id']);self.assertTrue(saved['archived']);self.assertEqual(saved['title'],'Unsaved title');self.assertEqual(saved['revision'],entry['revision']+1);self.assertFalse(triggers.get(entry['id'])['enabled']);self.assertEqual(source.read_text(),'Original')
