import errno
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import lumen_transfers as transfers
from lumen_store import Store
from transfer_copy import execute


class CopyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.store = Store(self.base / "state")
        self.target = self.base / "target"
        self.target.mkdir()
        self.source = self.base / "folder"
        self.source.mkdir()
        (self.source / "large.bin").write_bytes(b"abcdefg\0" * 1024**2)
        (self.source / "empty").mkdir()
        (self.source / "link").symlink_to("large.bin")

    def ticket(self):
        return transfers.create(
            self.store, "copy", [str(self.source)], str(self.target)
        )

    def test_partial_directory_resumes_without_publishing_or_overwriting(self):
        value = self.ticket()

        def interrupt(done, total):
            if done >= 2 * 1024**2:
                raise OSError("disconnected")

        with self.assertRaises(OSError):
            execute(self.store, value, interrupt)
        self.assertFalse((self.target / "folder").exists())
        resumed = self.store.setting(transfers.PREFIX + value["id"])
        part = self.target / resumed["copy_plan"]["stage"] / "folder/large.bin"
        inode = part.stat().st_ino
        self.assertEqual(part.stat().st_size, 2 * 1024**2)
        execute(self.store, resumed, lambda *_: None)
        self.assertEqual((self.target / "folder/large.bin").stat().st_ino, inode)
        self.assertEqual(
            (self.target / "folder/large.bin").read_bytes(),
            (self.source / "large.bin").read_bytes(),
        )
        self.assertTrue((self.target / "folder/empty").is_dir())
        self.assertEqual(os.readlink(self.target / "folder/link"), "large.bin")
        with self.assertRaises(FileExistsError):
            execute(self.store, self.ticket(), lambda *_: None)

    def test_changed_source_or_partial_stops_and_cancel_removes_only_partial(self):
        value = self.ticket()
        with self.assertRaises(OSError):
            execute(
                self.store, value, lambda *_: (_ for _ in ()).throw(OSError("pause"))
            )
        resumed = self.store.setting(transfers.PREFIX + value["id"])
        (self.source / "large.bin").write_bytes(b"new content")
        with self.assertRaisesRegex(ValueError, "Quelldatei"):
            execute(self.store, resumed, lambda *_: None)
        transfers.cleanup(self.store, resumed)
        self.assertEqual((self.source / "large.bin").read_bytes(), b"new content")
        self.assertEqual(list(self.target.iterdir()), [])

    def test_publish_receipt_recovers_lost_completion(self):
        value = self.ticket()
        import transfer_copy

        with patch.object(
            transfer_copy, "file_change", side_effect=OSError("lost completion")
        ):
            with self.assertRaises(OSError):
                execute(self.store, value, lambda *_: None)
        resumed = self.store.setting(transfers.PREFIX + value["id"])
        # Simulate a crash after rename but before the completed-source checkpoint.
        resumed = transfers.update(self.store, value["id"], done=[])
        execute(self.store, resumed, lambda *_: None)
        self.assertEqual(
            (self.target / "folder/large.bin").read_bytes(),
            (self.source / "large.bin").read_bytes(),
        )

    def test_drive_copy_cleanup_resumes_after_staging_parent_was_removed(self):
        from transfer_copy import root
        value = transfers.create(self.store, "drive-copy", ["lumen-drive://test"],
                                 "lumen-drive://target", drive={"scope": "test"})
        cache = self.store.directory / ("drive-copy-" + value["id"])
        cache.mkdir()
        value["download_plan"] = {"root": root(cache), "stage": ".lumen-drive/copy-test"}
        # A prior cleanup removed the staging parent before the cache itself.
        transfers.cleanup(self.store, value)
        self.assertFalse(cache.exists())
        transfers.cleanup(self.store, value)

    def test_unknown_network_capacity_does_not_mean_full(self):
        from types import SimpleNamespace
        import drive_local

        unknown = SimpleNamespace(f_blocks=0, f_bfree=0, f_bavail=0, f_frsize=512)
        value = self.ticket()
        value["portable"] = True
        with patch.object(drive_local.os, "fstatvfs", return_value=unknown):
            execute(self.store, value, lambda *_: None)
        self.assertEqual((self.target / "folder/large.bin").read_bytes(),
                         (self.source / "large.bin").read_bytes())

    def test_known_full_target_stops_before_copying_bytes(self):
        from types import SimpleNamespace
        import drive_local

        full = SimpleNamespace(f_blocks=1024, f_bfree=0, f_bavail=0, f_frsize=4096)
        with patch.object(drive_local.os, "fstatvfs", return_value=full):
            with self.assertRaisesRegex(ValueError, "Zu wenig"):
                execute(self.store, self.ticket(), lambda *_: None)
        self.assertFalse((self.target / "folder").exists())

    def test_unsupported_kernel_copy_mid_file_falls_back_to_reading(self):
        real, calls = os.copy_file_range, []

        def partial(*args):
            calls.append(args)
            if len(calls) > 1:
                raise OSError(errno.EXDEV, "cross-device")
            return real(*args)

        with patch("transfer_copy.os.copy_file_range", partial):
            execute(self.store, self.ticket(), lambda *_: None)
        self.assertGreater(len(calls), 1)
        self.assertEqual(
            (self.target / "folder/large.bin").read_bytes(),
            (self.source / "large.bin").read_bytes(),
        )

    def test_local_names_are_not_restricted_to_drive_names(self):
        for name in (" trailing ", "back\\slash", "x" * 240):
            (self.source / name).write_bytes(b"local")
        execute(self.store, self.ticket(), lambda *_: None)
        for name in (" trailing ", "back\\slash", "x" * 240):
            self.assertEqual((self.target / "folder" / name).read_bytes(), b"local")


if __name__ == "__main__":
    unittest.main()
