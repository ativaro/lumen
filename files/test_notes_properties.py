import unittest
from notes_properties import change,values,filters,matches


class PropertiesTest(unittest.TestCase):
    def test_add_edit_delete_preserves_unknown_yaml_and_body(self):
        text='---\nstatus: offen # comment\nforeign: {items: [a, b]}\n---\n# Note\nBody 🌍\n'
        new=change(text,'status',value='done: yes')
        self.assertIn('status: "done: yes" # comment',new);self.assertIn('foreign: {items: [a, b]}',new)
        new=change(new,'due','date','2026-10-14');self.assertEqual(values(new)['due'],{'kind':'date','value':'2026-10-14'})
        self.assertTrue(new.endswith('# Note\nBody 🌍\n'));self.assertNotIn('status:',change(new,'status',remove=True))
        self.assertEqual(values(change('# Note','status',value='open'))['status']['value'],'open')
    def test_invalid_ambiguous_and_anchored_metadata_are_rejected(self):
        for text in ('---\nstatus: [x\n---\n','---\nstatus: a\nstatus: b\n---\n','---\nbase: &a open\nstatus: *a\n---\n','---\nstatus: {a: b}\n---\n'):
            with self.subTest(text=text),self.assertRaises(ValueError):change(text,'status',value='new')
        for value in ('2026-02-30','20261014','tomorrow'):
            with self.assertRaises(ValueError):change('# Note','due','date',value)
        with self.assertRaises(ValueError):change('# Note','tags',value='x')
    def test_block_scalar_and_filters(self):
        text='---\nsummary: |\n  First\n  Second\nstatus: open\n---\nBody'
        changed=change(text,'summary',value='Short');self.assertEqual(values(changed)['status']['value'],'open')
        self.assertIn('status: open',change(text,'summary',remove=True))
        query,selected=filters('Report #project [status=OPEN] [due=2026-10-14]')
        self.assertEqual(query.strip(),'Report #project');self.assertTrue(matches(change(text,'due','date','2026-10-14'),selected))
        self.assertFalse(matches(text,selected))

    def test_property_and_tag_text_search_are_combined(self):
        from wissen_data import parse,search
        notes=[parse('a.md',b'---\nstatus: open\ntags: [project]\n---\n# Report'),parse('b.md',b'---\nstatus: done\ntags: [project]\n---\n# Report')]
        self.assertEqual([n['path'] for n in search(notes,'Report #project [status=open]')],['a.md'])

class NativePropertiesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def wait(self,check):
        from PySide6.QtTest import QTest
        for _ in range(600):
            QTest.qWait(20)
            if check():return
        self.fail('Properties timed out')
    def test_grid_save_cancel_stale_and_preserved_body_undo(self):
        import tempfile,os
        from pathlib import Path
        from unittest.mock import patch
        from PySide6.QtCore import QEvent
        from tools_wissen import Wissen
        from notes_properties_ui import PropertiesDialog
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'LUMEN_DATA':root+'/state','XDG_CONFIG_HOME':root+'/config'}):
            w=Wissen(Path(root)/'tools');w.show()
            try:
                self.wait(lambda:w.book and not w.job and not w.poller);w.poll_timer.stop();note=w.book.create('One','Original');w.scanned(w.book.scan());w.show_note(note)
                w.editor.appendPlainText('Typed');dialog=PropertiesDialog(w);dialog.add('status',value='open');dialog.add('due','date','2026-10-14');dialog.accept()
                self.assertEqual(values(w.document_text())['status']['value'],'open');w.editor.undo();self.assertNotIn('Typed',w.editor.toPlainText());self.assertIn('status',values(w.document_text()))
                w.save_note();self.wait(lambda:not w.job and not w.dirty);self.assertEqual(values(w.book.read(note['path'])['text'])['due']['value'],'2026-10-14')
                old=w.document_text();dialog=PropertiesDialog(w);dialog.add('extra',value='cancelled');dialog.reject();self.assertEqual(w.document_text(),old)
                dialog=PropertiesDialog(w);dialog.add('extra',value='stale');w.editor.appendPlainText('New edit');dialog.accept();self.assertNotIn('extra',values(w.document_text()));self.assertTrue(dialog.message.text())
                w.save_note();self.wait(lambda:not w.job and not w.dirty)
            finally:
                self.wait(lambda:not w.job and not w.poller and not w.live_preview.job);w.close();self.wait(lambda:not w.job);w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_saved_filters_sorting_restart_and_notebook_isolation(self):
        import tempfile,os
        from pathlib import Path
        from unittest.mock import patch
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QInputDialog
        from tools_wissen import Wissen
        import notes_views
        from wissen_data import Notebook
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'LUMEN_DATA':root+'/state','XDG_CONFIG_HOME':root+'/config'}):
            w=Wissen(Path(root)/'tools');w.show()
            try:
                self.wait(lambda:w.book and not w.job and not w.poller);w.poll_timer.stop()
                for name,status,due in [('Zebra','open','2026-10-14'),('Alpha','open','2026-10-15'),('Done','done','2026-10-13')]:
                    w.book.write(name+'.md',f'---\nstatus: {status}\ndue: {due}\n---\n# {name}','')
                w.scanned(w.book.scan());w.search.setText('[status=open]');notes_views.sort(w,'date')
                self.assertEqual([w.entries.item(i).text().split('\n')[0] for i in range(w.entries.count())],['Zebra','Alpha'])
                with patch.object(QInputDialog,'getText',return_value=('Open dates',True)):notes_views.save(w)
                identity=next(iter(notes_views.state(w)['saved']));old_book=w.book
                w.book=Notebook(w.store,Path(root)/'other',create=True);self.assertEqual(notes_views.state(w)['saved'],{});w.book=old_book
                w.close();self.wait(lambda:not w.job);w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
                w=Wissen(Path(root)/'tools');w.show();self.wait(lambda:w.book and not w.job and not w.poller);w.poll_timer.stop()
                self.assertEqual(w.search.text(),'[status=open]');self.assertEqual(w.view_sort,'date');self.assertEqual(w.entries.count(),2)
                self.assertEqual(w.views_button.text(),'Open dates');notes_views.remove(w,identity);self.assertEqual(notes_views.state(w)['saved'],{})
            finally:
                self.wait(lambda:not w.job and not w.poller and not w.live_preview.job);w.close();self.wait(lambda:not w.job);w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_default_order_does_not_replace_search_ranking(self):
        from notes_views import ordered
        notes=[dict(title='Z',path='z',text='',modified=1),dict(title='A',path='a',text='',modified=2)]
        self.assertEqual(ordered(notes,''),notes);self.assertEqual(ordered(notes,'title')[0]['path'],'a')

    def test_missing_saved_folder_never_expands_to_all_notes(self):
        import tempfile,os
        from pathlib import Path
        from unittest.mock import patch
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QInputDialog
        from tools_wissen import Wissen
        import notes_views
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'LUMEN_DATA':root+'/state','XDG_CONFIG_HOME':root+'/config'}):
            w=Wissen(Path(root)/'tools');w.show()
            try:
                self.wait(lambda:w.book and not w.job and not w.poller);w.poll_timer.stop()
                w.book.create_collection('Selected');w.book.create('Outside','Do not include');w.scanned(w.book.scan());w.collection='folder:Selected'
                with patch.object(QInputDialog,'getText',return_value=('Scoped',True)):notes_views.save(w)
                identity=notes_views.state(w)['active'];(w.book.root/'Selected').rmdir()
                w.scanned(w.book.scan());self.assertEqual(w.collection,'folder:Selected');self.assertEqual(w.entries.count(),0)
                with self.assertRaises(FileNotFoundError):notes_views.choose(w,identity)
            finally:
                self.wait(lambda:not w.job and not w.poller and not w.live_preview.job);w.close();self.wait(lambda:not w.job);w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
