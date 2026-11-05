import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import server_app_downloads as downloads


class Signal:
    def connect(self,callback):self.callback=callback


class Request:
    def __init__(self,page):
        self._page=page;self.cancelled=False;self.accepted=False
        self.receivedBytesChanged=Signal();self.stateChanged=Signal()
    def url(self):return SimpleNamespace(toString=lambda:'https://staging.invalid/api/inbox/drafts/file/attachments/part')
    def page(self):return self._page
    def totalBytes(self):return 80*1024**2
    def receivedBytes(self):return 0
    def suggestedFileName(self):return 'Attachment.bin'
    def setDownloadDirectory(self,value):self.directory=value
    def setDownloadFileName(self,value):self.name=value
    def accept(self):self.accepted=True
    def cancel(self):self.cancelled=True


class InboxDownloadTest(unittest.TestCase):
    def test_disappearing_save_volume_cancels_before_accepting_download(self):
        with tempfile.TemporaryDirectory() as root:
            page=object()
            window=SimpleNamespace(_binding=SimpleNamespace(app='inbox',origin='https://staging.invalid',resource=lambda value:True),page=page,_temporary=SimpleNamespace(name=root),_app_title='Lumen Inbox')
            request=Request(page)
            with patch.object(downloads,'context',return_value='proof'),patch.object(downloads,'current',return_value=True),patch.object(downloads,'fresh',return_value=True),patch.object(downloads.QFileDialog,'getSaveFileName',return_value=(str(Path(root)/'saved.bin'),'')),patch.object(downloads.shutil,'disk_usage',side_effect=OSError('Synthetic volume unmounted')),patch.object(downloads.QMessageBox,'warning') as warning:
                downloads.download(window,request)
            self.assertTrue(request.cancelled)
            self.assertFalse(request.accepted)
            warning.assert_called_once()

    def test_inbox_stream_has_no_mail_size_ceiling_but_stops_at_storage_reserve(self):
        with tempfile.TemporaryDirectory() as root:
            page=object()
            window=SimpleNamespace(_binding=SimpleNamespace(app='inbox',origin='https://staging.invalid',resource=lambda value:True),page=page,_temporary=SimpleNamespace(name=root),_app_title='Lumen Inbox')
            request=Request(page)
            with patch.object(downloads,'context',return_value='proof'),patch.object(downloads,'current',return_value=True),patch.object(downloads,'fresh',return_value=True),patch.object(downloads.QFileDialog,'getSaveFileName',return_value=(str(Path(root)/'saved.bin'),'')),patch.object(downloads.shutil,'disk_usage',return_value=SimpleNamespace(free=2*1024**3)):
                downloads.download(window,request)
            self.assertTrue(request.accepted)
            self.assertFalse(request.cancelled)
            with patch.object(downloads.shutil,'disk_usage',return_value=SimpleNamespace(free=1024)):
                request.receivedBytesChanged.callback()
            self.assertTrue(request.cancelled)
            window._binding.app='vault'
            vault=Request(page)
            with patch.object(downloads,'context',return_value='proof'),patch.object(downloads,'current',return_value=True):
                downloads.download(window,vault)
            self.assertTrue(vault.cancelled)
            self.assertFalse(vault.accepted)


if __name__=='__main__':unittest.main()
