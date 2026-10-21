"""Reviewed-copy receipts bind first download and final resolve, without new I/O APIs."""
import hashlib
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

import drive_references as drive


class MaterializedPinsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=os.environ['LUMEN_IMPORT_FIXTURES']);self.addCleanup(self.temp.cleanup)
        self.env=patch.dict(os.environ,XDG_CACHE_HOME=self.temp.name);self.env.start();self.addCleanup(self.env.stop)
        self.ref=dict(app='files',kind='drive_file',id=str(uuid4()),title='Selected.md',
                      locator=dict(server='https://synthetic.invalid',account=str(uuid4())))
        self.config=dict(server=self.ref['locator']['server'],token='synthetic-token')
        self.data=b'hello';self.job=SimpleNamespace(check=lambda:None)
        self.row=dict(id=str(uuid4()),family=self.ref['id'],version=1,revision=3,size=5,
                      sha256=hashlib.sha256(self.data).hexdigest(),name='Selected.md',folder_id=str(uuid4()),
                      current=True,trashed=False)
        self.pin={key:self.row[key] for key in drive.COPY_RECEIPT_FIELDS}
        self.resolve=patch.object(drive,'resolve',return_value=(self.config,[dict(self.row)])).start()
        self.addCleanup(patch.stopall)
        self.download=patch('drive_transport.download',side_effect=self.transfer).start()

    def transfer(self,config,root,row,progress):
        Path(root['path'],'stage').write_bytes(self.data);progress(len(self.data),len(self.data));return 'stage'

    def enter(self,**kwargs):return drive.materialized([self.ref],self.job,**kwargs)

    def assert_clean(self):self.assertFalse(list(Path(self.temp.name).glob('lumen-drive-handoffs/copy-*')))

    def changed(self,key):
        value=self.row[key]
        return value+1 if type(value) is int else ('0'*64 if key=='sha256' else 'renamed.md' if key=='name' else str(uuid4()))

    def test_unchanged_full_receipt_is_downloaded_and_cleaned(self):
        with self.enter(expected_rows=[self.pin],max_file_bytes=5) as paths:
            self.assertEqual(Path(paths[0]).read_bytes(),self.data)
            self.assertEqual(self.download.call_args.args[2],self.row)
        self.download.assert_called_once();self.assert_clean()

    def test_changed_receipt_field_is_refused_before_any_download(self):
        for key in drive.COPY_RECEIPT_FIELDS:
            with self.subTest(field=key):
                self.resolve.return_value=(self.config,[dict(self.row,**{key:self.changed(key)})])
                self.download.reset_mock()
                with self.assertRaises(ValueError),self.enter(expected_rows=[self.pin],max_file_bytes=512000):pass
                self.download.assert_not_called();self.assert_clean()
        for key,value in (('current',False),('trashed',True),('version',True),('size',True)):
            with self.subTest(flag_or_type=key):
                self.resolve.return_value=(self.config,[dict(self.row,**{key:value})]);self.download.reset_mock()
                with self.assertRaises(ValueError),self.enter(expected_rows=[self.pin]):pass
                self.download.assert_not_called();self.assert_clean()

    def test_changed_final_receipt_is_never_yielded_and_copy_is_removed(self):
        for key in drive.COPY_RECEIPT_FIELDS:
            with self.subTest(field=key):
                self.resolve.side_effect=[(self.config,[dict(self.row)]),(self.config,[dict(self.row,**{key:self.changed(key)})])]
                self.download.reset_mock()
                with self.assertRaises(ValueError),self.enter(expected_rows=[self.pin]):self.fail('Changed final row was yielded')
                self.download.assert_called_once();self.assert_clean()

    def test_size_cap_is_checked_even_if_current_receipt_matches(self):
        huge=dict(self.row,size=512001);pin={key:huge[key] for key in drive.COPY_RECEIPT_FIELDS}
        self.resolve.return_value=(self.config,[huge])
        with self.assertRaises(ValueError),self.enter(expected_rows=[pin],max_file_bytes=512000):pass
        self.download.assert_not_called();self.assert_clean()

    def test_complete_pin_required_for_every_reference_before_download(self):
        for pins in ([],[self.pin,self.pin],[{key:value for key,value in self.pin.items() if key!='folder_id'}],
                     [dict(self.pin,token='must-not-be-a-pin-field')]):
            with self.subTest(shape=list(map(len,pins))):
                with self.assertRaises(ValueError),self.enter(expected_rows=pins):pass
                self.download.assert_not_called();self.assert_clean()

    def test_legacy_callers_need_no_receipt_and_keep_existing_cleanup(self):
        with self.enter() as paths:self.assertEqual(Path(paths[0]).read_bytes(),self.data)
        self.download.assert_called_once();self.assert_clean()

    def test_unpinned_optional_size_limit_also_prevents_download(self):
        with self.assertRaises(ValueError),self.enter(max_file_bytes=4):pass
        self.download.assert_not_called();self.assert_clean()

    def test_download_failure_never_yields_and_removes_private_copy(self):
        def failed(config,root,row,progress):
            Path(root['path'],'partial').write_bytes(b'h');raise OSError('Synthetic interrupted download')
        self.download.side_effect=failed
        with self.assertRaises(OSError),self.enter(expected_rows=[self.pin]):self.fail('Failed download was yielded')
        self.assert_clean()

if __name__=='__main__':unittest.main()
