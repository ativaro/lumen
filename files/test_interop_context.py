"""Exercise contextual entry points and native review."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication


class ContextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'LUMEN_DATA':str(self.root/'state'),'LUMEN_TOOLS_DATA':str(self.root/'tools'),
                                       'XDG_CONFIG_HOME':str(self.root/'config')})
        self.env.start();self.addCleanup(self.env.stop);self.windows=[];self.addCleanup(self.close)

    def close(self):
        for window in self.windows:
            if window.job:window.job.cancelled.set();window.job.wait(5000)
            self.app.processEvents();window.close();window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def wait(self,predicate):
        until=time.monotonic()+8
        while time.monotonic()<until:
            self.app.processEvents()
            if predicate():return
            time.sleep(.01)
        self.fail('Native operation did not finish')



    def test_dropped_reader_files_are_queued_without_an_import_chooser(self):
        from types import SimpleNamespace
        from interop_context import receive_drop
        paths=[]
        for name in ('one.txt','two.txt'):
            path=self.root/name;path.write_text(name);paths.append(str(path))
        with patch('interop_ui.controller') as control,patch('interop_ui.reviewed_send') as review:
            receive_drop(SimpleNamespace(name='reader'),dict(paths=paths))
        self.assertEqual([c.args[0] for c in control.return_value.enqueue.call_args_list],[{'path':p} for p in paths])
        review.assert_not_called()


if __name__=='__main__':unittest.main()
