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
