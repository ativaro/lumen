"""The file action sentence must preserve its typed actions and approval."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication, QEvent, QTimer, Qt
from PySide6.QtWidgets import QApplication, QDialog, QFrame, QListWidget, QMenu, QMessageBox, QTabWidget
from PySide6.QtTest import QTest
from plan_dialog import PlanDialog, StepDialog
from lumen_store import Store


class NativeSentenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.app=QApplication.instance() or create_app()

    def setUp(self):
        self.tmp=self.enterContext(tempfile.TemporaryDirectory()); self.root=Path(self.tmp)
        self.windows=[]

    def tearDown(self):
        for window in self.windows:window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);self.app.processEvents()

    def dialog(self,value=None,file_action=True):
        d=PlanDialog(None,value,file_action=file_action);self.windows.append(d);return d

    def value(self):
        return dict(name='Dienst prüfen',roots=[str(self.root)],steps=[dict(action='restart_service',unit='lumen-demo.service',scope='system')],prompt='',approved=True)

    def test_empty_sentence_and_unchanged_task_preparation(self):
        d=self.dialog();self.assertEqual(d.steps.count(),0);self.assertEqual(d.prompt.toPlainText(),'')
        self.assertIsNotNone(d.findChild(QFrame,'sentence'));self.assertEqual(d.findChildren(QTabWidget),[])
        d.name.setText('Leer');d.approve.setChecked(True);d.save();self.assertIsNone(d.value)
        task=self.dialog(self.value(),file_action=False)
        self.assertEqual(task.findChildren(QTabWidget)[0].count(),3)
        self.assertIsNone(task.findChild(QFrame,'sentence'))
        with patch('code_sentence_native.QMessageBox.question') as question:task.reject();question.assert_not_called()

    def test_native_save_reopen_keeps_fields_scope_and_identity(self):
        value=self.value();value['name']='Ein bestehender Automationsname'.ljust(200,'x');d=self.dialog(value)
        self.assertFalse(d.approve.isChecked());d.save();self.assertIsNone(d.value)
        d.approve.setChecked(True);d.show();QTest.qWait(10);d.name.setFocus();QTest.keyClick(d.name,Qt.Key_Return)
        self.assertEqual(d.value,value)
        store=Store(self.root/'state');identity=store.save_file_action(**d.value)
        loaded=store.file_actions()[0];reopened=self.dialog(loaded)
        self.assertFalse(reopened.approve.isChecked());reopened.approve.setChecked(True)
        reopened.save();self.assertEqual(reopened.value,value)
        rows=store.file_actions();self.assertEqual(len(rows),1);self.assertEqual(rows[0]['id'],identity)
        self.assertEqual(rows[0]['steps'],value['steps']);self.assertEqual(rows[0]['roots'],value['roots'])
        self.assertEqual(rows[0]['trigger'],'manual');self.assertFalse(rows[0]['enabled'])
        self.assertNotIn('nodes',rows[0]['steps'][0]);self.assertEqual(rows[0]['steps'][0]['scope'],'system')

    def test_sentence_and_editor_keep_the_same_field_order(self):
        step=dict(action='copy',path=str(self.root/'Ziel.txt'),source=str(self.root/'Quelle.txt'))
        d=self.dialog(dict(self.value(),steps=[step]));d.approve.setChecked(True);d.save()
        store=Store(self.root/'state');store.save_file_action(**d.value)
        reopened=self.dialog(store.file_actions()[0]);reopened.native_sentence.refresh()
        captions=[part.caption.text() for part in reopened.native_sentence.parts]
        # A long temporary folder elides the middle of a path; its file name stays.
        self.assertEqual([caption.rsplit('/',1)[-1] for caption in captions[1:3]],['Quelle.txt','Ziel.txt'])
        editor=StepDialog(reopened,step);self.windows.append(editor)
        self.assertEqual(list(editor.controls),['source','path'])

    def test_prompt_and_placeholders_remain_literal(self):
        value=self.value();value.update(steps=[],prompt='Prüfe {{datei}} im Ordner {{ordner}} und frage vor Änderungen.')
        d=self.dialog(value);d.approve.setChecked(True);d.save()
        self.assertEqual(d.value,value);self.assertNotIn('flow',d.value)
        d=self.dialog(self.value());d.prompt.setPlainText('Zweiter Auftrag');d.approve.setChecked(True);d.save()
        self.assertIsNone(d.value);self.assertTrue(d.steps.count());self.assertEqual(d.prompt.toPlainText(),'Zweiter Auftrag')

    def test_all_native_actions_and_scope_remain_editable(self):
        from lumen_actions import ACTIONS,validate_steps
        parent=self.dialog()
        values={'path':str(self.root/'ziel.txt'),'source':str(self.root/'quelle.txt'),'text':'Inhalt {{datei}}',
                'desktop':'org.kde.kate.desktop','unit':'lumen-demo.service','scope':'system','packages':'ripgrep'}
        for kind,(_,fields) in ACTIONS.items():
            step={'action':kind,**{key:values[key] for key in fields}}
            d=StepDialog(parent,step);self.windows.append(d)
            self.assertEqual(d.step(),step);validate_steps([d.step()])
            self.assertEqual(d.action.count(),len(ACTIONS))

    def test_step_order_and_modal_cancel_preserve_data(self):
        d=self.dialog(self.value());d.add_step_item(dict(action='diagnose'));d.move_step(-1)
        self.assertEqual(d.steps.item(0).data(Qt.UserRole),{'action':'diagnose'})
        before=d.native_sentence.snapshot()
        def reject_modal(modal):
            roots=modal.findChild(QListWidget,'codeSteps')
            self.assertTrue(roots.accessibleName());roots.clear();return QDialog.Rejected
        with patch.object(QDialog,'exec',reject_modal):d.native_sentence.permissions()
        self.assertEqual(d.native_sentence.snapshot(),before)
        d.steps.takeItem(0);self.assertEqual(d.steps.count(),1)
        self.assertEqual(d.steps.item(0).data(Qt.UserRole)['scope'],'system')

    def test_action_menu_opens_at_the_focused_action(self):
        d=self.dialog(self.value());d.show();QTest.qWait(20)
        button=d.native_sentence.menu_buttons[0];button.setFocus();locations=[]
        def close_menu():
            menu=self.app.activePopupWidget()
            if isinstance(menu,QMenu):locations.append(menu.geometry());menu.close()
        QTimer.singleShot(0,close_menu);QTest.keyClick(button,Qt.Key_Space)
        self.assertEqual(len(locations),1)
        anchor=button.mapToGlobal(button.rect().bottomLeft())
        self.assertEqual(locations[0].top(),anchor.y())
        self.assertLessEqual(abs(locations[0].left()-anchor.x()),locations[0].width())

    def test_long_path_is_compact_only_in_the_sentence(self):
        path=str(self.root/('ausführlicher Ordnername/'*12)/'Beleg.pdf')
        d=self.dialog(dict(self.value(),steps=[dict(action='open',path=path)]))
        part=d.native_sentence.parts[1]
        self.assertIn('…',part.caption.text());self.assertTrue(part.caption.text().endswith('Beleg.pdf'))
        self.assertEqual(part.accessibleDescription(),path);self.assertIn(path,part.toolTip())
        editor=StepDialog(d,dict(action='open',path=path));self.windows.append(editor)
        self.assertEqual(editor.controls['path'].text(),path)
        d.approve.setChecked(True);d.save();self.assertEqual(d.value['steps'][0]['path'],path)

    def test_dirty_close_cancel_discard_and_save(self):
        d=self.dialog(self.value());d.show();QTest.qWait(20);d.name.setText('Geändert')
        with patch('code_sentence_native.QMessageBox.question',return_value=QMessageBox.Cancel):d.reject()
        self.assertTrue(d.isVisible());self.assertIsNone(d.value)
        with patch('code_sentence_native.QMessageBox.question',return_value=QMessageBox.Discard):d.reject()
        self.assertFalse(d.isVisible());self.assertIsNone(d.value)
        saved=self.dialog(self.value());saved.show();QTest.qWait(20);saved.name.setText('Gespeichert');saved.approve.setChecked(True)
        with patch('code_sentence_native.QMessageBox.question',return_value=QMessageBox.Save):saved.reject()
        self.assertEqual(saved.result(),QDialog.Accepted);self.assertEqual(saved.value['name'],'Gespeichert')

    def test_a_file_action_has_no_start_setting(self):
        d=self.dialog(self.value());d.show();QTest.qWait(20)
        for retired in ('trigger','interval','watch','enable'):self.assertFalse(hasattr(d,retired),retired)
        self.assertFalse(hasattr(d.native_sentence,'start_part'));self.assertFalse(hasattr(d.native_sentence,'start'))
        self.assertEqual(sorted(d.value or {}),[]);d.approve.setChecked(True);d.save()
        self.assertEqual(sorted(d.value),['approved','name','prompt','roots','steps'])
