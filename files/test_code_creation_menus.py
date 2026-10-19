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
    def test_small_creation_keeps_review_reachable_and_validation_visible(self):
        from code_creation import CreationDialog
        from PySide6.QtCore import QPoint
        d=CreationDialog(kind='tool');self.addCleanup(lambda:d.done(0));d.show();d.resize(960,640);QTest.qWait(60)
        self.assertEqual((d.width(),d.height()),(960,640))
        d.review();QTest.qWait(30)
        self.assertTrue(d.error.isVisible());self.assertIn('Auftrag',d.error.text())
        self.assertTrue(d.rect().contains(d.review_button.mapTo(d,QPoint(0,d.review_button.height()-1))))
        d.show_goal();QTest.qWait(30)
        self.assertEqual((d.width(),d.height()),(960,640))
        self.assertTrue(d.goal.isVisible())

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

    def test_dedicated_editors_keep_context_and_formulation_links_return_to_flow(self):
        from code_creation import CreationDialog
        from PySide6.QtWidgets import QPushButton,QWidget
        from desktop_design import AppHeader
        for kind in ('tool','routine','automation','code'):
            with self.subTest(kind=kind):
                d=CreationDialog(kind=kind);self.addCleanup(self.dispose,d);d.show();QTest.qWait(10)
                self.assertIsNone(d.findChild(QWidget,'codeRail'))
                self.assertEqual(len([w for w in d.findChildren(AppHeader) if w.isVisible()]),1)
                self.assertTrue(d.header.title.text().startswith('Lumen'))
                self.assertTrue(d.forms[kind].isVisible());self.assertTrue(d.review_button.isVisible())
                if kind=='code':self.assertFalse(d.name.isVisible())
                if kind=='tool':self.assertTrue(d.forms[kind].example.isVisible());self.assertTrue(d.test_result.isVisible())
                if kind=='automation':
                    from code_block_paths import starter
                    editor=d.flow_editor;editor.set_plan(starter());editor.edit_gate();editor.dialog_apply.click();plan=editor.plan();editor.open_detail('gate');link=next(w for w in editor.findChildren(QPushButton) if w.text()=='Bedingung in Worten beschreiben')
                    link.click();self.assertEqual(editor.tabs.currentIndex(),1)
                    back=next(w for w in editor.tabs.currentWidget().findChildren(QPushButton) if w.text()=='‹ Zurück zum Ablauf')
                    back.click();self.assertEqual(editor.tabs.currentIndex(),0);self.assertEqual(editor.plan(),plan)
                d.hide()

    def test_code_folder_supplies_title_without_creating_or_cloning(self):
        from code_creation import CreationDialog
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'Mein Projekt';folder.mkdir()
            d=CreationDialog(kind='code');self.addCleanup(self.dispose,d);d.forms['code'].directory.setText(str(folder));d.review()
            self.assertEqual(d.value['title'],'Mein Projekt')
            self.assertEqual(list(folder.iterdir()),[]);self.assertIsNone(d.job)
            d.pages.setCurrentIndex(1);d.code_name_toggle.click();self.assertFalse(d.name.isHidden())
            d.name.setText('Eigener Name');d.show_goal();d.select_kind('tool');d.select_kind('code')
            self.assertEqual(d.name.text(),'Eigener Name');d.review();self.assertEqual(d.value['title'],'Eigener Name')

    def test_routine_creation_opens_saved_entry_without_second_creation_editor(self):
        from code_creation_forms import RoutineForm
        from code_library_window import CollectionWindow
        with tempfile.TemporaryDirectory() as tmp:
            w=CollectionWindow(Store(tmp));self.addCleanup(w.close)
            from code_flow import encode
            from code_clock import default
            legacy=dict(trigger='schedule',minutes=60,watch='',cron='',timezone='Europe/Zurich',clock=default(),steps=[dict(title='Neuer Schritt',prompt='Offene Punkte zusammenfassen')],condition='always',outputs=['notify'],source_ids=[],service_ids=[])
            value=dict(kind='automation',title='Morgenroutine',description='',definition={'flow':encode(legacy)},project_id='')
            w.categories.setCurrentRow(w.category_keys.index('routine'))
            self.assertEqual(w.create_button.text(),'Routine zusammenstellen')
            with patch('code_creation.CreationDialog') as dialog,patch.object(w,'open_entry') as opened,patch('code_edit_window.EditDialog') as editor:
                dialog.return_value.exec.return_value=1;dialog.return_value.kind='routine';dialog.return_value.value=value
                w.create();editor.assert_not_called();opened.assert_called_once()
            item=w.collection.get(opened.call_args.args[0]);self.assertEqual(item['title'],'Morgenroutine')
            w.open_entry(item['id'],blocks=False)
            self.assertTrue(w.input.isHidden());self.assertTrue(w.prompt.isHidden())
            self.assertIn('Neuer Schritt',w.routine_overview.text());self.assertTrue(w.directory.isReadOnly());self.assertFalse(w.choose_directory_button.isEnabled())
            self.assertFalse(w.store.workflows())

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
        editor=SectionsEditor();self.addCleanup(self.dispose,editor);editor.items.append(node('notify'))
        editor.gate_enabled=True;editor.gate=node('condition',json.dumps({'field':'sender','op':'contains','value':'team'}));editor.refresh()
        with self.assertRaises(ValueError):editor.plan()
        editor.items[0]['config']=json.dumps({'kind':'message','text':'Hello','sender':'team@example.test'});editor.select_entry('gate');self.assertEqual(editor.plan()['version'],3)
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
            d=CreationDialog(tools=[tool],kind='routine');self.addCleanup(self.dispose,d);form=d.forms['routine']
            from code_block_paths import config
            form.items[0]['config']=json.dumps({**config(form.items[0]),'text':'Beispieltext'});form.refresh()
            add=next(w for w in form.findChildren(QComboBox) if w.accessibleName()=='Aktion hinzufügen')
            index=next(i for i in range(add.count()) if isinstance(add.itemData(i),dict));add.setCurrentIndex(index);add.activated.emit(index)
            d.review();value=json.loads(d.value['definition']['flow']);copied=next(n for n in value['nodes'] if n['title'].startswith('Text prüfen'))
            self.assertEqual(copied['config'],tool['definition']['prompt']);self.assertIn('Version 1',copied['title']);self.assertEqual(json.loads(value['nodes'][0]['config'])['trigger']['clock']['kind'],'weekly');self.assertEqual(d.value['definition']['editor'],'routine')
            c.create('app','Vorhanden',value={'html':'<p>Bestehend</p>'})
            w=CollectionWindow(c.store);self.addCleanup(w.close);w.categories.setCurrentRow(w.category_keys.index('app'));self.assertEqual(w.entries.topLevelItemCount(),1)

    def test_condition_model_suggestion_requires_apply_and_rejects_stale(self):
        from code_sections_editor import SectionsEditor
        editor=SectionsEditor();self.addCleanup(self.dispose,editor);editor.proposal_fields={'text'};editor.proposal_source='text';editor.proposal_text='Nur Rechnungen';editor.description.setPlainText(editor.proposal_text)
        editor.described(True,json.dumps({'condition':{'field':'text','op':'contains','value':'Rechnung'},'explanation':'Nur Rechnungstext'}))
        self.assertFalse(editor.gate_enabled);editor.description.setPlainText('Geändert');editor.accept_condition();self.assertFalse(editor.gate_enabled)
        editor.description.setPlainText(editor.proposal_text);editor.accept_condition();self.assertTrue(editor.gate_enabled)
        with self.assertRaises(ValueError):editor.plan()
        from code_blocks import node
        editor.items.append(node('notify'));editor.plan()

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
        editor.items[0]['config']=json.dumps({'kind':'file','path':'/synthetic/input.txt'});editor.refresh()
        editor.open_detail('input')
        path=next(w for w in editor.findChildren(QLineEdit) if w.accessibleName()=='Quelldatei')
        self.assertTrue(path.isReadOnly());editor.set_locked(True);editor.refresh()
        folds=[w for w in editor.findChildren(QPushButton) if w.objectName()=='sentencePart']
        self.assertTrue(all(w.isEnabled() for w in folds))
        self.assertTrue(all(not w.isEnabled() for w in editor.inspector.findChildren(QComboBox)))
        self.assertFalse(editor.dialog_apply.isEnabled())
        editor.set_locked(False);editor.refresh()
        path=next(w for w in editor.findChildren(QLineEdit) if w.accessibleName()=='Quelldatei');self.assertTrue(path.isReadOnly())

    def test_model_flow_is_reviewed_and_source_paths_do_not_come_from_model(self):
        from code_block_paths import generated,proposal
        value=generated(json.dumps({'steps':[{'kind':'read_file','title':'Lesen','config':'/private/model-invented'},{'kind':'notify','title':'Melden','config':''}]}))
        self.assertEqual(value['nodes'][1]['config'],'')
        with self.assertRaises(ValueError):generated('{"steps":[{"kind":"shell","title":"x","config":"whoami"}]}')
        self.assertIn('Keine Werkzeuge',proposal('Lies und melde'))

if __name__=='__main__':unittest.main()
