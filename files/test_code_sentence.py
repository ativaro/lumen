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

    def test_legacy_v2_has_no_start_gate_and_is_lossless(self):
        from code_blocks import node
        plan={'version':2,'nodes':[node('manual'),node('notify')]}
        w=SentenceEditor(plan=plan);self.addCleanup(self.dispose,w);w.show()
        self.assertFalse(w.condition_button.isVisible());w.edit_gate()
        self.assertIsNone(w.dialog);self.assertEqual(w.plan(),plan)

    def test_source_file_cancel_emits_no_committed_change(self):
        from PySide6.QtWidgets import QComboBox
        w=SentenceEditor();self.addCleanup(self.dispose,w);original=w.plan(False);changes=[];w.changed.connect(lambda:changes.append(True))
        w.open_detail('input');source=next(c for c in w.inspector.findChildren(QComboBox) if c.accessibleName()=='Eingabequelle')
        index=source.findData('file');source.setCurrentIndex(index);source.activated.emit(index)
        with patch('code_sections_editor.QFileDialog.getOpenFileName',return_value=('/tmp/synthetic.txt','')):
            next(b for b in w.inspector.findChildren(QPushButton) if b.text()=='Datei wählen').click()
        self.assertEqual(changes,[]);w.dialog.reject();self.assertEqual(w.plan(False),original);self.assertEqual(changes,[])

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


if __name__=='__main__':unittest.main()
