import tempfile
import unittest
from pathlib import Path
from code_library import Collection
from lumen_store import Store


class EditUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        from unittest.mock import patch
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.environment=patch.dict(os.environ,{'LUMEN_DATA':cls.temp.name+'/state','LUMEN_TOOLS_DATA':cls.temp.name+'/tools','XDG_CONFIG_HOME':cls.temp.name+'/config','QT_QPA_PLATFORM':'offscreen','LUMEN_LANGUAGE':'de'})
        cls.environment.start();cls.addClassCleanup(cls.environment.stop)
        from app import create_app
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or create_app()

    def test_tool_review_save_discard_and_conflict(self):
        from code_edit_window import EditDialog
        from unittest.mock import patch
        from PySide6.QtWidgets import QDialog
        with tempfile.TemporaryDirectory() as tmp:
            c=Collection(Store(tmp));item=c.create('tool','Prüfen',value={'prompt':'Freier bestehender Auftrag'})
            w=EditDialog(c,item);self.addCleanup(lambda:w.done(0))
            self.assertFalse(w.review_button.isEnabled());w.name.setText('Neue Prüfung')
            self.assertTrue(w.review_button.isEnabled());w.discard(confirm=False)
            self.assertEqual(w.name.text(),'Prüfen');self.assertFalse(w.review_button.isEnabled())
            w.name.setText('Umbenannt')
            with patch.object(QDialog,'exec',return_value=QDialog.Accepted):w.review()
            self.assertEqual(c.get(item['id'])['title'],'Umbenannt')
            self.assertEqual(c.get(item['id'])['definition']['prompt'],'Freier bestehender Auftrag')
            # A second window cannot overwrite changes made since opening.
            other=EditDialog(c,c.get(item['id']));self.addCleanup(lambda:other.done(0))
            current=c.get(item['id']);c.update(item['id'],current['revision'],title='Extern')
            other.name.setText('Veraltet')
            with patch.object(QDialog,'exec',return_value=QDialog.Accepted):other.review()
            self.assertIn('inzwischen',other.status.text());self.assertEqual(other.name.text(),'Veraltet')

    def test_routine_schedule_shared_draft_save_and_explicit_activation(self):
        from code_edit_window import EditDialog
        from unittest.mock import patch
        from PySide6.QtWidgets import QDialog
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);c=Collection(store);tool=c.create('tool','Prüfen',value={'prompt':'Nenne offene Punkte'})
            w=EditDialog(c,tool=tool);self.addCleanup(lambda:w.done(0))
            w.source.setText(tmp);w.name.setText('Belege prüfen');w.tabs.setCurrentIndex(1)
            w.clock_kind.setCurrentIndex(w.clock_kind.findData('daily'));w.clock_time.setTime(__import__('PySide6.QtCore',fromlist=['QTime']).QTime(9,15))
            self.assertIn('09:15',w.next_starts.text());w.tabs.setCurrentIndex(0);self.assertEqual(w.source.text(),tmp)
            with patch.object(QDialog,'exec',return_value=QDialog.Accepted):w.review()
            self.assertIsNotNone(w.item);self.assertEqual(store.workflows(),[])
            with patch.object(QDialog,'exec',return_value=QDialog.Accepted),patch('lumen_actions.command'):
                w.activate()
            self.assertTrue(store.workflows()[0]['enabled'])
            w.name.setText('Entwurf bleibt');w.activate();self.assertFalse(store.workflows()[0]['enabled']);self.assertEqual(w.name.text(),'Entwurf bleibt')
            w.discard(confirm=False)
            with patch.object(QDialog,'exec',return_value=QDialog.Accepted),patch('lumen_actions.command'):w.activate()
            w.source.setText(str(Path(tmp)/'missing'))
            with patch.object(QDialog,'exec',return_value=QDialog.Accepted):w.review()
            self.assertTrue(store.workflows()[0]['enabled']);self.assertEqual(w.source.text(),str(Path(tmp)/'missing'))
            w.source.setText(tmp);w.name.setText('Andere Belege')
            with patch.object(QDialog,'exec',return_value=QDialog.Accepted):w.review()
            self.assertFalse(store.workflows()[0]['enabled']);self.assertFalse(store.workflows()[0]['approved'])

    def test_real_test_snapshot_cannot_save_or_run_actions(self):
        from code_edit_window import EditDialog
        from unittest.mock import patch
        from PySide6.QtWidgets import QMessageBox
        from PySide6.QtCore import QObject, Signal
        class Backend(QObject):
            completed=Signal(bool,str)
            def __init__(self,*args,**kwargs):super().__init__();self.busy=False;self.sent=None
            def send(self,*args,**kwargs):self.busy=True;self.sent=(args,kwargs)
            def stop(self):self.busy=False;self.completed.emit(False,'Gestoppt')
            def shutdown(self):self.busy=False;self.closed=True
        with tempfile.TemporaryDirectory() as tmp:
            c=Collection(Store(tmp));item=c.create('tool','Prüfen',value={'prompt':'Frist prüfen'})
            w=EditDialog(c,item);self.addCleanup(lambda:w.done(0));w.rule_controls[0][1].setPlainText('Neue Regel');w.test_input.setPlainText('Rechnung CHF 42')
            with patch('assistant_backend.OpenCodeBackend',Backend),patch('code_edit_window.QMessageBox.question',return_value=QMessageBox.Yes):w.test_tool()
            self.assertTrue(w.engine.sent[1]['proposal']);self.assertIn('Neue Regel',w.engine.sent[0][0]);self.assertEqual(c.get(item['id'])['revision'],1)
            w.name.setText('Anderer Entwurf');w.engine.busy=False;w.engine.completed.emit(True,'Frist fehlt')
            self.assertIn('früheren',w.test_state.text());self.assertFalse(c.store.tasks());self.assertEqual(w.previous.toPlainText(),'Frist fehlt');w.done(0);self.assertTrue(w.engine.closed)
