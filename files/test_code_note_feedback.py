"""Saved errors and Notes guidance over real private automation checkpoints."""
import json
from pathlib import Path
import tempfile
import unittest
from PySide6.QtCore import QCoreApplication,QEvent,Qt
from PySide6.QtWidgets import QApplication,QLabel,QPlainTextEdit
from code_blocks import node,encode
from code_blocks_run import Runs
from code_blocks_window import BlockWindow
from code_library import Collection
from lumen_i18n import tr
from lumen_jobs import Job
from lumen_store import Store


class NoteFeedbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.app=QApplication.instance() or create_app()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.collection=Collection(Store(Path(self.tmp.name)/'state'));self.runs=Runs(self.collection)
        plan=dict(version=3,nodes=[node('manual',json.dumps({'kind':'text','text':''})),node('save_note','Prüfnotiz'),node('delay','0')])
        self.entry=self.collection.create('automation','Notes-Prüfung',value={'flow':encode(plan)})
        self.job=Job(lambda _:None)

    def drain(self):
        run=self.runs.create(self.entry['id'],True);self.runs.resume(run['id'])
        for _ in range(5):
            self.runs.advance(run['id'],self.job);run=self.runs.get(run['id'])
            if run['status']!='running':return run
        self.fail('Run did not finish')

    def window(self):
        window=BlockWindow(self.collection,self.entry['id'])
        self.addCleanup(self.dispose,window);return window

    @staticmethod
    def dispose(window):
        if window.editor.dialog is not None:window.editor.dialog.reject()
        window.reject();window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_saved_reason_survives_other_selection_and_clears_after_success(self):
        failed=self.drain();self.assertEqual(failed['status'],'error')
        reason=tr(failed['data']['steps'][1]['error']);window=self.window()
        self.assertIn(reason,window.status.text())
        for key in ('input',window.editor.items[2]['id']):
            window.editor.select_entry(key);window.editor.dialog.reject();window.render()
            self.assertIn(reason,window.status.text());self.assertIn(reason,window.result_view.toPlainText())
        window.editor.select_entry('input')
        edit=next(w for w in window.editor.dialog.findChildren(QPlainTextEdit) if w.accessibleName()==tr('Eingabetext'))
        edit.setPlainText('Synthetischer Inhalt');window.editor.dialog_apply.click();window.save()
        window.run=self.drain();window.render()
        self.assertEqual(window.run['status'],'completed');self.assertNotIn(reason,window.status.text())
        self.assertNotIn(reason,window.result_view.toPlainText())

    def test_saved_error_is_plain_text_and_full_reason_stays_in_result(self):
        run=self.runs.create(self.entry['id'],True);self.runs.resume(run['id']);self.runs.advance(run['id'],self.job)
        reason='<b>Quelldatei & Titel</b>\n'+('Langer Dateiname ' * 80)
        self.runs.fail(run['id'],reason);window=self.window()
        self.assertEqual(window.status.textFormat(),Qt.PlainText)
        self.assertIn('<b>Quelldatei & Titel</b>',window.status.text())
        self.assertLess(len(window.status.text()),500)
        self.assertIn(reason,window.result_view.toPlainText())

    def test_notes_detail_explains_title_content_and_test_mode_without_changing_plan(self):
        window=self.window();before=window.editor.plan()
        window.editor.select_entry(window.editor.items[1]['id'])
        text='\n'.join(w.text() for w in window.editor.dialog.findChildren(QLabel))
        self.assertIn(tr('Der Inhalt kommt aus der Eingabe beim Start oder aus dem Ergebnis des vorherigen Schritts. Hier legst du nur den Titel fest.'),text)
        self.assertIn(tr('Für festen Text: „Auf Knopfdruck“ öffnen, „Text eingeben“ wählen und den Inhalt eintragen.'),text)
        self.assertIn(tr('Auf Knopfdruck'),text)
        self.assertIn(tr('Ein Testlauf legt keine Notiz an. „Jetzt ausführen“ speichert sie in Lumen Notes.'),text)
        window.editor.dialog.reject();self.assertEqual(before,window.editor.plan())

    def test_manual_start_hint_is_not_offered_for_clock_or_legacy_sources(self):
        from code_clock import default
        window=self.window();clock=window.editor.plan()
        clock['nodes'][0]['config']=json.dumps({'kind':'text','text':'','trigger':{'kind':'clock','clock':default()}})
        legacy=dict(version=2,nodes=[node('manual'),node('save_note')])
        for plan in (clock,legacy):
            with self.subTest(version=plan['version']):
                window.editor.set_plan(plan);window.editor.select_entry(window.editor.items[1]['id'])
                text='\n'.join(w.text() for w in window.editor.dialog.findChildren(QLabel))
                self.assertNotIn(tr('Für festen Text: „Auf Knopfdruck“ öffnen, „Text eingeben“ wählen und den Inhalt eintragen.'),text)
                window.editor.dialog.reject()


if __name__=='__main__':unittest.main()
