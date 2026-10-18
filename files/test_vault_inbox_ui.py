import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QDialog,QComboBox,QLineEdit,QPlainTextEdit,QMessageBox
from tools_inbox import Inbox
from tools_vault import Vault


class NativeToolsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_vault_sections_fit_large_fonts_and_switch_backup_views(self):
        from PySide6.QtTest import QTest
        from PySide6.QtGui import QFont
        from PySide6.QtCore import QProcess
        from appearance import apply_design
        for theme in ('glass', 'graphite', 'atelier', 'midnight'):
            apply_design(self.app, theme)
            with tempfile.TemporaryDirectory() as tmp:
                vault=Vault(tmp)
                vault.show()
                for size in (12, 20, 24):
                    for tab in (vault.vault_tab, vault.backups_tab):
                        tab.setFont(QFont('Noto Sans', size))
                    QTest.qWait(25)
                    for tab in (vault.vault_tab, vault.backups_tab):
                        self.assertGreaterEqual(tab.width(), tab.fontMetrics().horizontalAdvance(tab.text()) + 40)
                        self.assertGreaterEqual(tab.height(), tab.fontMetrics().tightBoundingRect(tab.text()).height() + 18)
                self.assertEqual(vault.backup_stack.currentIndex(), 0)
                with patch.object(QProcess, 'startDetached', return_value=(True, 123)) as launch:
                    vault.vault_tab.click()
                    launch.assert_called_once()
                self.assertTrue(vault.backups_tab.isChecked())
                plan=vault.library.create('Layout backup', repository='/media/example', sources=['/home/example/Documents'], interval=0)
                vault.focus_record(plan)
                self.assertEqual(vault.backup_stack.currentIndex(), 1)
                self.assertTrue(vault.body.isEnabled())
                with patch('tools_vault.QMessageBox.question',return_value=QMessageBox.Yes), patch('vault_data.schedule'):
                    vault.archive()
                    for _ in range(250):
                        if not vault.job: break
                        QTest.qWait(10)
                    self.assertIsNone(vault.job)
                self.assertEqual(vault.backup_stack.currentIndex(), 0)
                vault.close()

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
