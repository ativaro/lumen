import tempfile
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from interop_open import focus
from interop_parts import FIELDS,capture_part
from interop_sources import capture


class FocusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name); self.windows = []
        self.env=patch.dict(os.environ,{'LUMEN_DATA':str(self.root/'state')});self.env.start();self.addCleanup(self.env.stop)

    def tearDown(self):
        for window in self.windows: window.close(); window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def window(self, cls):
        result = cls(self.root); self.windows.append(result); return result

    def ref(self, window, key, part, **position):
        kind,_,value=part.partition(':')
        if kind in FIELDS:
            window.focus_record(key);part=capture_part(window,kind,int(value))
        return dict(app=window.name, kind='record', id=key, title='Test', position=dict(part=part, **position))







    def test_vault_snapshot_focus_is_registered_before_fast_result(self):
        from tools_vault import Vault
        window=self.window(Vault);key=window.library.create('Plan',repository='/tmp/repo',sources=[],excludes=[])
        def immediate(text,function,done,**kwargs):
            done([dict(id='chosen-snapshot',time='2026-10-03T12:00:00',paths=['/tmp/source'])]);return True
        with patch.object(window,'work',side_effect=immediate):
            focus(window,dict(app='vault',kind='record',id=key,title='Plan',position=dict(part='snapshot:chosen-snapshot')))
        self.assertEqual(window.selected(),'chosen-snapshot')

if __name__ == '__main__': unittest.main()
