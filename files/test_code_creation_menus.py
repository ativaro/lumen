import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QDialog,QComboBox,QLineEdit,QCheckBox,QMessageBox
from PySide6.QtTest import QTest
from code_library import Collection
from lumen_store import Store

class CreationMenus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.root.cleanup)
        cls.env=patch.dict(os.environ,{'LUMEN_DATA':cls.root.name+'/state','LUMEN_TOOLS_DATA':cls.root.name+'/tools','XDG_CONFIG_HOME':cls.root.name+'/config','LUMEN_LANGUAGE':'de'});cls.env.start();cls.addClassCleanup(cls.env.stop)
        from app import create_app
        cls.app=QApplication.instance() or create_app()

    def dispose(self,w):
        if hasattr(w,'done'):w.done(0)
        elif hasattr(w,'shutdown'):w.shutdown()
        w.deleteLater();QTest.qWait(5)

    def test_project_is_created_only_after_review_and_confirmation(self):
        from code_creation import CreationDialog
        with tempfile.TemporaryDirectory() as tmp:
            d=CreationDialog(kind='code');self.addCleanup(self.dispose,d);d.show();QTest.qWait(10)
            form=d.forms['code'];form.source.setCurrentIndex(form.source.findData('new'));target=Path(tmp)/'new';form.directory.setText(str(target));d.name.setText('Neues Projekt')
            d.review();self.assertEqual(d.pages.currentIndex(),2);self.assertFalse(target.exists());d.create()
            for _ in range(100):
                QTest.qWait(10)
                if d.job is None:break
            self.assertTrue(target.is_dir());self.assertEqual(d.result(),QDialog.Accepted)
            self.assertFalse(list(Path(tmp).glob('.lumen-project-*')))

    def test_source_fields_are_dynamic_and_old_conditions_fail_closed(self):
        from code_sections_editor import SectionsEditor
        from code_blocks import node
        editor=SectionsEditor();self.addCleanup(self.dispose,editor)
        editor.gate_enabled=True;editor.gate=node('condition',json.dumps({'field':'sender','op':'contains','value':'team'}));editor.refresh()
        with self.assertRaises(ValueError):editor.plan()
        editor.items[0]['config']=json.dumps({'kind':'message','text':'Hello','sender':'team@example.test'});editor.refresh();self.assertEqual(editor.plan()['version'],3)
        from code_condition_ui import ConditionEditor
        controls=editor.findChildren(ConditionEditor)
        fields=next(c for c in controls if c.available and 'sender' in c.available)
        self.assertNotIn('matched',fields.available)
        fields.mode.setCurrentIndex(fields.mode.findData('any'));self.assertIn('any',fields.value())

    def test_routine_freezes_tool_and_old_apps_stay_available(self):
        from code_creation import CreationDialog
        from code_library_window import CollectionWindow
        with tempfile.TemporaryDirectory() as tmp:
            c=Collection(Store(tmp));tool=c.create('tool','Text prüfen',value={'prompt':'Fehlende Angaben nennen'})
            d=CreationDialog(tools=[tool],kind='routine');self.addCleanup(self.dispose,d);form=d.forms['routine'];form.tools.setCurrentIndex(1);form.use_tool();self.assertEqual(len(form.steps),1)
            d.review();value=json.loads(d.value['definition']['flow']);self.assertEqual(value['steps'][0]['tool_revision'],tool['revision']);self.assertEqual(value['clock']['kind'],'weekly')
            c.create('app','Vorhanden',value={'html':'<p>Bestehend</p>'})
            w=CollectionWindow(c.store);self.addCleanup(w.close);w.categories.setCurrentRow(w.category_keys.index('app'));self.assertEqual(w.entries.topLevelItemCount(),1)

    def test_condition_model_suggestion_requires_apply_and_rejects_stale(self):
        from code_sections_editor import SectionsEditor
        editor=SectionsEditor();self.addCleanup(self.dispose,editor);editor.proposal_fields={'text'};editor.proposal_source='text';editor.proposal_text='Nur Rechnungen';editor.description.setPlainText(editor.proposal_text)
        editor.described(True,json.dumps({'condition':{'field':'text','op':'contains','value':'Rechnung'},'explanation':'Nur Rechnungstext'}))
        self.assertFalse(editor.gate_enabled);editor.description.setPlainText('Geändert');editor.accept_condition();self.assertFalse(editor.gate_enabled)
        editor.description.setPlainText(editor.proposal_text);editor.accept_condition();self.assertTrue(editor.gate_enabled);editor.plan()

    def test_editors_preserve_condition_signature_before_user_changes(self):
        from code_conditions import describe
        from code_condition_ui import ConditionEditor
        from code_block_paths import flatten
        from code_sections_editor import SectionsEditor
        from code_blocks import node
        from code_blocks_run import digest
        for value in ({'field':'hour','op':'greater','value':12},{'not':{'field':'hour','op':'greater','value':12}},{'any':[{'field':'hour','op':'equals','value':8}]}):
            c=ConditionEditor({'hour'},value);self.addCleanup(self.dispose,c);self.assertEqual(json.dumps(c.value()),json.dumps(value))
        start=node('manual',json.dumps({'kind':'text','text':'abc'}));branch=node('choose');branch.update(cases=[{'when':{'field':'text','op':'contains','value':'a'},'steps':[node('approval')]}],otherwise=[node('notify')]);plan=flatten([start,branch])
        editor=SectionsEditor(plan=plan);self.addCleanup(self.dispose,editor);self.assertEqual(digest(editor.plan()),digest(plan))

    def test_locked_inspector_stays_readable_and_source_paths_stay_readonly(self):
        from code_sections_editor import SectionsEditor
        from PySide6.QtWidgets import QPushButton,QPlainTextEdit
        editor=SectionsEditor();self.addCleanup(self.dispose,editor)
        editor.items[0]['config']=json.dumps({'kind':'file','path':'/synthetic/input.txt'});editor.open_ids.add('input');editor.refresh()
        path=next(w for w in editor.findChildren(QLineEdit) if w.accessibleName()=='Quelldatei')
        self.assertTrue(path.isReadOnly());editor.set_locked(True);editor.refresh()
        folds=[w for w in editor.findChildren(QPushButton) if w.objectName()=='codeFold']
        self.assertTrue(all(w.isEnabled() for w in folds))
        self.assertTrue(all(not w.isEnabled() for w in editor.scroll.widget().findChildren(QComboBox)))
        editor.set_locked(False);editor.refresh()
        path=next(w for w in editor.findChildren(QLineEdit) if w.accessibleName()=='Quelldatei');self.assertTrue(path.isReadOnly())

    def test_model_flow_is_reviewed_and_source_paths_do_not_come_from_model(self):
        from code_block_paths import generated,proposal
        value=generated(json.dumps({'steps':[{'kind':'read_file','title':'Lesen','config':'/private/model-invented'},{'kind':'notify','title':'Melden','config':''}]}))
        self.assertEqual(value['nodes'][1]['config'],'')
        with self.assertRaises(ValueError):generated('{"steps":[{"kind":"shell","title":"x","config":"whoami"}]}')
        self.assertIn('Keine Werkzeuge',proposal('Lies und melde'))

if __name__=='__main__':unittest.main()
