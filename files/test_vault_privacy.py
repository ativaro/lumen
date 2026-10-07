"""Privacy boundaries use only isolated runtime directories and synthetic MIME."""
import fcntl
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from vault_privacy import acquire_capture, capture_guard

class PrivacyLeaseTest(unittest.TestCase):
    def test_shared_vault_lease_blocks_capture_and_releases_after_close(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, XDG_RUNTIME_DIR=root):
            path=Path(root)/'lumen-vault-privacy.lock'
            fd=os.open(path,os.O_CREAT|os.O_RDWR,0o600)
            try:
                fcntl.flock(fd,fcntl.LOCK_SH)
                with self.assertRaises(BlockingIOError): acquire_capture()
            finally: os.close(fd)
            with capture_guard():
                fd=os.open(path,os.O_RDWR)
                try:
                    with self.assertRaises(BlockingIOError):fcntl.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
                finally:os.close(fd)
            with capture_guard():pass

    def test_missing_relative_and_symlink_runtime_fail_closed(self):
        for value in ['', 'relative/path']:
            with patch.dict(os.environ,XDG_RUNTIME_DIR=value),self.assertRaises(OSError):acquire_capture()
        with tempfile.TemporaryDirectory() as root:
            link=Path(root)/'link';link.symlink_to(root,target_is_directory=True)
            with patch.dict(os.environ,XDG_RUNTIME_DIR=str(link)),self.assertRaises(OSError):acquire_capture()

    def test_ai_editor_refuses_protected_paste(self):
        from PySide6.QtCore import QMimeData
        from PySide6.QtWidgets import QApplication
        from private_input import AssistantInput
        app=QApplication.instance() or QApplication([])
        editor=AssistantInput();mime=QMimeData();mime.setText('SYNTHETIC SECRET');mime.setData('x-kde-passwordManagerHint',b'secret')
        editor.insertFromMimeData(mime);self.assertEqual(editor.toPlainText(),'')
        public=QMimeData();public.setText('public note');editor.insertFromMimeData(public);self.assertEqual(editor.toPlainText(),'public note')
        editor.close()
