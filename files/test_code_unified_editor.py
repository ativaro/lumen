"""One UI preserves old execution plans and only activates a tested saved plan."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QLineEdit,QComboBox,QMessageBox
from PySide6.QtCore import QCoreApplication,QEvent
from code_blocks import node,encode
from code_blocks_run import digest,Runs
from code_block_paths import flatten
from code_library import Collection
from lumen_store import Store
from code_sections_editor import SectionsEditor
from code_blocks_window import BlockWindow


class UnifiedEditorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.app=QApplication.instance() or create_app()

    def dispose(self,w):
        if isinstance(w,BlockWindow):
            w.dirty=False;w.reject()
        else:w.shutdown();w.close()
        w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_legacy_pdf_and_nested_paths_preserve_signatures_and_ids(self):
        branch=node('choose');loop=node('for_each');loop.update(steps=[node('approval')],end=node('end_each',loop['id']))
        branch.update(cases=[{'when':{'field':'text','op':'exists','value':True},'steps':[loop]}],otherwise=[node('notify')])
        legacy={'version':2,'nodes':[node('manual','historical input'),node('read_file','/tmp/example.pdf'),node('if_pdf'),node('approval'),node('save_note','Notes'),node('notify')]}
        modern=flatten([node('manual',json.dumps({'kind':'text','text':'a\nb'})),branch])
        for plan in (legacy,modern):
            editor=SectionsEditor(plan=plan);self.addCleanup(self.dispose,editor)
            for n in plan['nodes']:
                if n['kind']!='end_each':editor.select_entry('input' if n['kind']=='manual' else n['id'])
                self.assertEqual(digest(editor.plan()),digest(plan))
            editor.set_locked(True)
            self.assertTrue(all(b.isEnabled() for b,_,_ in editor.summaries.values()))

    def test_title_save_test_activation_and_edit_revocation(self):
        from code_clock import default
        from code_triggers import Triggers
        from test_code_triggers import Job
        with tempfile.TemporaryDirectory() as tmp:
            c=Collection(Store(tmp));plan={'version':3,'nodes':[node('manual',json.dumps({'kind':'text','text':'alpha','trigger':{'kind':'clock','clock':{**default(),'kind':'daily'}}})),node('filter_text','alpha')]}
            entry=c.create('automation','Before',value={'flow':encode(plan)});w=BlockWindow(c,entry['id']);self.addCleanup(self.dispose,w)
            with self.assertRaisesRegex(ValueError,'erfolgreich testen'):w.toggle_trigger()
            runs=Runs(c);test=runs.create(entry['id'],True);runs.resume(test['id']);runs.advance(test['id'],Job());runs.advance(test['id'],Job())
            w.refresh_run()
            with patch('code_blocks_window.QMessageBox.question',return_value=QMessageBox.Yes),patch('lumen_actions.command'):w.toggle_trigger()
            self.assertTrue(Triggers(c).get(entry['id'])['enabled'])
            w.editor.update_node(w.editor.items[1],'config','beta');self.assertTrue(w.dirty);self.assertFalse(Triggers(c).get(entry['id'])['enabled'])
            w.title_edit.setText('After');w.save();self.assertEqual(c.get(entry['id'])['title'],'After');self.assertFalse(w.activation_button.isEnabled())
            self.assertIn('früheren Entwurf',w.result_view.toPlainText())

    def test_editing_nested_action_reorder_remove_and_add_targets_real_branch(self):
        branch=node('choose');one=node('ai','one');two=node('approval');branch.update(cases=[{'when':{'field':'text','op':'exists','value':True},'steps':[one,two]}],otherwise=[])
        w=SectionsEditor(plan=flatten([node('manual',json.dumps({'kind':'text','text':'abc'})),branch]));self.addCleanup(self.dispose,w)
        w.select_entry(one['id']);edit=next(x for x in w.findChildren(QLineEdit) if x.accessibleName()=='Bezeichnung');edit.textEdited.emit('Changed')
        self.assertEqual(w.plan()['nodes'][2]['title'],'Changed')
        from PySide6.QtWidgets import QPushButton
        menu=next(b.menu() for b in w.inspector.findChildren(QPushButton) if b.text()=='Mehr')
        next(a for a in menu.actions() if a.text()=='Nach unten').trigger()
        self.assertEqual(w.items[1]['cases'][0]['steps'][1]['id'],one['id'])
        menu=next(b.menu() for b in w.inspector.findChildren(QPushButton) if b.text()=='Mehr')
        next(a for a in menu.actions() if a.text()=='Aktion entfernen').trigger()
        self.assertEqual(len(w.items[1]['cases'][0]['steps']),1)
        self.assertEqual(w.selected,'input');self.assertTrue(w.summaries['input'][0].isChecked())
        w.select_entry(branch['id']);add=next(x for x in w.inspector.findChildren(QComboBox) if x.accessibleName()=='Aktion hinzufügen');i=add.findData('notify');add.setCurrentIndex(i);add.activated.emit(i)
        self.assertEqual(w.items[1]['cases'][0]['steps'][-1]['kind'],'notify');w.plan()

    def test_skipped_actions_or_new_unfinished_test_do_not_enable_activation(self):
        from test_code_triggers import Job
        with tempfile.TemporaryDirectory() as tmp:
            c=Collection(Store(tmp));plan={'version':3,'nodes':[node('manual',json.dumps({'kind':'text','text':'alpha'})),node('condition',json.dumps({'field':'text','op':'contains','value':'beta'})),node('notify')]}
            entry=c.create('automation','Filter',value={'flow':encode(plan)});w=BlockWindow(c,entry['id']);self.addCleanup(self.dispose,w)
            runs=Runs(c);test=runs.create(entry['id'],True);runs.resume(test['id']);runs.advance(test['id'],Job());runs.advance(test['id'],Job())
            self.assertEqual(runs.get(test['id'])['status'],'completed');self.assertFalse(w.passed_test())
            w.editor.gate['config']=json.dumps({'field':'text','op':'contains','value':'alpha'});w.changed();w.save()
            test=runs.create(entry['id'],True);runs.resume(test['id'])
            for _ in range(3):runs.advance(test['id'],Job())
            self.assertTrue(w.passed_test())
            runs.create(entry['id'],True);self.assertFalse(w.passed_test())

if __name__=='__main__':unittest.main()
