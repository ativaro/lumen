"""Mount readiness must wait for FUSE without accepting a local fallback."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import backup_network

class MountReadinessTest(unittest.TestCase):
    def test_announced_share_waits_until_its_fuse_directory_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp); (runtime/'gvfs').mkdir()
            share = runtime/'gvfs/share'
            file = Mock(); file.get_path.side_effect = [None, str(share), str(share)]
            def register(_): share.mkdir(exist_ok=True)
            with patch.dict(os.environ, XDG_RUNTIME_DIR=tmp), patch('os.path.ismount', return_value=True), patch('backup_network.time.sleep', side_effect=register):
                self.assertEqual(backup_network.mounted_path(file), str(share))

    def test_missing_fuse_external_path_and_unavailable_share_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp); (runtime/'gvfs').mkdir()
            file = Mock()
            with patch.dict(os.environ, XDG_RUNTIME_DIR=tmp):
                with patch('os.path.ismount', return_value=False):
                    self.assertIsNone(backup_network.mounted_path(file))
                    file.get_path.assert_not_called()
                with patch('os.path.ismount', return_value=True):
                    file.get_path.return_value = tmp
                    self.assertIsNone(backup_network.mounted_path(file))
                    (runtime/'gvfs/escape').symlink_to(runtime, target_is_directory=True)
                    file.get_path.return_value = str(runtime/'gvfs/escape')
                    self.assertIsNone(backup_network.mounted_path(file))
                    file.get_path.return_value = None
                    self.assertIsNone(backup_network.mounted_path(file, timeout=0))

if __name__ == '__main__': unittest.main()
