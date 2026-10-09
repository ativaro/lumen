import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lumen_memory import Memory
from lumen_store import Store
from lumen_i18n import tr


class MemorySyncUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or create_app()

    def wait(self,window):
        from PySide6.QtTest import QTest
        for _ in range(400):
            QTest.qWait(20)
            if not window.job and not window.poller:return
        self.fail(window.status.text())

    def test_settings_and_conflict_buttons_use_revision_bound_choices(self):
        from PySide6.QtWidgets import QDialogButtonBox,QPushButton,QPlainTextEdit
        from PySide6.QtCore import QCoreApplication,QEvent
        from PySide6.QtTest import QTest
        from tools_wissen import Wissen
        from wissen_data import activate
        import memory_sync_ui as ui
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'LUMEN_DATA':temp+'/state'}):
            store=Store();activate(store);memory=Memory(store)
            note=memory.remember('Antwortstil','Kurze Antworten.',kind='preference')
            window=Wissen(Path(temp)/'tools');window.show();self.wait(window)
            calls=[]
            preview=dict(id=note['id'],local=note,remote=dict(revision=8,title='Antwortstil',body='Ausführliche Antworten.'))
            def worker(job,store,action,**values):
                calls.append((action,values))
                if action=='conflicts':return preview
                if action=='synchronize':return dict(changed=1,conflicts=0)
                return dict(enabled=True,pending=True)
            try:
                window.switch_area('lumen');self.wait(window)
                with patch.object(ui.sync,'worker',side_effect=worker):
                    ui.show(window,dict(server='https://lumen.example.test',user='Testkonto',enabled=True,allowed=True,
                        reachable=True,conflicts=1,connection='synthetic-binding'))
                    QTest.qWait(50)
                    dialog=window.memory_sync_dialog
                    self.assertTrue(dialog.isVisible())
                    review=next(b for b in dialog.findChildren(QPushButton) if b.text()==tr('Erinnerungen auf dem Server prüfen'))
                    with patch('PySide6.QtGui.QDesktopServices.openUrl') as open_url:
                        review.click()
                        self.assertEqual(open_url.call_args.args[0].toString(),'https://lumen.example.test/?app=note&memory=1')
                    dialog.grab().save('/tmp/lumen-memory-sync-settings.png')
                    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click();self.wait(window)
                    self.assertIn(('configure',dict(enabled=True,expected='synthetic-binding')),calls)
                    self.assertTrue(any(action=='synchronize' for action,_ in calls))
                    ui.conflict_dialog(window,[dict(id=note['id'],title=note['title'])]);self.wait(window)
                    dialog=window.memory_conflict_dialog
                    texts=[editor.toPlainText() for editor in dialog.findChildren(QPlainTextEdit)]
                    self.assertIn('Kurze Antworten.',texts[0]);self.assertIn('Ausführliche Antworten.',texts[1])
                    dialog.grab().save('/tmp/lumen-memory-sync-conflict.png')
                    button=next(b for b in dialog.findChildren(QPushButton) if b.text()==tr('Serverfassung übernehmen'))
                    self.assertTrue(button.isEnabled());button.click();self.wait(window)
                    self.assertIn(('resolve',dict(identity=note['id'],use_server=True,expected_revision=8,expected_hash=note['hash'])),calls)
            finally:
                window.close();window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_imported_memory_requires_native_checkbox_approval(self):
        from PySide6.QtCore import QCoreApplication,QEvent
        from tools_wissen import Wissen
        from wissen_data import activate
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'LUMEN_DATA':temp+'/state'}):
            store=Store();activate(store);memory=Memory(store);memory.configure(True,False)
            note=memory.remember('Imported','Synthetic memory',kind='preference')
            memory.allow(note['path'],note['hash'],False)
            window=Wissen(Path(temp)/'tools');window.show();self.wait(window)
            try:
                window.switch_area('lumen');self.wait(window);window.open_profile_note(note['path']);self.wait(window)
                self.assertTrue(window.share_note.isVisible());self.assertFalse(window.share_note.isChecked())
                self.assertEqual(memory.eligible(temp),[])
                window.share_note.setChecked(True);self.wait(window)
                self.assertEqual(len(memory.eligible(temp)),1)
                window.share_note.setChecked(False);self.wait(window)
                self.assertEqual(memory.eligible(temp),[])
            finally:
                window.close();window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


if __name__=='__main__':unittest.main()
