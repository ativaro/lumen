"""Complete selected directories are streamed without file count or text-only gates."""
import io
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from server_code_transport import folder_archive


class FolderStreamTest(unittest.TestCase):
    def test_configuration_binary_empty_directory_executable_and_external_link(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); folder = root / 'selected'; folder.mkdir()
            (folder / 'empty').mkdir(); (folder / '.env.example').write_text('EXAMPLE=1')
            (folder / 'start.sh').write_text('#!/bin/sh\n'); (folder / 'start.sh').chmod(0o755)
            (folder / 'binary.bin').write_bytes(bytes(range(256))*4096)
            (root / 'outside.txt').write_text('not selected')
            (folder / 'outside').symlink_to(root / 'outside.txt')
            for index in range(260): (folder / str(index)).write_text('module')
            data = b''.join(folder_archive(folder, lambda: None))
            with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                self.assertEqual(len(archive.getmembers()), 265)
                self.assertEqual(archive.getmember('start.sh').mode, 0o755)
                self.assertTrue(archive.getmember('empty').isdir())
                self.assertTrue(archive.getmember('outside').issym())
                self.assertEqual(archive.extractfile('binary.bin').read(), bytes(range(256))*4096)
                self.assertNotIn('outside.txt', archive.getnames())

    def test_cancelled_import_does_not_continue_reading(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / 'file').write_bytes(b'x'*1024*1024)
            def cancelled(): raise InterruptedError('cancelled')
            with self.assertRaises(InterruptedError):
                b''.join(folder_archive(root, cancelled))


if __name__ == '__main__': unittest.main()
