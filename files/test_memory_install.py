import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import memory_install

LIBRARY = b'ELF library bytes ' * 500


def sha(data):
    return hashlib.sha256(data).hexdigest()


class MemoryInstallTest(unittest.TestCase):
    """The installer against a synthetic model and wheel; nothing is downloaded and no service starts."""

    def setUp(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as wheel:
            wheel.writestr('onnxruntime/LICENSE', 'MIT')
            wheel.writestr('onnxruntime/ThirdPartyNotices.txt', 'notices')
            wheel.writestr('onnxruntime/capi/libonnxruntime.so.1.30.0', LIBRARY)
        self.remote = {memory_install.BASE + 'onnx/model_quint8_avx2.onnx': b'model',
                       memory_install.BASE + 'tokenizer.json': b'tokenizer', 'wheel': archive.getvalue()}
        self.sums = dict(zip(('model/model.onnx', 'model/tokenizer.json', memory_install.RUNTIME),
                             (sha(b'model'), sha(b'tokenizer'), sha(LIBRARY))))
        self.fetched = []
        for patcher in (patch.object(memory_install, 'model_files', lambda: dict(self.sums)),
                        patch.object(memory_install, 'WHEEL', ('wheel', sha(self.remote['wheel']), len(self.remote['wheel']))),
                        patch.object(memory_install, 'supported', return_value=True),
                        patch('lumen_memory.verify', return_value='hybrid')):
            patcher.start(); self.addCleanup(patcher.stop)
        folder = tempfile.TemporaryDirectory(prefix='lumen-memory-install-'); self.addCleanup(folder.cleanup)
        self.home = Path(folder.name) / 'home'

    def download(self, url, destination, checksum, size):
        data = self.remote[url]
        self.fetched.append(url)
        if sha(data) != checksum: raise ValueError('checksum')
        Path(destination).write_bytes(data)

    def install(self):
        memory_install.install(self.home, run=None, download=self.download, report=lambda message: None)

    def test_fresh_home_gets_model_runtime_and_notices(self):
        self.install()
        self.assertEqual(len(self.fetched), 3)
        self.assertEqual((self.home / 'runtime/libonnxruntime.so.1.30.0').read_bytes(), LIBRARY)
        self.assertEqual(sorted(p.name for p in (self.home / 'runtime').iterdir()),
                         ['LICENSE', 'ThirdPartyNotices.txt', 'libonnxruntime.so.1.30.0'])
        self.assertEqual({p.name for p in self.home.iterdir()},
                         {'model', 'runtime', 'setup.lock', 'LICENSE', 'MODEL.md', 'NOTICE.md'})
        self.assertTrue(all((self.home / name).is_file() for name in self.sums))
        self.install()
        self.assertEqual(len(self.fetched), 3)

    def test_existing_model_without_runtime_fetches_only_the_runtime(self):
        (self.home / 'model').mkdir(parents=True)
        (self.home / 'model/model.onnx').write_bytes(b'model')
        (self.home / 'model/tokenizer.json').write_bytes(b'tokenizer')
        self.install()
        self.assertTrue(all((self.home / name).is_file() for name in self.sums))
        self.assertEqual(self.fetched, ['wheel'])

    def test_wrong_library_checksum_is_refused_and_nothing_is_published(self):
        self.sums[memory_install.RUNTIME] = sha(b'another library')
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual(list((self.home / 'runtime').iterdir()), [])
        self.assertEqual([p.name for p in self.home.iterdir() if p.name.startswith('.setup-')], [])


if __name__ == '__main__':
    unittest.main()
