"""New-file reconciliation stays linear and persists bindings before upload."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import drive_sync as drive


class Entries(dict):
    scans = 0
    def values(self):
        self.scans += 1
        return super().values()


class DriveSyncScalingTests(unittest.TestCase):
    def sync_files(self, count):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)
            for n in range(count): (path/f'{n}.txt').write_bytes(b'Synthetic')
            info=path.stat();folder=str(uuid4());entries=Entries();durable=set();uploads=[]
            root=dict(path=str(path),identity=[info.st_dev,info.st_ino],folder=folder,enabled=True,
                      entries=entries,dirs={},conflicts={},cache=dict(files={},folders={folder:dict(id=folder,name='Root',parent_id=None,trashed=False,can_write=True)}))
            def persist(): durable.update(entries)
            def upload(config, target, staged, destination, request_id, digest, previous, progress, **options):
                self.assertIn(request_id,durable)
                self.assertEqual(entries[request_id]['path'],options['filename'])
                identity=str(uuid4());options['remember'](identity)
                uploads.append(options['filename'])
                return dict(id=identity,family=identity,revision=1,name=options['filename'],folder_id=destination,
                            sha256=digest,size=9,trashed=False,current=True,can_write=True)
            with patch.object(drive,'refresh'),patch.object(drive.transport,'upload',side_effect=upload):
                drive.reconcile({},root,persist,lambda *_:None)
            self.assertEqual(len(uploads),count);self.assertEqual(len(set(uploads)),count)
            self.assertEqual(len(root['cache']['files']),count)
            return entries.scans

    def test_doubling_new_files_does_not_double_full_binding_scans(self):
        first=self.sync_files(32);second=self.sync_files(64)
        self.assertEqual(first,second,'Each new file rescans the growing binding map')
        self.assertLessEqual(second,4)
