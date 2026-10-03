import json
from pathlib import Path
import tempfile
import unittest
from tools_ui import Job
from tools_data import Cancelled
from interop_exports import export_payload

class ExportTest(unittest.TestCase):
    def test_portable_package_preserves_originals_and_cancellation_leaves_no_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'invoice.txt';source.write_text('Original')
            payload=dict(title='Gerät',text='Details',paths=[str(source)])
            path=Path(export_payload(payload,root,Job(lambda _:None)))
            self.assertEqual((path/'files/001-invoice.txt').read_text(),'Original')
            self.assertEqual(json.loads((path/'manifest.json').read_text())['files'][0]['size'],8)
            job=Job(lambda _:None);job.cancelled.set();before=set(root.iterdir())
            with self.assertRaises(Cancelled):export_payload(payload,root,job)
            self.assertEqual(set(root.iterdir()),before);self.assertEqual(source.read_text(),'Original')

if __name__=='__main__':unittest.main()
