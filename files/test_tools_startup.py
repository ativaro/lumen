"""Headless acceptance must not claim a real user's single-instance libraries."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tools_app

class StartupIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_incomplete_headless_environment_never_constructs_app_or_library(self):
        for platform in ('offscreen','minimal'):
            for missing in ('LUMEN_DATA','LUMEN_TOOLS_DATA'):
                with self.subTest(platform=platform,missing=missing),tempfile.TemporaryDirectory() as tmp:
                    env={**os.environ,'QT_QPA_PLATFORM':platform,'LUMEN_DATA':tmp+'/state','LUMEN_TOOLS_DATA':tmp+'/tools'};env.pop(missing)
                    with patch.dict(os.environ,env,clear=True),patch('sys.argv',['tools_app.py','workbench']),patch.object(tools_app,'create_app',side_effect=AssertionError('GUI startup reached before isolation validation')) as app,patch('tools_data.Library') as library:
                        with self.assertRaisesRegex(ValueError,'LUMEN_DATA and LUMEN_TOOLS_DATA'):tools_app.main()
                        app.assert_not_called();library.assert_not_called()

    def test_explicit_headless_roots_retain_normal_warm_activation(self):
        class Socket:
            def connectToServer(self,*args):pass
            def waitForConnected(self,*args):return True
            def write(self,*args):pass
            def waitForBytesWritten(self,*args):return True
            def disconnectFromServer(self):pass
        with tempfile.TemporaryDirectory() as tmp:
            for platform in ('offscreen','wayland'):
                env={**os.environ,'QT_QPA_PLATFORM':platform}
                if platform=='offscreen':env.update(LUMEN_DATA=tmp+'/state',LUMEN_TOOLS_DATA=tmp+'/tools')
                else:
                    env.pop('LUMEN_DATA',None);env.pop('LUMEN_TOOLS_DATA',None)
                with patch.dict(os.environ,env,clear=True),patch('sys.argv',['tools_app.py','workbench']),patch.object(tools_app,'create_app'),patch('tools_data.Library',return_value=SimpleNamespace(root=Path(tmp)/'tools/workbench')),patch.object(tools_app,'QLocalSocket',Socket):
                    self.assertEqual(tools_app.main(),0)

if __name__=='__main__':unittest.main()
