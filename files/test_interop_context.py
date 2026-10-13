"""Exercise contextual entry points, native review and durable backup setup."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QTimer,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication,QComboBox,QDialog,QLabel,QLineEdit,QMenu,QPlainTextEdit
from interop_data import Registry
import interop_ui
import interop_vault


class ContextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'LUMEN_DATA':str(self.root/'state'),'LUMEN_TOOLS_DATA':str(self.root/'tools'),
                                       'XDG_CONFIG_HOME':str(self.root/'config')})
        self.env.start();self.addCleanup(self.env.stop);self.windows=[];self.addCleanup(self.close)

    def close(self):
        for window in self.windows:
            if window.job:window.job.cancelled.set();window.job.wait(5000)
            self.app.processEvents();window.close();window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def wait(self,predicate):
        until=time.monotonic()+8
        while time.monotonic()<until:
            self.app.processEvents()
            if predicate():return
            time.sleep(.01)
        self.fail('Native operation did not finish')

    def test_context_actions_replace_top_chrome_and_keep_real_item_drag(self):
        from tools_workbench import Workbench
        from interop_context import add_actions
        window=Workbench(self.root/'tools');self.windows.append(window)
        window.focus_record(window.library.create('Project',notes='Text',questions=[],resources=[]))
        self.app.processEvents()
        self.assertFalse(window.menuBar().actions());self.assertIsNone(window.menuBar().cornerWidget())
        self.assertTrue(window.entries.dragEnabled())
        menu=QMenu();add_actions(window,menu)
        self.assertIn(interop_ui.tr('Als Notiz speichern …'),[a.text() for a in menu.actions()])
        self.assertIn(window._workflow_menu.menuAction(),menu.actions())

    def test_context_menu_waits_for_selected_content_to_load(self):
        from tools_workbench import Workbench
        window=Workbench(self.root/'tools');self.windows.append(window);window.show()
        window.focus_record(window.library.create('Project',notes='Text',questions=[],resources=[]))
        self.app.processEvents();window.work('Loading',lambda job:time.sleep(.1),lambda _:None)
        observed=[];timer=QTimer();timer.setInterval(15)
        def inspect():
            menu=QApplication.activePopupWidget()
            if isinstance(menu,QMenu):
                names=[a.text() for a in menu.actions()]
                observed.extend(names)
                if interop_ui.tr('Als Notiz speichern …') in names:menu.close()
        timer.timeout.connect(inspect);timer.start()
        # A bounded fallback ensures a failed population cannot hang the suite.
        watchdog=QTimer();watchdog.setSingleShot(True);watchdog.timeout.connect(lambda:QApplication.activePopupWidget().close() if QApplication.activePopupWidget() else None);watchdog.start(2000)
        try:window.entries.customContextMenuRequested.emit(window.entries.visualItemRect(window.entries.currentItem()).center())
        finally:timer.stop();watchdog.stop()
        self.assertIn(interop_ui.tr('Auswahl wird geladen …'),observed)
        self.assertIn(interop_ui.tr('Als Notiz speichern …'),observed)

    def test_dropped_reader_files_are_queued_without_an_import_chooser(self):
        from types import SimpleNamespace
        from interop_context import receive_drop
        paths=[]
        for name in ('one.txt','two.txt'):
            path=self.root/name;path.write_text(name);paths.append(str(path))
        with patch('interop_ui.controller') as control,patch('interop_ui.reviewed_send') as review:
            receive_drop(SimpleNamespace(name='reader'),dict(paths=paths))
        self.assertEqual([c.args[0] for c in control.return_value.enqueue.call_args_list],[{'path':p} for p in paths])
        review.assert_not_called()

    def test_reader_quote_native_review_saves_named_exact_source(self):
        from tools_reader import Reader
        from tools_wissen import Wissen
        source=Reader(self.root/'tools');target=Wissen(self.root/'tools');self.windows.extend([source,target])
        errors=[];source.error=errors.append;target.error=errors.append
        document=self.root/'Thoughts.txt';document.write_text('A selected passage with its exact source.')
        source.open_file(str(document))
        self.wait(lambda:source.data and not source.job and target.book and not target.job)
        source.canvas.select_all()
        with patch('interop_ui.launch') as launch:source.remember()
        token=launch.call_args.args[1][1];registry=Registry(self.root/'tools');request=registry.request(token)
        self.assertEqual(request['payload']['source']['position']['page'],0)
        inspected=[]
        def accept():
            dialog=QApplication.activeModalWidget()
            if not dialog:return
            visible=[w for w in dialog.findChildren(QComboBox) if w.isVisible()]
            inspected.append([w.text() for w in dialog.findChildren(QLabel) if w.isVisible()])
            self.assertEqual(len(visible),1) # notebook folder only
            edits=[w for w in dialog.findChildren(QLineEdit) if w.isVisible()]
            self.assertEqual(len(edits),1) # title; no unrelated date
            edits[0].setText('My saved thought')
            self.assertIn('exact source',dialog.findChild(QPlainTextEdit).toPlainText())
            dialog.accept()
        timer=QTimer();timer.setInterval(20);timer.timeout.connect(accept);timer.start()
        try:
            interop_ui.controller(target).enqueue({'handoff':token})
            self.wait(lambda:registry.request(token)['state']=='done' and not target.job)
        finally:timer.stop()
        self.assertFalse(errors,errors);self.assertTrue(inspected)
        note=target.book.scan()['notes'][0]
        self.assertEqual(note['title'],'My saved thought');self.assertIn('exact source',note['text'])
        self.assertNotIn('lumen://',target.editor.toPlainText());self.assertIn('Thoughts',target.origin.text())
        self.assertEqual(note['source'],request['payload']['source_url'])
        with patch('interop_open.launch') as opened:target.origin.linkActivated.emit(note['source'])
        self.assertEqual(opened.call_args.args[:2],('reader',['--ref',note['source']]))
        result=registry.request(token)['result'];self.assertEqual(registry.related(result)[0]['position']['page'],0)
        markup=interop_ui.source_markup(request['payload']['source_url'],self.root/'tools')
        self.assertIn('Thoughts',markup);self.assertIn(interop_ui.tr(' · Seite {0}',1),markup)

    def test_notebook_backup_saves_edits_and_selects_only_notebook_and_links(self):
        from tools_wissen import Wissen
        window=Wissen(self.root/'tools');self.windows.append(window);errors=[];window.error=errors.append
        self.wait(lambda:window.book and not window.job)
        note=window.book.create('Keep','Original');window.scanned(window.book.scan());window.open_note(note['path'])
        self.wait(lambda:window.doc and not window.job)
        window.editor.appendPlainText('Unsaved edit')
        with patch('interop_ui.launch') as launch:
            window.backup_notebook();self.wait(lambda:launch.called and not window.job)
        self.assertIn('Unsaved edit',window.book.read(note['path'])['text'])
        request=Registry(self.root/'tools').request(launch.call_args.args[1][1])
        rows=interop_vault.payload_sources(request['payload'],self.root/'tools',window.store)
        self.assertEqual([r['kind'] for r in rows if r['app']=='wissen'],['notebook'])
        window.backup_status();self.assertEqual(window.backup_info.text(),interop_ui.tr('Noch kein Sicherungsplan für dieses Notizbuch.'))
        from tools_data import Library
        library=Library('vault',self.root/'tools');key=library.create('Notes',sources=[str(window.book.root)],interval=86400)
        window.backup_status();self.assertIn(interop_ui.tr('Täglich'),window.backup_info.text())
        self.assertIn(interop_ui.tr('Noch kein erfolgreicher Sicherungslauf.'),window.backup_info.text())
        library.update(key,last_backup=1700000000,backup_sources=[str(window.book.root)])
        window.backup_status();self.assertIn('14.11.2023',window.backup_info.text());self.assertFalse(errors,errors)

    def test_failed_schedule_resumes_existing_plan_without_second_review(self):
        from tools_vault import Vault
        from tools_ui import Job
        window=Vault(self.root/'tools');self.windows.append(window);errors=[];window.error=errors.append
        repository=self.root/'backup';repository.mkdir();source=self.root/'note.md';source.write_text('Keep')
        key=window.library.create('Notes',repository=str(repository),sources=[]);window.focus_record(key)
        payload=dict(source=dict(app='files',path=str(source)),paths=[str(source)])
        def accept():
            dialog=QApplication.activeModalWidget()
            next(w for w in dialog.findChildren(QComboBox) if w.accessibleName()==interop_ui.tr('Sicherungsrhythmus')).setCurrentIndex(1)
            dialog.accept()
        completed=[];QTimer.singleShot(0,accept)
        with patch('vault_data.schedule',side_effect=ValueError('Timer unavailable')):
            self.assertTrue(interop_vault.receive_sources(window,payload,token='c'*32,done=completed.append))
            self.wait(lambda:not window.job)
        self.assertEqual(completed,[None]);self.assertEqual(window.library.get(key)['schedule_pending'],86400)
        self.assertEqual(window.library.get(key).get('last_backup'),None)
        with patch.object(QDialog,'exec',side_effect=AssertionError('Already reviewed')),patch.object(Job,'command',return_value=b''):
            self.assertTrue(interop_vault.receive_sources(window,payload,token='c'*32,done=completed.append))
            self.wait(lambda:not window.job)
        self.assertEqual(completed[-1]['id'],key);self.assertEqual(len(window.library.all()),1)
        self.assertEqual(window.library.get(key)['interval'],86400);self.assertIsNone(window.library.get(key)['schedule_pending'])
        self.assertEqual(errors,['Timer unavailable'])

    def test_prefilled_backup_setup_keeps_schedule_separate_from_backup(self):
        from tools_vault import Vault
        from tools_ui import Job
        window=Vault(self.root/'tools');self.windows.append(window);errors=[];window.error=errors.append
        source=self.root/'notebook';source.mkdir();repository=self.root/'backup';repository.mkdir()
        def accept():
            dialog=QApplication.activeModalWidget();edits=dialog.findChildren(QLineEdit)
            for field,value in zip(edits,['My notes',str(repository),str(source),'synthetic-secret-only','synthetic-secret-only']):field.setText(value)
            dialog.findChild(QComboBox).setCurrentIndex(2)
            dialog.accept()
        completed=[];QTimer.singleShot(0,accept)
        with patch('vault_data.binary',return_value='/synthetic/restic'),patch('vault_data.command',return_value='{"id":"synthetic"}'),patch('vault_data.secret'),patch.object(Job,'command',return_value=b''):
            self.assertTrue(window.create(prefill_sources=[dict(path=str(source))],on_done=completed.append));self.wait(lambda:not window.job)
        self.assertFalse(errors,errors);self.assertEqual(len(completed),1)
        plan=window.library.get(completed[0]);self.assertEqual(plan['interval'],604800)
        self.assertFalse(plan.get('last_backup'));self.assertIsNone(plan['schedule_pending'])


if __name__=='__main__':unittest.main()
