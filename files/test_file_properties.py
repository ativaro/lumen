"""Properties edits use temporary files only; no user paths or credentials."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QSettings, QCoreApplication, QEvent
from PySide6.QtTest import QTest
from app import Window, create_app
from file_properties import Properties
from shiboken6 import isValid
from lumen_jobs import Job
import file_properties_data as data


class PropertiesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=create_app()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        env=patch.dict(os.environ,LUMEN_DATA=str(self.root/'state'),LUMEN_TOOLS_DATA=str(self.root/'tools'));env.start();self.addCleanup(env.stop)
        self.file=self.root/'note.txt';self.file.write_text('hello');self.file.chmod(0o640)
        self.job=Job(lambda job:None)
        self.w=Window(str(self.root),QSettings(str(self.root/'settings'),QSettings.IniFormat));self.addCleanup(self.w.close)

    def row(self,path=None):return data.inspect([str(path or self.file)],self.job)['rows'][0]

    def wait(self,predicate):
        for _ in range(600):
            QTest.qWait(10)
            if predicate():return
        self.fail('Properties job did not finish')

    def dialog(self,path=None):
        d=Properties(self.w,[str(path or self.file)]);d.show();self.addCleanup(lambda:d.reject() if isValid(d) else None)
        self.wait(lambda:d.fact is not None and d.job is None)
        return d

    def test_totals_do_not_follow_links_and_hash_rejects_special_files(self):
        folder=self.root/'folder';folder.mkdir();(folder/'a').write_bytes(b'abc');(folder/'loop').symlink_to(folder)
        totals=data.folder_totals([str(folder),str(folder/'a')],self.job)
        self.assertEqual(totals['files'],2);self.assertEqual(totals['folders'],0)
        self.assertEqual(totals['size'],3+(folder/'loop').lstat().st_size)
        self.assertEqual(data.checksum(self.row(),self.job),'2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824')
        with self.assertRaises(OSError):data.checksum(self.row(folder/'loop'),self.job)
        fifo=self.root/'fifo';os.mkfifo(fifo)
        with self.assertRaises(ValueError):data.checksum(self.row(fifo),self.job)

    def test_permissions_and_rename_require_apply_and_keep_mode_bits(self):
        d=self.dialog();d.name.setText('changed.txt');d.toggle()
        self.assertTrue(self.file.exists());self.assertEqual(d.name.text(),'changed.txt')
        # Wait for optional expanded overview calculation, then apply an explicit edit.
        self.wait(lambda:d.job is None)
        d.save();self.wait(lambda:d.job is None and d.paths==[str(self.root/'changed.txt')])
        self.assertFalse(self.file.exists());self.assertEqual((self.root/'changed.txt').read_text(),'hello')
        self.assertEqual(d.fact['rows'][0]['name'],'changed.txt')
        owner_write=next(check for check,bit in d.bits if bit==0o200);owner_write.setChecked(False)
        d.save();self.wait(lambda:d.job is None and d.fact['rows'][0]['mode']==0o440)
        self.assertEqual((self.root/'changed.txt').stat().st_mode&0o777,0o440)
        self.assertFalse(d.apply.isEnabled())

    def test_collision_stale_identity_and_symlink_permissions_are_safe(self):
        row=self.row();(self.root/'taken.txt').write_text('keep')
        with self.assertRaises(FileExistsError):data.apply_local(row,'taken.txt',0o600,self.job)
        self.assertEqual(self.file.stat().st_mode&0o777,0o640);self.assertEqual((self.root/'taken.txt').read_text(),'keep')
        self.file.rename(self.root/'old.txt');self.file.write_text('replacement')
        with self.assertRaises(ValueError):data.apply_local(row,'moved.txt',0o600,self.job)
        link=self.root/'link';link.symlink_to(self.file);linkrow=self.row(link)
        with self.assertRaises(ValueError):data.apply_local(linkrow,'link',0o600,self.job)
        self.assertEqual(self.file.read_text(),'replacement')

    def test_readonly_acl_and_network_are_not_editable(self):
        remote=data.inspect([str(self.file)],self.job,remote=True)['rows'][0]
        self.assertFalse(remote['can_mode'])
        with self.assertRaises(ValueError):data.apply_local(remote,'note.txt',0o600,self.job)
        # Named ACLs must not silently be flattened by basic permission controls.
        with patch.object(data.os,'listxattr',return_value=['system.posix_acl_access']):
            aclrow=self.row();self.assertFalse(aclrow['can_mode'])
            with self.assertRaises(ValueError):data.apply_local(aclrow,'note.txt',0o600,self.job)

    def test_cancel_and_close_do_not_save_edits(self):
        d=self.dialog();d.name.setText('unsaved.txt');d.reject()
        self.assertTrue(self.file.exists());self.assertFalse((self.root/'unsaved.txt').exists())
        self.job.cancelled.set()
        with self.assertRaises(Exception):data.folder_totals([str(self.root)],self.job)

    def test_drive_properties_show_server_role_and_checksum_without_download(self):
        address='lumen-drive://00000000-0000-0000-0000-000000000001/file/00000000-0000-0000-0000-000000000002/test.txt'
        self.w.drive.entries[address]=('file',dict(id='v',name='test.txt',size=5,sha256='abcdef',revision=7,mime='text/plain'))
        self.w.drive.config={'server':'https://example.invalid','token':'test'}
        d=Properties(self.w,[address]);d.show();self.addCleanup(lambda:d.reject() if isValid(d) else None);self.wait(lambda:d.fact is not None)
        self.assertTrue(d.name.isReadOnly());self.assertFalse(d.hash_button.isEnabled());self.assertFalse(d.permissions_widget.isVisible())
        self.assertEqual(d.hash_value.text(),'abcdef');self.assertIn('reader',d.details.toPlainText())
        self.assertFalse(d.apply.isEnabled())

    def test_close_during_background_work_cleans_up_worker(self):
        d=self.dialog()
        def wait_for_cancel(job):
            job.cancelled.wait(2);job.check()
        d.start('count',wait_for_cancel);d.reject();d.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.wait(lambda:not self.app.property_jobs)
        self.assertTrue(self.file.exists())

    def test_drive_rename_uses_revision_and_retains_current_connection(self):
        address='lumen-drive://space/file/file-id/test.txt'
        self.w.drive.entries[address]=('file',dict(id='file-id',folder_id=None,name='test.txt',size=5,revision=7))
        config={'server':'https://example.invalid','token':'test'}
        self.w.drive.config=config;self.w.drive.space='space';self.w.drive.spaces=[dict(id='space',role='editor')]
        d=Properties(self.w,[address]);d.show();self.addCleanup(lambda:d.reject() if isValid(d) else None);self.wait(lambda:d.fact is not None)
        with patch('lumen_connect.read_config',return_value=config), patch('drive_sync.request',return_value={'name':'new.txt','revision':8}) as request, patch.object(self.w,'refresh'):
            d.name.setText('new.txt');d.save();self.wait(lambda:d.job is None)
            request.assert_called_once_with(config,'/files/file-id',dict(name='new.txt',revision=7,trashed=False,folder_id=None))
            self.assertEqual(d.fact['rows'][0]['revision'],8)
            self.assertTrue(d.paths[0].endswith('/new.txt'))

    def test_special_permissions_are_preserved(self):
        self.file.chmod(0o2640);row=self.row()
        data.apply_local(row,'note.txt',0o2440,self.job)
        self.assertEqual(self.file.stat().st_mode&0o7777,0o2440)
        with self.assertRaises(ValueError):data.apply_local(self.row(),'note.txt',0o440,self.job)


if __name__=='__main__':unittest.main()
