import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QTimer,QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QInputDialog
from notes_grid import Model,show
from notes_properties_ui import PropertiesDialog
from wissen_data import parse


class GridTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def wait(self,check):
        for _ in range(600):
            QTest.qWait(10)
            if check():return
        self.fail('Notes table timed out')
    def test_virtual_model_many_rows_and_sparse_properties(self):
        model=Model();notes=[parse(f'{i}.md',f'---\nstatus: open\n---\n# Note {i}'.encode()) for i in range(10000)]
        model.replace(notes);self.assertEqual(model.rowCount(),10000);self.assertEqual(model.columnCount(),4)
        self.assertEqual(model.data(model.index(9999,0)),'Note 9999');self.assertEqual(model.data(model.index(9999,3)),'open')
        self.assertFalse(model.flags(model.index(0,3))&Qt.ItemIsEditable)
        model.replace([parse('empty.md',b'# Empty')]);self.assertEqual(model.columnCount(),3)
    def test_edit_filter_and_saved_table_survive_restart(self):
        from tools_wissen import Wissen
        from notes_views import save
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'LUMEN_DATA':root+'/state','XDG_CONFIG_HOME':root+'/config'}):
            w=Wissen(Path(root)/'tools');w.show()
            try:
                self.wait(lambda:w.book and not w.job and not w.poller);w.poll_timer.stop()
                a=w.book.write('A.md','---\nstatus: open\nplugin: {keep: true}\n---\n# A\nBody','');w.book.write('B.md','---\nstatus: open\n---\n# B','')
                w.scanned(w.book.scan());w.search.setText('[status=open]');show(w);table=w.notes_table
                self.assertEqual(table.model.rowCount(),2)
                index=next(i for i,n in enumerate(table.model.notes) if n['path']=='A.md');table.grid.setCurrentIndex(table.model.index(index,3+table.model.fields.index('status')))
                timer=QTimer();seen=[]
                def accept():
                    dialog=QApplication.activeModalWidget()
                    if isinstance(dialog,PropertiesDialog):
                        row=next(i for i in range(dialog.grid.rowCount()) if dialog.grid.item(i,0).text()=='status')
                        dialog.grid.item(row,2).setText('done');timer.stop();seen.append(True);dialog.accept()
                timer.timeout.connect(accept);timer.start(20);table.edit()
                self.wait(lambda:seen and not w.job and not w.dirty);self.assertEqual(table.model.rowCount(),1)
                self.assertIn('plugin: {keep: true}',w.book.read('A.md')['text']);self.assertIn('done',w.book.read('A.md')['text'])
                with patch.object(QInputDialog,'getText',return_value=('Open table',True)):save(w,True)
                table.close();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
                table.reload();table.edit_note('A.md','status')  # Late save callbacks after closing are harmless.
                w.close();w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
                w=Wissen(Path(root)/'tools');w.show();self.wait(lambda:w.book and not w.job and not w.poller and getattr(w,'notes_table',None));w.poll_timer.stop()
                self.assertEqual(w.notes_table.model.rowCount(),1);self.assertEqual(w.search.text(),'[status=open]')
                w.notes_table.open_note();self.wait(lambda:not w.job);self.assertEqual(w.doc['path'],'B.md')
            finally:
                self.wait(lambda:not w.job and not w.poller and not w.live_preview.job)
                if getattr(w,'notes_table',None):w.notes_table.close()
                w.close();w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_external_edit_preserves_table_property_draft_and_notebook_boundary(self):
        from tools_wissen import Wissen
        from wissen_data import draft,Notebook
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'LUMEN_DATA':root+'/state','XDG_CONFIG_HOME':root+'/config'}):
            w=Wissen(Path(root)/'tools');w.show()
            try:
                self.wait(lambda:w.book and not w.job and not w.poller);w.poll_timer.stop()
                note=w.book.write('A.md','---\nstatus: open\n---\n# A\nOriginal','');w.scanned(w.book.scan());show(w);table=w.notes_table
                timer=QTimer();seen=[]
                def accept():
                    dialog=QApplication.activeModalWidget()
                    if isinstance(dialog,PropertiesDialog):
                        timer.stop();dialog.grid.item(0,2).setText('local')
                        w.book.write('A.md','---\nstatus: external\n---\n# A\nExternal',note['hash'])
                        seen.append(True);dialog.accept()
                timer.timeout.connect(accept);timer.start(20);table.edit()
                self.wait(lambda:seen and not w.job and w.conflict)
                self.assertIn('external',w.book.read('A.md')['text']);self.assertIn('local',draft(w.store,w.book.root,'A.md')['text'])
                w.dirty=False;w.autosave_timer.stop();w.draft_timer.stop()
                w.book=Notebook(w.store,Path(root)/'other',create=True);w.notes={};w.doc=None;w.refresh()
                self.assertIsNone(w.notes_table)
            finally:
                self.wait(lambda:not w.job and not w.poller and not w.live_preview.job)
                if getattr(w,'notes_table',None):w.notes_table.close()
                w.dirty=False;w.close();w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_changed_row_does_not_widen_saved_filter(self):
        from tools_wissen import Wissen
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'LUMEN_DATA':root+'/state','XDG_CONFIG_HOME':root+'/config'}):
            w=Wissen(Path(root)/'tools');w.show()
            try:
                self.wait(lambda:w.book and not w.job and not w.poller);w.poll_timer.stop()
                note=w.book.write('A.md','---\nstatus: open\n---\n# A','');w.book.create('Unrelated','Hidden by filter')
                w.scanned(w.book.scan());w.search.setText('[status=open]');show(w);table=w.notes_table
                w.book.write('A.md','---\nstatus: closed\n---\n# A',note['hash'])
                timer=QTimer();seen=[]
                def cancel():
                    dialog=QApplication.activeModalWidget()
                    if isinstance(dialog,PropertiesDialog):timer.stop();seen.append(True);dialog.reject()
                timer.timeout.connect(cancel);timer.start(20)
                table.grid.setCurrentIndex(table.model.index(0,3+table.model.fields.index('status')));table.grid.setFocus();QTest.qWait(30);QTest.keyClick(table.grid,Qt.Key_Return)
                self.wait(lambda:seen and not w.job)
                self.assertEqual(w.search.text(),'[status=open]');self.assertEqual(table.model.rowCount(),0)
            finally:
                self.wait(lambda:not w.job and not w.poller and not w.live_preview.job)
                if getattr(w,'notes_table',None):w.notes_table.close()
                w.close();w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)


if __name__=='__main__':unittest.main()
