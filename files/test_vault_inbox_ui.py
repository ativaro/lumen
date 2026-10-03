import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QDialog,QComboBox,QLineEdit,QPlainTextEdit
from tools_inbox import Inbox
from tools_vault import Vault


class NativeToolsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_native_account_modes_draft_persistence_and_vault_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            window=Inbox(tmp);failures=[]
            def inspect():
                try:
                    dialog=next(w for w in QApplication.topLevelWidgets() if isinstance(w,QDialog) and w.isVisible())
                    kind=dialog.findChildren(QComboBox)[0]
                    for i in range(4):kind.setCurrentIndex(i);self.app.processEvents()
                    self.assertEqual(kind.currentData(),'ics');dialog.reject()
                except Exception as error:failures.append(error);QApplication.activeModalWidget().reject()
            QTimer.singleShot(0,inspect);window.account_dialog();self.assertFalse(failures,failures)
            key=window.library.create('Test',kind='imap');window.focus_record(key)
            def write():
                dialog=QApplication.activeModalWidget();fields=dialog.findChildren(QLineEdit)
                fields[0].setText('recipient@example.invalid');fields[1].setText('Saved draft');dialog.findChild(QPlainTextEdit).setPlainText('Private local draft');dialog.reject()
            QTimer.singleShot(0,write)
            with patch('inbox_data.send_draft') as send:window.compose(account=window.library.get(key));send.assert_not_called()
            with window.library.connect() as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM drafts WHERE status='draft'").fetchone()[0],1)
            window.close();again=Inbox(tmp);self.assertEqual(again.drafts.topLevelItemCount(),1);again.close()
            vault=Vault(tmp);plan=vault.library.create('Test backup',repository='/media/backup',sources=['/home/demo/Documents'],interval=0)
            vault.focus_record(plan);self.assertEqual(vault.sources.count(),1);self.assertTrue(vault.body.isEnabled());vault.close()


if __name__=='__main__':unittest.main()
