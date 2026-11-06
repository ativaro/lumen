"""KIO-FUSE metadata refreshes must not invalidate a checksummed upload."""

import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import drive_local as local


class TransferStampTest(unittest.TestCase):
    def setUp(self):
        self.info = SimpleNamespace(st_dev=os.makedev(0, 77), st_ino=42,
                                    st_size=123, st_mtime_ns=456, st_ctime_ns=789)
        self.before = local.signature(self.info)
        self.mount = '524 1204 0:77 / /run/user/1000/kio rw - fuse.kio-fuse kio-fuse rw\n'

    def test_only_kio_ctime_refresh_is_accepted(self):
        self.info.st_ctime_ns += 1
        with patch.object(Path, 'read_text', return_value=self.mount):
            self.assertTrue(local.transfer_unchanged(self.before, self.info))
            for field in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns'):
                original = getattr(self.info, field)
                setattr(self.info, field, original + 1)
                self.assertFalse(local.transfer_unchanged(self.before, self.info), field)
                setattr(self.info, field, original)

    def test_local_other_fuse_and_unknown_mounts_keep_ctime_guard(self):
        self.info.st_ctime_ns += 1
        for mount in ('', self.mount.replace('0:77', '0:78'),
                      self.mount.replace('fuse.kio-fuse', 'btrfs'),
                      self.mount.replace('fuse.kio-fuse', 'fuse.sshfs')):
            with patch.object(Path, 'read_text', return_value=mount):
                self.assertFalse(local.transfer_unchanged(self.before, self.info))
        with patch.object(Path, 'read_text', side_effect=OSError):
            self.assertFalse(local.transfer_unchanged(self.before, self.info))

    def test_identical_stamp_needs_no_mount_lookup(self):
        with patch.object(Path, 'read_text', side_effect=AssertionError):
            self.assertTrue(local.transfer_unchanged(self.before, self.info))


if __name__ == '__main__':
    unittest.main()
