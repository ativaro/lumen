"""Native sentence editing keeps strict plans and the real checkpoint runner."""
import json,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
from PySide6.QtWidgets import QApplication,QPushButton,QLineEdit,QDialog
from PySide6.QtTest import QTest
from PySide6.QtCore import QCoreApplication,QEvent
from code_sections_editor import SentenceEditor
from code_library import Collection
from lumen_store import Store
from code_blocks import encode


class SentenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.app=QApplication.instance() or create_app()

    def dispose(self,w):
        if isinstance(w,SentenceEditor):w.shutdown();w.close()
        else:w.dirty=False;w.reject()
        w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def add_notification(self,w,title='Workshop fertig'):
        w.pick_action();QTest.qWait(20)
        next(b for b in w.picker.findChildren(QPushButton) if b.property('actionKind')=='notify').click();QTest.qWait(20)
        field=next(x for x in w.inspector.findChildren(QLineEdit) if x.accessibleName()=='Bezeichnung')
        field.setText(title);field.textEdited.emit(title)
        return field

    def test_empty_action_cancel_apply_save_and_reopen(self):
        w=SentenceEditor();self.addCleanup(self.dispose,w);w.show();w.resize(960,640)
        self.assertEqual([n['kind'] for n in w.nodes],['manual'])
        with self.assertRaisesRegex(ValueError,'Aktion'):w.plan()
        original=w.plan(False);self.add_notification(w);w.dialog.reject();self.assertEqual(w.plan(False),original)
        self.add_notification(w);w.dialog_apply.click();self.assertIsNone(w.dialog)
        plan=w.plan();self.assertEqual([n['kind'] for n in plan['nodes']],['manual','notify'])
        with tempfile.TemporaryDirectory() as tmp:
            c=Collection(Store(tmp));entry=c.create('automation','Mein Ablauf',value={'flow':encode(plan)})
            from code_blocks_window import BlockWindow
            opened=BlockWindow(c,entry['id']);self.addCleanup(self.dispose,opened)
            self.assertEqual(opened.editor.plan(),plan)
            from code_blocks_run import Runs
            from test_code_triggers import Job
            runs=Runs(c);run=runs.create(entry['id'],True);runs.resume(run['id'])
            for _ in range(2):runs.advance(run['id'],Job())
            finished=runs.get(run['id']);self.assertEqual(finished['status'],'completed')
            self.assertTrue(finished['data']['steps'][1]['output']['effect']['test'])

    def test_cancelled_source_and_gate_never_change_the_plan(self):
        w=SentenceEditor();self.addCleanup(self.dispose,w);original=w.plan(False)
        w.open_detail('input');w.dialog.reject();self.assertEqual(w.plan(False),original)
        w.edit_gate();self.assertTrue(w.gate_enabled);w.dialog.reject();self.assertEqual(w.plan(False),original)

    def test_empty_creation_can_be_closed_and_uses_canonical_draft_changes(self):
        from code_creation import CreationDialog
        w=CreationDialog(kind='automation');self.addCleanup(lambda:w.done(0))
        original=w.fingerprint();self.add_notification(w.flow_editor);w.flow_editor.dialog_apply.click()
        self.assertNotEqual(w.fingerprint(),original)

    def test_creation_error_disappears_when_the_missing_action_is_added(self):
        from code_creation import CreationDialog
        w=CreationDialog(kind='automation');self.addCleanup(lambda:w.done(0));w.show();w.review()
        self.assertFalse(w.error.isHidden());self.assertIn('Aktion',w.error.text())
        self.add_notification(w.flow_editor);w.flow_editor.dialog_apply.click()
        self.assertTrue(w.error.isHidden());self.assertEqual(w.error.text(),'')

    def test_optional_gate_does_not_turn_an_empty_draft_into_a_saved_action(self):
        w=SentenceEditor();self.addCleanup(self.dispose,w);w.edit_gate();w.dialog_apply.click()
        self.assertTrue(w.gate_enabled)
        with self.assertRaisesRegex(ValueError,'Aktion'):w.plan()

    def test_duplicate_is_inactive_history_is_real_and_archive_preserves_it(self):
        from code_blocks import node
        from code_blocks_window import BlockWindow
        from code_blocks_run import Runs
        from code_triggers import Triggers
        from PySide6.QtWidgets import QTextBrowser,QMessageBox
        from test_code_triggers import Job
        with tempfile.TemporaryDirectory() as tmp:
            c=Collection(Store(tmp));plan={'version':3,'nodes':[node('manual',json.dumps({'kind':'text','text':'Synthetischer Beleg'})),node('notify',title='Nur Test')]}
            entry=c.create('automation','Original',value={'flow':encode(plan)});runs=Runs(c);run=runs.create(entry['id'],True);runs.resume(run['id'])
            for _ in range(2):runs.advance(run['id'],Job())
            w=BlockWindow(c,entry['id']);self.addCleanup(self.dispose,w);self.assertTrue(w.passed_test())
            rendered=[]
            def inspect(dialog):
                view=next(v for v in dialog.findChildren(QTextBrowser) if v.accessibleName()=='Durchlaufdetails');rendered.append(view.toPlainText());return QDialog.Rejected
            with patch.object(QDialog,'exec',inspect):w.history()
            self.assertIn('Synthetischer Beleg',rendered[0]);self.assertIn('Nur Test',rendered[0])
            copied=w.duplicate();self.assertNotEqual(copied['id'],entry['id']);self.assertFalse(w.passed_test());self.assertIsNone(Triggers(c).get(copied['id']))
            self.assertEqual(json.loads(copied['definition']['flow']),plan)
            with patch('code_blocks_window.QMessageBox.question',return_value=QMessageBox.Yes):w.archive()
            self.assertTrue(c.get(copied['id'])['archived']);self.assertFalse(c.get(entry['id'])['archived']);self.assertEqual(runs.get(run['id'])['status'],'completed')

    def test_latest_and_history_hide_machine_fields_until_details_are_requested(self):
        from code_blocks import node
        from code_blocks_window import BlockWindow
        from code_blocks_run import Runs
        from test_code_triggers import Job
        from PySide6.QtWidgets import QTextBrowser,QCheckBox
        with tempfile.TemporaryDirectory() as tmp:
            c=Collection(Store(tmp));plan={'version':3,'nodes':[node('manual',json.dumps({'kind':'text','text':'Beleg <42> CHF'})),node('notify',title='Beleg geprüft')]}
            entry=c.create('automation','Ergebnisse',value={'flow':encode(plan)});runs=Runs(c);run=runs.create(entry['id'],True);runs.resume(run['id'])
            for _ in range(2):runs.advance(run['id'],Job())
            w=BlockWindow(c,entry['id']);self.addCleanup(self.dispose,w)
            def readable(text):
                self.assertIn('Beleg <42> CHF',text);self.assertIn('Beleg geprüft',text);self.assertIn('Testausgabe',text)
                for raw in ('"weekday"','"success"','"input"','True'):self.assertNotIn(raw,text)
            readable(w.result_view.toPlainText());w.technical_details.setChecked(True);self.assertIn('"weekday"',w.result_view.toPlainText())
            def inspect(dialog):
                view=next(v for v in dialog.findChildren(QTextBrowser) if v.accessibleName()=='Durchlaufdetails');readable(view.toPlainText())
                next(v for v in dialog.findChildren(QCheckBox) if v.text()=='Technische Details').setChecked(True)
                self.assertIn('"weekday"',view.toPlainText());return QDialog.Rejected
            with patch.object(QDialog,'exec',inspect):w.history()
            failed=c.create('automation','Fehlerbezug',value={'flow':encode({'version':3,'nodes':[node('manual',json.dumps({'kind':'text','text':'Eingabe'})),node('read_file','/tmp/lumen-missing-result-source',title='Fehlende Quelle lesen')]})})
            run=runs.create(failed['id'],True);runs.resume(run['id'])
            for _ in range(2):runs.advance(run['id'],Job())
            broken=BlockWindow(c,failed['id']);self.addCleanup(self.dispose,broken);text=broken.result_view.toPlainText()
            self.assertLess(text.index('Fehlende Quelle lesen'),text.index('Manuell starten'));self.assertIn('Quelldatei: /tmp/lumen-missing-result-source',text)

    def test_collection_open_and_edit_routes_do_not_fall_back_to_metadata_inspector(self):
        from code_blocks import node
        from code_library_window import CollectionWindow
        with tempfile.TemporaryDirectory() as tmp:
            c=Collection(Store(tmp));entry=c.create('automation','Ein Weg',value={'flow':encode({'version':2,'nodes':[node('manual'),node('notify')]})})
            w=CollectionWindow(c.store);self.addCleanup(w.close)
            with patch('code_blocks_window.BlockWindow.exec',return_value=QDialog.Rejected) as opened,patch('code_edit_window.EditDialog',side_effect=AssertionError('Old editor reached')):
                w.open_entry(entry['id'],blocks=False);self.assertTrue(opened.called)
                w.current=c.get(entry['id']);w.edit_entry();self.assertEqual(opened.call_count,2)
                w.toggle_favorite();self.assertTrue(w.current['favorite']);self.assertEqual(opened.call_count,3)
            from code_blocks_window import BlockWindow
            for dialog in w.findChildren(BlockWindow):dialog.reject()

    def test_portable_description_stays_temporary_until_an_action_is_chosen(self):
        from code_creation import CreationDialog
        from code_library_contract import export_template
        from code_blocks import node
        with tempfile.TemporaryDirectory() as tmp:
            c=Collection(Store(tmp));item=c.create('automation','Quelle',value={'flow':encode({'version':2,'nodes':[node('manual'),node('notify')]})})
            portable=export_template(item);self.assertNotIn('flow',portable['definition'])
            d=CreationDialog(kind='automation');self.addCleanup(lambda:d.done(0));d.load_description(portable)
            self.assertEqual(len(d.flow_editor.items),1);self.assertEqual(d.flow_editor.full_description.toPlainText(),portable['definition']['prompt'])
            d.flow_editor.description_as_action();self.assertEqual(d.flow_editor.items[1]['kind'],'ai');d.flow_editor.dialog.reject();self.assertEqual(len(d.flow_editor.items),1)
            self.assertEqual(len(c.items()),1)

    def test_import_replaces_existing_draft_only_after_confirmation(self):
        from code_creation import CreationDialog
        from code_library_contract import export_template
        from code_blocks import node
        from PySide6.QtWidgets import QMessageBox,QLabel
        d=CreationDialog(kind='automation');self.addCleanup(lambda:d.done(0))
        previous={'version':3,'nodes':[node('manual',json.dumps({'kind':'file','path':'/tmp/previous-source.txt'})),node('notify',title='Vorherige Aktion')]}
        d.flow_editor.set_plan(previous);d.name.setText('Vorheriger Entwurf');d.flow_editor.full_description.setPlainText('Vorherige Beschreibung')
        d.flow_editor.full_candidate=previous;d.flow_editor.full_preview.setPlainText('Vorheriger Vorschlag');d.flow_editor.full_accept.show()
        d.flow_editor.proposal_layout.addWidget(QLabel('Vorherige Bedingung'));d.flow_editor.proposal_condition={'field':'text','op':'exists','value':True}
        portable=export_template({'kind':'automation','title':'Importierter Entwurf','description':'','definition':{'prompt':'Neuer Auftrag'}})
        original=d.fingerprint()
        with patch('code_creation.QMessageBox.question',return_value=QMessageBox.Cancel):d.load_description(portable)
        self.assertEqual(d.fingerprint(),original);self.assertEqual(d.flow_editor.full_candidate,previous)
        with patch('code_creation.QMessageBox.question',return_value=QMessageBox.Yes):d.load_description(portable)
        self.assertEqual(d.name.text(),'Importierter Entwurf');self.assertEqual([n['kind'] for n in d.flow_editor.items],['manual'])
        self.assertEqual(json.loads(d.flow_editor.items[0]['config']),{'kind':'text','text':''});self.assertIsNone(d.flow_editor.full_candidate)
        self.assertEqual(d.flow_editor.full_preview.toPlainText(),'');self.assertTrue(d.flow_editor.full_accept.isHidden())
        self.assertEqual(d.flow_editor.proposal_layout.count(),0);self.assertIsNone(d.flow_editor.proposal_condition)
        self.assertEqual(d.flow_editor.full_description.toPlainText(),'Neuer Auftrag')
        with self.assertRaisesRegex(ValueError,'Aktion'):d.flow_editor.plan()

    def test_native_collection_entry_opens_sentence_and_dispatches_after_close(self):
        from code_library_window import CollectionWindow
        from lumen_workspace import PlanDialog
        from PySide6.QtCore import Qt
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);steps=[{'action':'restart_service','unit':'lumen-synthetic.service','scope':'system'}]
            identity=store.save_workflow('Nativer Ablauf',steps,[tmp],approved=True)
            c=Collection(store);entry=c.create('automation','Sammlungseintrag',value={'workflow_id':identity})
            w=CollectionWindow(store);self.addCleanup(w.close);seen=[]
            def inspect(dialog):
                self.assertTrue(dialog.workflow);self.assertTrue(hasattr(dialog,'native_sentence'));self.assertFalse(w.pages.currentIndex())
                self.assertEqual(dialog.steps.item(0).data(Qt.UserRole),steps[0]);dialog.show();self.app.processEvents();seen.append(dialog)
                next(b for b in dialog.findChildren(QPushButton) if b.text()=='Jetzt ausführen').click();return dialog.result()
            def dispatch(task,action):
                self.assertFalse(seen[0].isVisible());self.assertEqual(action,'run')
                self.assertEqual(store.task(task)['steps'],steps);self.assertEqual(store.task(task)['roots'],[tmp])
            with patch.object(PlanDialog,'exec',inspect),patch('lumen_detail_routes.open_tasks') as opened,patch('lumen_detail_routes.task_action',side_effect=dispatch) as started:
                w.open_entry(entry['id']);self.assertTrue(started.called);self.assertTrue(opened.called)
            self.assertEqual(c.get(entry['id'])['definition'],{'workflow_id':identity});self.assertEqual(len(store.workflows()),1)
            with patch.object(PlanDialog,'exec',inspect),patch('code_library_execution.prepare_run',side_effect=ValueError('Freigegebener Ordner fehlt.')):
                w.show();w.safe(w.open_entry,entry['id']);self.assertEqual(w.pages.currentIndex(),0)
                self.assertTrue(w.footer.isVisible());self.assertEqual(w.footer.text(),'Freigegebener Ordner fehlt.')

    def test_native_draft_run_requires_save_and_explicit_approval(self):
        from code_library_window import CollectionWindow
        from lumen_workspace import PlanDialog
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);steps=[{'action':'diagnose'}];identity=store.save_workflow('Vorher',steps,[tmp],approved=True)
            c=Collection(store);entry=c.create('automation','Sammlungseintrag',value={'workflow_id':identity});w=CollectionWindow(store);self.addCleanup(w.close)
            def inspect(dialog):
                dialog.show();self.app.processEvents();dialog.name.setText('Nachher')
                next(b for b in dialog.findChildren(QPushButton) if b.text()=='Jetzt ausführen').click()
                self.assertTrue(dialog.isVisible());self.assertIn('Freigabe',dialog.error.text());self.assertIsNone(dialog.value)
                dialog.approve.setChecked(True);next(b for b in dialog.findChildren(QPushButton) if b.text()=='Jetzt ausführen').click()
                self.assertFalse(dialog.isVisible());return dialog.result()
            with patch.object(PlanDialog,'exec',inspect),patch('lumen_detail_routes.open_tasks'),patch('lumen_detail_routes.task_action') as started:
                w.open_entry(entry['id']);started.assert_called_once()
            flows=store.workflows();self.assertEqual(len(flows),1);self.assertEqual(flows[0]['id'],identity);self.assertEqual(flows[0]['name'],'Nachher')
            self.assertEqual(flows[0]['steps'],steps);self.assertEqual(flows[0]['roots'],[tmp]);self.assertTrue(flows[0]['approved'])

    def test_closing_changed_entry_requires_explicit_discard_or_save(self):
        from code_blocks import node
        from code_blocks_window import BlockWindow
        from PySide6.QtWidgets import QMessageBox
        with tempfile.TemporaryDirectory() as tmp:
            c=Collection(Store(tmp));entry=c.create('automation','Erhalten',value={'flow':encode({'version':2,'nodes':[node('manual'),node('notify')]})})
            w=BlockWindow(c,entry['id']);self.addCleanup(self.dispose,w);w.show();QTest.qWait(20)
            w.title_edit.setFocus();w.title_edit.selectAll();QTest.keyClicks(w.title_edit,'Noch nicht gespeichert')
            with patch('code_blocks_window.QMessageBox.question',return_value=QMessageBox.Cancel):w.reject()
            self.assertFalse(w.closed);self.assertEqual(c.get(entry['id'])['title'],'Erhalten')
            with patch('code_blocks_window.QMessageBox.question',return_value=QMessageBox.Discard):w.reject()
            self.assertTrue(w.closed);self.assertEqual(c.get(entry['id'])['title'],'Erhalten')

    def test_legacy_v2_has_no_start_gate_and_is_lossless(self):
        from code_blocks import node
        plan={'version':2,'nodes':[node('manual'),node('notify')]}
        w=SentenceEditor(plan=plan);self.addCleanup(self.dispose,w);w.show()
        self.assertFalse(w.condition_button.isVisible());w.edit_gate()
        self.assertIsNone(w.dialog);self.assertEqual(w.plan(),plan)

    def test_source_file_cancel_emits_no_committed_change(self):
        from PySide6.QtWidgets import QComboBox
        from PySide6.QtTest import QSignalSpy
        w=SentenceEditor();self.addCleanup(self.dispose,w);original=w.plan(False);changes=[];w.changed.connect(lambda:changes.append(True))
        spy=QSignalSpy(w.changed)
        w.open_detail('input');source=next(c for c in w.inspector.findChildren(QComboBox) if c.accessibleName()=='Eingabequelle')
        index=source.findData('file');source.setCurrentIndex(index);source.activated.emit(index)
        with patch('code_sections_editor.QFileDialog.getOpenFileName',return_value=('/tmp/synthetic.txt','')):
            next(b for b in w.inspector.findChildren(QPushButton) if b.text()=='Datei wählen').click()
        self.assertEqual(changes,[]);self.assertEqual(spy.count(),0);w.dialog.reject();self.assertEqual(w.plan(False),original);self.assertEqual(spy.count(),0)

    def test_description_on_empty_draft_reaches_proposal_without_weakening_validator(self):
        from PySide6.QtCore import QObject,Signal
        from PySide6.QtWidgets import QMessageBox
        class Backend(QObject):
            completed=Signal(bool,str)
            busy=False
            def __init__(self,*args,**kwargs):super().__init__();self.sent=[]
            def send(self,text,**kwargs):self.sent.append(text)
            def shutdown(self):pass
        w=SentenceEditor();self.addCleanup(self.dispose,w);w.full_description.setPlainText('Informiere mich auf Knopfdruck.')
        with patch('assistant_backend.OpenCodeBackend',Backend),patch('code_sections_editor.QMessageBox.question',return_value=QMessageBox.Yes):w.describe_flow()
        self.assertEqual(len(w.full_engine.sent),1)
        with self.assertRaises(ValueError):w.plan()
        w.flow_described(True,json.dumps({'steps':[{'kind':'notify','title':'Vorschlag A','config':''}]}))
        self.assertIsNotNone(w.full_candidate)
        w.full_description.setPlainText('Beschreibung B mit anderem Ziel')
        with patch('code_sections_editor.QMessageBox.question',return_value=QMessageBox.No):w.describe_flow()
        w.accept_flow()
        self.assertEqual(len(w.plan(False)['nodes']),1)
        self.assertIn('inzwischen',w.full_status.text())


if __name__=='__main__':unittest.main()
