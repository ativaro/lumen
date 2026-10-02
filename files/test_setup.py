import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import lumen_setup as setup


class SetupTest(unittest.TestCase):
    def test_download_is_verified_and_atomic(self):
        data = b'a multilingual speech model'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'model'; path.write_bytes(b'previous model')
            def response(*_args, **_kwargs):
                stream = io.BytesIO(data); stream.url = 'https://example.test/model'; return stream
            with patch.object(setup.urllib.request, 'urlopen', side_effect=response), patch.object(setup, 'report'):
                for checksum, size in [('0' * 64, len(data)), (hashlib.sha256(data).hexdigest(), 1)]:
                    with self.assertRaises(ValueError): setup.download('https://example.test/model', path, checksum, size)
                    self.assertEqual(path.read_bytes(), b'previous model')
                    self.assertEqual(list(Path(tmp).iterdir()), [path])
                setup.download('https://example.test/model', path, hashlib.sha256(data).hexdigest(), len(data))
                self.assertEqual(path.read_bytes(), data)

    def test_existing_tools_and_models_are_reused_without_install_or_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); model = root / 'ggml-small-q5_1.bin'; model.write_bytes(b'model')
            with patch.object(setup, 'speech_root', return_value=root), patch.object(setup, 'executable', return_value='/existing/tool'), \
                    patch.object(setup, 'MODEL_SIZE', 5), patch.object(setup, 'MODEL_HASH', hashlib.sha256(b'model').hexdigest()), \
                    patch.object(setup, 'download') as download, patch.object(setup, 'run') as run, patch.object(setup, 'report'):
                self.assertEqual(setup.missing_packages(['engine', 'documents']), [])
                setup.install_dictation()
                download.assert_not_called(); run.assert_not_called()
                with self.assertRaises(ValueError): setup.install_packages(['unapproved-package'])

    def test_discovery_uses_same_user_install_for_setup_and_dictation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_DATA_HOME': tmp}), \
                patch.object(setup.shutil, 'which', return_value=None):
            binary = setup.speech_root() / ('whisper-' + setup.VERSION)
            binary.parent.mkdir(parents=True); binary.write_text('#!/bin/sh\nexit 0\n'); binary.chmod(0o755)
            self.assertEqual(setup.executable('whisper-cli'), str(binary))
            binary.chmod(0o644)
            self.assertFalse(setup.executable('whisper-cli'))


if __name__ == '__main__': unittest.main()
