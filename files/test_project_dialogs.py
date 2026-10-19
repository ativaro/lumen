import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QFileDialog,QLineEdit,QPlainTextEdit,QMessageBox
from PySide6.QtCore import QCoreApplication,QEvent
from tools_workbench import Workbench

class DialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.tmp=self.enterContext(tempfile.TemporaryDirectory());self.root=Path(self.tmp)
        self.enterContext(patch.dict(os.environ,LUMEN_TOOLS_DATA=self.tmp,LUMEN_DATA=self.tmp+'/state',XDG_CONFIG_HOME=self.tmp+'/config'))
        self.w=Workbench(self.root);self.w.error=lambda text:self.fail(text)
        self.resources=[dict(kind='url',title='Existing',target='https://example.org')]
        self.key=self.w.library.create('Coding',notes='Initial notes',goal='Initial goal',resources=self.resources,references=[])
        self.w.home.choose(self.key);self.w.show();self.app.processEvents()
    def tearDown(self):
        from shiboken6 import isValid
        if hasattr(self.w,'project_dialog') and isValid(self.w.project_dialog):self.w.project_dialog.reject()
        self.w.editor.discard();self.w.close();self.w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    def details(self):
        self.w.journal.edit.click();self.app.processEvents();return self.w.project_dialog
    def test_edit_only_details_and_save_preserves_sources(self):
        d=self.details();self.assertTrue(d.isVisible());self.assertFalse(self.w.editor.isVisible())
        self.assertEqual(len(d.findChildren(QLineEdit)),1);self.assertEqual(len(d.findChildren(QPlainTextEdit)),2)
        d.title.setText('Changed');d.notes.setPlainText('New notes');d.goal.setPlainText('New goal');d.apply.click()
        saved=self.w.library.get(self.key);self.assertEqual((saved['title'],saved['notes'],saved['goal']),('Changed','New notes','New goal'))
        self.assertEqual(saved['resources'],self.resources);self.assertEqual(self.w.journal.title.text(),'Changed')
        self.w.save();self.assertEqual(self.w.library.get(self.key)['goal'],'New goal')
    def test_cancel_and_escape_discard(self):
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt
        for escape in (False,True):
            d=self.details();d.title.setText('Unsaved')
            if escape:QTest.keyClick(d,Qt.Key_Escape)
            else:d.reject()
            self.assertEqual(self.w.library.get(self.key)['title'],'Coding')
    def test_conflict_and_revoked_permissions_preserve_draft(self):
        d=self.details();d.notes.setPlainText('Draft');self.w.library.update(self.key,notes='External');d.save()
        self.assertTrue(d.isVisible());self.assertFalse(d.error.isHidden());self.assertEqual(d.notes.toPlainText(),'Draft')
        self.assertEqual(self.w.library.get(self.key)['notes'],'External');d.reject()
        d=self.details();self.w.library.archive(self.key);d.save();self.assertFalse(d.error.isHidden());d.reject()
        d=self.details();self.assertFalse(d.apply.isEnabled());d.reject()
        self.w.library.archive(self.key,False);self.w.library.update(self.key,server_bound=True,server_role='reader')
        d=self.details();self.assertFalse(d.apply.isEnabled())
    def test_source_folder_cancel_then_save_changes_only_links(self):
        folder=self.root/'linked';folder.mkdir()
        for save in (False,True):
            self.w.journal.tabs.setCurrentIndex(1);self.w.journal.add_source.click();self.app.processEvents();d=self.w.project_dialog
            self.assertFalse(self.w.editor.isVisible());self.assertFalse(d.findChildren(QPlainTextEdit))
            self.assertEqual({d.kind.itemData(i) for i in range(d.kind.count())},{'file','folder','url','wissen'})
            d.kind.setCurrentIndex(d.kind.findData('folder'))
            with patch.object(QFileDialog,'getExistingDirectory',return_value=str(folder)):d.pick.click()
            self.assertEqual(self.w.library.get(self.key)['resources'],self.resources)
            if save:d.apply.click()
            else:d.reject()
        record=self.w.library.get(self.key);self.assertEqual(record['notes'],'Initial notes');self.assertEqual(record['goal'],'Initial goal')
        self.assertEqual(record['resources'][-1],dict(kind='folder',title='linked',target=str(folder)))
        with patch('tools_workbench.open_path') as opened:self.w.journal.open_material(1)
        opened.assert_called_once_with(str(folder));self.assertFalse(self.w.editor.isVisible())
    def test_invalid_url_does_not_write_and_notes_uses_original(self):
        from project_dialogs import open_dialog
        d=open_dialog(self.w,'url');d.address.setText('javascript:bad');d.save();self.assertFalse(d.error.isHidden());self.assertEqual(self.w.library.get(self.key)['resources'],self.resources);d.reject()
        d=open_dialog(self.w,'wissen')
        from wissen_data import Notebook
        book=Notebook(self.w.project_store,self.root/'notes',create=True);path=book.root/'source.md';path.parent.mkdir(parents=True,exist_ok=True);path.write_text('Original note')
        from PySide6.QtWidgets import QListWidgetItem
        from PySide6.QtCore import Qt
        ref=dict(app='wissen',kind='note',id='source.md',title='Original note',path=str(path),locator=dict(root=str(book.root),area='user'))
        item=QListWidgetItem('Original note');item.setData(Qt.UserRole,ref);d.notes.addItem(item);d.notes.setCurrentItem(item);d.choose();d.save()
        record=self.w.library.get(self.key);self.assertTrue(record['resources'][-1]['target'].startswith('lumen:'));self.assertEqual(record['notes'],'Initial notes');self.assertEqual(path.read_text(),'Original note')
    def test_cancel_notes_loading_keeps_window_alive_until_finished(self):
        import threading,time
        from PySide6.QtTest import QTest
        from project_dialogs import open_dialog
        release=threading.Event();started=threading.Event()
        def load(_):started.set();release.wait(5);return []
        with patch('project_material_editor.note_sources',side_effect=load):
            d=open_dialog(self.w,'wissen');d.choose();self.assertTrue(started.wait(1))
            d.reject();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
            self.assertTrue(self.w.project_source_jobs);self.assertFalse(self.w.close());self.assertTrue(self.w.isVisible())
            release.set();deadline=time.monotonic()+3
            while self.w.project_source_jobs and time.monotonic()<deadline:QTest.qWait(10)
            self.assertFalse(self.w.project_source_jobs);self.assertTrue(self.w.close())
    def test_source_unlink_keeps_original_and_details(self):
        from project_dialogs import remove_source
        with patch.object(QMessageBox,'question',return_value=QMessageBox.No):remove_source(self.w,self.key,self.resources[0])
        self.assertEqual(self.w.library.get(self.key)['resources'],self.resources)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):remove_source(self.w,self.key,self.resources[0])
        record=self.w.library.get(self.key);self.assertEqual(record['resources'],[]);self.assertEqual(record['notes'],'Initial notes');self.assertEqual(record['goal'],'Initial goal')
    def test_archive_remains_separate_from_details(self):
        with patch.object(self.w.project_trash,'confirm',return_value=True):self.w.journal.project_archive.trigger()
        self.assertTrue(self.w.library.get(self.key)['_archived'])
        self.w.home.choose(self.key);self.w.journal.project_archive.trigger();self.assertFalse(self.w.library.get(self.key)['_archived'])

    def test_existing_task_edit_still_scoped(self):
        parent=self.w.projects.add(self.key,'','Parent','initiative');task=self.w.projects.add(self.key,parent,'Task','analysis',goal='Task goal')
        self.w.navigate(self.key,task);self.w.goal.setPlainText('Task change')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):self.w.journal.edit.click()
        self.assertTrue(self.w.editor.isVisible());self.assertEqual(self.w.goal.toPlainText(),'Task change')
        self.w.editor.commit();self.assertEqual(self.w.projects.get(task)['goal'],'Task change')
        d=self.details();self.assertEqual(d.goal.toPlainText(),'Initial goal');d.goal.setPlainText('Root change');d.save()
        self.assertEqual(self.w.projects.get(task)['goal'],'Task change');self.assertEqual(self.w.library.get(self.key)['goal'],'Root change')

if __name__=='__main__':unittest.main()
