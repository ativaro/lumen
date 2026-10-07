import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QLockFile
from vault_activation import activate_backup, activate_existing_backup


class VaultActivationTest(unittest.TestCase):
    def test_invalid_pid_never_requests_focus(self):
        for value in (None, '', '123', -1, 0, True):
            self.assertFalse(activate_backup(value))

    def test_existing_backup_targets_lock_owner(self):
        with tempfile.TemporaryDirectory() as root:
            lock=QLockFile(str(Path(root)/'window.lock'))
            self.assertTrue(lock.tryLock(0))
            try:
                with patch('vault_activation.activate_backup', return_value=True) as activate:
                    self.assertTrue(activate_existing_backup(root))
                    activate.assert_called_once_with(os.getpid())
            finally:
                lock.unlock()


def verify_private_kde():
    if os.environ.get('LUMEN_PRIVATE_KDE_TEST') != '1':
        raise RuntimeError('This focus test requires an isolated KDE session.')
    from PySide6.QtWidgets import QApplication, QMainWindow
    from PySide6.QtTest import QTest
    app=QApplication(['lumen-vault'])
    app.setApplicationName('lumen-vault')
    app.setDesktopFileName('lumen-vault')
    window=QMainWindow()
    window.setWindowTitle('Synthetic backup activation test')
    window.show()
    QTest.qWait(100)
    window.showMinimized()
    QTest.qWait(100)
    assert window.isMinimized()
    assert activate_backup(os.getpid())
    QTest.qWait(100)
    assert not window.isMinimized()
    assert window.isActiveWindow()
    window.close()
    print('VAULT_FOCUS_OK')


if __name__ == '__main__':
    if sys.argv[1:] == ['--kde']:
        verify_private_kde()
    else:
        unittest.main()
