import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt,QCoreApplication,QEvent
from code_blocks import node,encode
from code_sections_editor import SectionsEditor
from PySide6.QtWidgets import QLineEdit
from code_blocks_window import BlockWindow
from code_library import Collection
from lumen_store import Store



class BlocksUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.root.cleanup)
        cls.env=patch.dict(os.environ,{'LUMEN_DATA':cls.root.name+'/state','LUMEN_TOOLS_DATA':cls.root.name+'/tools','XDG_CONFIG_HOME':cls.root.name+'/config','LUMEN_LANGUAGE':'de'})
        cls.env.start();cls.addClassCleanup(cls.env.stop)
        from app import create_app
        cls.app=QApplication.instance() or create_app()

    @staticmethod
    def dispose(widget):
        if isinstance(widget,BlockWindow):widget.reject()
        elif hasattr(widget,'done'):widget.done(0)
        else:widget.close()
        widget.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_editor_keyboard_structure_and_creation(self):
        editor=SectionsEditor(plan=dict(version=2,nodes=[node('manual'),node('ai','Prüfen')]))
        self.addCleanup(self.dispose,editor);editor.resize(950,580);editor.show();QTest.qWait(20)
        editor.select_entry(editor.items[1]['id']);QTest.qWait(20);title=next(w for w in editor.findChildren(QLineEdit) if w.accessibleName()=='Bezeichnung');title.setFocus();title.selectAll();QTest.keyClicks(title,'Dokument verstehen')
        self.assertEqual(editor.plan()['nodes'][1]['title'],'Dokument verstehen');self.assertTrue(title.hasFocus());self.assertEqual(editor.plan()['version'],2)
        editor.set_locked(True);self.assertTrue(title.isReadOnly())
        from code_creation import CreationDialog
        dialog=CreationDialog();self.addCleanup(self.dispose,dialog);dialog.select_kind('automation');dialog.review();self.assertIsNone(dialog.value)
        dialog.flow_editor.choose_action('notify',dialog.flow_editor.items,0);dialog.flow_editor.dialog_apply.click();dialog.review()
        self.assertEqual(dialog.value['kind'],'automation');self.assertEqual(__import__('json').loads(dialog.value['definition']['flow'])['version'],3)

    def test_real_test_pause_approval_from_other_selection_and_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'beleg.txt';source.write_text('Echter Beleg 42 CHF.')
            collection=Collection(Store(Path(tmp)/'state'))
            plan=dict(version=2,nodes=[node('manual'),node('read_file',str(source)),node('approval'),node('save_file',tmp),node('notify')])
            entry=collection.create('automation','Belege',value={'flow':encode(plan)})
            window=BlockWindow(collection,entry['id']);window.show();self.addCleanup(self.dispose,window)
            with patch('code_blocks_window.QMessageBox.question',return_value=QMessageBox.Yes):window.start(True)
            for _ in range(100):
                QTest.qWait(10);time.sleep(.005)
                if window.run['status']=='waiting':break
            self.assertEqual(window.run['status'],'waiting');self.assertTrue(window.approve_button.isVisible())
            window.editor.select_entry('input');window.editor.dialog.reject();window.approve()
            for _ in range(100):
                QTest.qWait(10);time.sleep(.005)
                if window.run['status']=='completed' and not window.job:break
            self.assertEqual(window.run['status'],'completed');self.assertEqual(window.run['data']['steps'][2]['output']['approval'],'Bestätigt')
            self.assertFalse(list(Path(tmp).glob('Lumen-*.md')))
            window.reject();reopened=BlockWindow(collection,entry['id']);self.addCleanup(self.dispose,reopened)
            self.assertEqual(reopened.run['status'],'completed')
            self.assertIn('42 CHF',reopened.result_view.toPlainText())

    def test_v3_branch_signature_approval_inspection_and_resume(self):
        import json
        from code_block_paths import flatten
        from PySide6.QtWidgets import QPushButton
        with tempfile.TemporaryDirectory() as tmp:
            c=Collection(Store(tmp));branch=node('choose');branch.update(cases=[{'when':{'field':'text','op':'contains','value':'abc'},'steps':[node('approval'),node('notify')]}],otherwise=[node('notify')])
            plan=flatten([node('manual',json.dumps({'kind':'text','text':'abc'})),branch]);entry=c.create('automation','Wege',value={'flow':encode(plan)})
            w=BlockWindow(c,entry['id']);self.addCleanup(self.dispose,w);w.show()
            with patch('code_blocks_window.QMessageBox.question',return_value=QMessageBox.Yes):w.start(True)
            for _ in range(300):
                QTest.qWait(10);time.sleep(.005)
                if w.run['status']=='waiting' and w.job is None:break
            self.assertEqual(w.run['status'],'waiting');self.assertTrue(w.editor.locked);self.assertTrue(w.approve_button.isVisible())
            self.assertTrue(all(b.isEnabled() for b in w.editor.findChildren(QPushButton) if b.objectName()=='codeFlowRow'))
            w.approve()
            for _ in range(300):
                QTest.qWait(10);time.sleep(.005)
                if w.run['status']=='completed' and w.job is None:break
            self.assertEqual(w.run['status'],'completed');self.assertEqual(w.run['data']['steps'][-1]['status'],'skipped')
            w.reject();reopened=BlockWindow(c,entry['id']);self.addCleanup(self.dispose,reopened);self.assertEqual(reopened.run['status'],'completed')

    def test_failed_target_resume_and_save_invalidation(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'input.txt';source.write_text('Daten')
            collection=Collection(Store(Path(tmp)/'state'))
            entry=collection.create('automation','Prüfen',value={'flow':encode(dict(version=2,nodes=[node('manual'),node('read_file',str(source)),node('notify')]))})
            window=BlockWindow(collection,entry['id']);self.addCleanup(self.dispose,window);window.show()
            window.editor.select_entry(window.editor.items[1]['id']);QTest.qWait(20);title=next(w for w in window.editor.findChildren(QLineEdit) if w.accessibleName()=='Bezeichnung');title.setFocus();title.selectAll();QTest.keyClicks(title,'Lesen')
            self.assertEqual(title.text(),'Lesen');self.assertFalse(window.dirty);window.editor.dialog_apply.click();self.assertTrue(window.dirty);window.save()
            with patch('code_blocks_window.QMessageBox.question',return_value=QMessageBox.Yes):window.start(True)
            window.pause()
            for _ in range(100):
                QTest.qWait(10);time.sleep(.005)
                # The queued idle callback releases the lease after job.finished.
                if window.job is None and window.lease_fd is None:break
            self.assertEqual(window.run['status'],'paused');self.assertIsNone(window.lease_fd)
            window.resume()
            for _ in range(100):
                QTest.qWait(10);time.sleep(.005)
                if window.run['status']=='completed' and not window.job:break
            self.assertEqual(window.run['status'],'completed')
            window.reject()


    def test_orphaned_run_can_resume_after_reopening(self):
        from code_blocks_run import Runs
        from lumen_jobs import Job
        with tempfile.TemporaryDirectory() as tmp:
            collection=Collection(Store(tmp));entry=collection.create('automation','Freigabe',value={'flow':encode(dict(version=2,nodes=[node('manual'),node('approval')]))})
            runs=Runs(collection);run=runs.create(entry['id']);runs.resume(run['id']);runs.advance(run['id'],Job(lambda _:None))
            window=BlockWindow(collection,entry['id']);self.addCleanup(self.dispose,window)
            self.assertEqual(window.run['status'],'paused');window.resume()
            for _ in range(100):
                QTest.qWait(10);time.sleep(.005)
                if window.run['status']=='waiting' and not window.job:break
            self.assertEqual(window.run['status'],'waiting');window.approve()
            self.assertEqual(window.run['status'],'completed');window.reject()


    def test_collection_metadata_archive_and_legacy_timer_remain_available(self):
        from code_library_window import CollectionWindow
        from code_flow_editor import FlowEditor
        with tempfile.TemporaryDirectory() as tmp:
            window=CollectionWindow(Store(tmp));self.addCleanup(self.dispose,window)
            entry=window.collection.create('automation','Metadaten',value={'flow':encode(dict(version=2,nodes=[node('manual'),node('approval')]))})
            with patch('code_blocks_window.BlockWindow.exec',return_value=0) as opened:
                window.open_entry(entry['id'],blocks=False);self.assertTrue(opened.called)
            for child in window.findChildren(BlockWindow):child.reject()
            editor=BlockWindow(window.collection,entry['id']);self.addCleanup(self.dispose,editor)
            editor.title_edit.setText('Eigener Name');editor.save();self.assertEqual(window.collection.get(entry['id'])['title'],'Eigener Name')
            window.current=window.collection.get(entry['id'])
            with patch('code_blocks_window.BlockWindow.exec',return_value=0) as opened:
                window.execute();self.assertTrue(opened.called);self.assertFalse(window.store.tasks())
                window.toggle_favorite();self.assertTrue(window.current['favorite'])
            for child in window.findChildren(BlockWindow):
                if child is not editor:child.reject()
            editor.item=window.collection.get(entry['id'])
            with patch('code_trash.confirm',return_value=True):editor.archive()
            self.assertTrue(window.collection.get(entry['id'])['archived'])
            legacy=FlowEditor();self.addCleanup(self.dispose,legacy);legacy.show();legacy.trigger.setCurrentIndex(1)
            self.assertTrue(legacy.watch_row.isVisible());self.assertFalse(legacy.minutes.isVisible())


    def test_pause_before_queued_ai_callback_does_not_send_data(self):
        from code_blocks_run import Runs
        from lumen_jobs import Job
        with tempfile.TemporaryDirectory() as tmp:
            collection=Collection(Store(tmp));entry=collection.create('automation','KI',value={'flow':encode(dict(version=2,nodes=[node('manual'),node('ai','Zusammenfassen')]))})
            runs=Runs(collection);run=runs.create(entry['id']);runs.resume(run['id']);runs.advance(run['id'],Job(lambda _:None));value=runs.advance(run['id'],Job(lambda _:None))
            window=BlockWindow(collection,entry['id']);self.addCleanup(self.dispose,window)
            self.assertEqual(window.run['status'],'paused')
            with patch('assistant_backend.OpenCodeBackend') as backend:window.advanced(value);backend.assert_not_called()
            window.reject()

if __name__=='__main__':unittest.main()
