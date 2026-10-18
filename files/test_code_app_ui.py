import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import test_code_app_preview as preview_tests

SOURCE='<label>Preis <input id="amount" value="1"></label><output id="total"></output><script>oninput=()=>document.querySelector("#total").textContent=Number(document.querySelector("#amount").value)*2;oninput()</script>'


class AppUiTest(preview_tests.PreviewTest):
    # Renderer checks run in their own class; only reuse the Qt/async helpers.
    test_real_html_and_form_input_restore=None
    test_external_navigation_and_browser_apis_are_denied=None
    test_app_resources_cannot_reach_a_local_server_or_files=None
    test_repeatable_examples_observe_real_output_and_skip_password_fields=None

    def test_saved_examples_rerun_and_prepare_a_reviewed_repair(self):
        from code_app_checks_ui import ChecksDialog
        window=self.window();dialog=ChecksDialog(window);self.addCleanup(lambda:dialog.done(0));dialog.show()
        self.js(window.preview,'amount.value="42";amount.dispatchEvent(new Event("input",{bubbles:true}));true')
        dialog.name.setText('42 doppelt');dialog.expect.setText('84');dialog.save();self.wait(lambda:not dialog.pending)
        self.assertEqual(len(dialog.examples['cases']),1);dialog.list.setCurrentRow(0)
        self.js(window.preview,'amount.value="2";amount.dispatchEvent(new Event("input",{bubbles:true}));true')
        dialog.run();self.wait(lambda:not dialog.pending);self.assertEqual(dialog.status.text(),'Erwartung erfüllt',(dialog.output.toPlainText(),dialog.examples))
        dialog.examples['cases'][0]['expect']='999';dialog.run();self.wait(lambda:not dialog.pending)
        self.assertEqual(dialog.status.text(),'Erwarteter Text fehlt');dialog.prepare_repair()
        self.assertIn('999',window.request.toPlainText());self.assertIsNone(window.engine)

    def test_selected_file_and_reviewed_note_use_existing_handoff_with_origin(self):
        from code_app_data_ui import DataDialog
        from wissen_data import activate,Notebook
        from interop_data import Registry
        window=self.window(SOURCE+'<textarea id="document"></textarea>')
        directory=window.collection.store.directory;source=directory/'input.txt';source.write_text('Ausdrücklich gewählte Datei')
        notes=directory/'notes';notes.mkdir();activate(window.collection.store,str(notes))
        dialog=DataDialog(window);self.addCleanup(lambda:dialog.done(0));dialog.show();self.wait(lambda:dialog.target.count()==2)
        dialog.target.setCurrentIndex(1)
        with patch('code_app_data_ui.QFileDialog.getOpenFileName',return_value=(str(source),'')):dialog.read_file()
        self.wait(lambda:dialog.job is None);self.wait(lambda:dialog.status.text().startswith('Übernommene Quelle'))
        self.assertEqual(self.js(window.preview,'document.querySelector("#document").value'),'Ausdrücklich gewählte Datei')
        dialog.prepare();self.wait(lambda:dialog.save_button.isEnabled());dialog.title.setText('Geprüftes Ergebnis');dialog.body.setPlainText('Nur dieser überprüfte Text')
        dialog.save();self.wait(lambda:dialog.job is None)
        self.assertEqual(dialog.status.text(),'Notiz gespeichert.')
        dialog.save();self.wait(lambda:dialog.job is None)
        book=Notebook(window.collection.store);records=book.scan()['notes'];self.assertEqual(len(records),1)
        note=book.read(records[0]['path']);self.assertIn('Nur dieser überprüfte Text',note['text'])
        self.assertEqual(Registry().resolve(note['source'])['app'],'code')

    def window(self,source=SOURCE):
        from code_app_window import AppWindow
        from code_library import Collection
        from lumen_store import Store
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        collection=Collection(Store(Path(tmp.name)));item=collection.create('app','Preisvergleich','Vergleiche deine Angebote.',{'html':source},project_id='retained')
        window=AppWindow(collection,item['id']);self.addCleanup(lambda:window.done(0));window.show();self.wait(lambda:window.preview.ready)
        return window

    def test_saved_draft_inputs_review_discard_and_reopen(self):
        from PySide6.QtWidgets import QDialog
        from code_app_window import AppWindow
        w=self.window();self.assertEqual(w.mode.currentIndex(),0)
        self.assertEqual(w.title.text(),'Preisvergleich')
        self.js(w.preview,'document.querySelector("#amount").value="42";document.querySelector("#amount").dispatchEvent(new Event("input",{bubbles:true}));true')
        w.mode.setCurrentIndex(1);self.assertEqual(w.title.text(),'Preisvergleich');w.request.setPlainText('Zusatztext anzeigen')
        source=SOURCE+'<p id="new">Lieferung einbeziehen</p>'
        w.source.setPlainText(source);w.apply_code();self.wait(lambda:self.js(w.preview,'!!document.querySelector("#new")'))
        self.wait(lambda:self.js(w.preview,'document.querySelector("#total").textContent')=='84')
        self.assertNotIn('new',w.collection.get(w.item['id'])['definition']['html'])
        w.mode.setCurrentIndex(0);self.wait(lambda:not self.js(w.preview,'!!document.querySelector("#new")'))
        self.assertEqual(self.js(w.preview,'document.querySelector("#amount").value'),'42')
        w.mode.setCurrentIndex(1);self.wait(lambda:self.js(w.preview,'!!document.querySelector("#new")'))
        with patch.object(QDialog,'exec',return_value=QDialog.Rejected):w.review()
        self.assertNotIn('new',w.collection.get(w.item['id'])['definition']['html'])
        w.done(0);other=AppWindow(w.collection,w.item['id']);self.addCleanup(lambda:other.done(0));other.show();self.wait(lambda:other.preview.ready)
        self.assertEqual(other.source.toPlainText(),source);self.assertEqual(other.request.toPlainText(),'Zusatztext anzeigen')
        with patch.object(QDialog,'exec',return_value=QDialog.Accepted):other.review()
        self.assertEqual(other.collection.get(w.item['id'])['definition']['html'],source);self.assertEqual(other.item['revision'],2)
        self.assertEqual(other.item['project_id'],'retained');self.assertFalse(other.dirty())
        other.source.setPlainText(source+'<p>Temporary</p>');other.apply_code();other.discard(confirm=False)
        self.assertEqual(other.source.toPlainText(),source);self.assertFalse(other.dirty())

    def test_empty_app_close_draft_and_reset_inputs(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from code_app_window import AppWindow
        w=self.window('');self.assertEqual(w.mode.currentIndex(),1)
        w.request.setPlainText('Meine erste App');w.source.setPlainText(SOURCE);w.apply_code();self.wait(lambda:self.js(w.preview,'!!document.querySelector("#amount")'))
        self.js(w.preview,'document.querySelector("#amount").value="123";true')
        w.reset_inputs();self.wait(lambda:w.preview.ready);self.assertEqual(self.js(w.preview,'document.querySelector("#amount").value'),'1')
        w.request.setPlainText('Unfertig');QTest.keyClick(w,Qt.Key_Escape);self.assertTrue(w.closed)
        d=AppWindow(w.collection,w.item['id']);self.addCleanup(lambda:d.done(0));self.assertEqual(d.request.toPlainText(),'Unfertig');self.assertEqual(d.source.toPlainText(),SOURCE)

    def test_preview_controls_fit_desktop_and_compact_editor_scrolls(self):
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QFrame,QPushButton
        w=self.window();w.mode.setCurrentIndex(1);w.resize(1240,850);QTest.qWait(40)
        self.assertIsNone(w.findChild(QFrame,'codeRail'))
        for control in w.findChildren(QPushButton):
            if control.text() in ('Eingaben prüfen','Ergebnis klarer','Schmale Fenster'):
                self.assertGreaterEqual(control.font().pixelSize(),14)
        self.assertEqual(w.body_area.verticalScrollBar().maximum(),0)
        self.assertTrue(w.rect().contains(w.preview_panel.mapTo(w,w.preview_panel.rect().bottomRight())))
        w.resize(820,850);QTest.qWait(40)
        self.assertGreater(w.body_area.verticalScrollBar().maximum(),0)
        self.assertEqual(w.editor.verticalScrollBar().maximum(),0)
        w.body_area.verticalScrollBar().setValue(w.body_area.verticalScrollBar().maximum());QTest.qWait(30)
        self.assertTrue(w.rect().contains(w.preview_panel.mapTo(w,w.preview_panel.rect().bottomRight())))

    def test_real_generation_contract_failure_cancel_and_conflict(self):
        from PySide6.QtCore import QObject,Signal
        from PySide6.QtWidgets import QDialog
        class Engine(QObject):
            completed=Signal(bool,str)
            busy=False
            def __init__(self,*args,**kw):super().__init__();self.kw=kw
            def send(self,prompt,**kw):self.busy=True;self.prompt=prompt;self.sent=kw
            def stop(self):self.busy=False;self.completed.emit(False,'Abgebrochen')
            def shutdown(self):self.busy=False
        w=self.window();w.mode.setCurrentIndex(1);w.request.setPlainText('Füge eine Überschrift hinzu')
        self.js(w.preview,'document.querySelector("#amount").value="private-user-value";true')
        with patch('assistant_backend.OpenCodeBackend',Engine):w.generate()
        self.assertTrue(w.engine.sent['proposal']);self.assertFalse(w.engine.kw['project_config'])
        self.assertNotIn('private-user-value',w.engine.prompt);self.assertFalse(w.review_button.isEnabled())
        w.engine.busy=False;w.engine.completed.emit(True,'bad JSON');self.assertEqual(w.source.toPlainText(),SOURCE)
        w.generate();w.stop();self.assertEqual(w.source.toPlainText(),SOURCE);self.assertTrue(w.generate_button.isEnabled())
        w.generate();w.engine.busy=False;w.engine.completed.emit(True,json.dumps(dict(html=SOURCE+'<h1>Hallo</h1>',changes=['Überschrift ergänzt'])))
        self.assertTrue(w.dirty());self.assertEqual(w.item['revision'],1)
        w.collection.update(w.item['id'],1,title='Inzwischen geändert')
        with patch.object(QDialog,'exec',return_value=QDialog.Accepted):w.review()
        self.assertTrue(w.dirty());self.assertIn('inzwischen',w.error.text())
        w.reload_saved()
        with patch.object(QDialog,'exec',return_value=QDialog.Accepted):w.review()
        self.assertEqual(w.item['revision'],3);self.assertIn('Hallo',w.item['definition']['html'])

    def test_collection_opens_native_app_editor(self):
        from code_library_window import CollectionWindow
        from code_app_window import AppWindow
        from PySide6.QtWidgets import QDialog
        w=self.window();collection_window=CollectionWindow(w.collection.store);self.addCleanup(collection_window.close)
        seen=[]
        def opened(dialog):
            self.assertIsInstance(dialog,AppWindow);seen.append(dialog.item['id']);dialog.done(0);return QDialog.Rejected
        with patch.object(AppWindow,'exec',opened):collection_window.open_entry(w.item['id'])
        self.assertEqual(seen,[w.item['id']])
