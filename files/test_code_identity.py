"""The Code process and collection must not inherit the Projects icon."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtGui import QIcon,QPixmap,QColor
from PySide6.QtTest import QTest

class CodeIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.root.cleanup)
        cls.env=patch.dict(os.environ,{'LUMEN_DATA':cls.root.name+'/state','LUMEN_TOOLS_DATA':cls.root.name+'/tools','XDG_CONFIG_HOME':cls.root.name+'/config','LUMEN_LANGUAGE':'de'});cls.env.start();cls.addClassCleanup(cls.env.stop)
        from app import create_app
        cls.app=QApplication.instance() or create_app()

    def test_collection_and_dialog_use_code_despite_foreign_application_icon(self):
        from code_library_window import CollectionWindow
        from lumen_store import Store
        icon=QPixmap(16,16);icon.fill(QColor('red'));foreign=QIcon(icon);previous=self.app.windowIcon();self.app.setWindowIcon(foreign);self.addCleanup(self.app.setWindowIcon,previous)
        with tempfile.TemporaryDirectory() as tmp:
            w=CollectionWindow(Store(tmp));self.addCleanup(w.close)
            self.assertEqual(w.windowIcon().name(),'lumen-code')
            d=QDialog(w);self.addCleanup(d.close);self.assertEqual(d.windowIcon().name(),'lumen-code')

    def test_entrypoint_sets_application_icon_before_constructing_collection(self):
        import code_app
        app=self.app
        class ExistingCollection:
            def __init__(self):
                assert app.applicationName()=='lumen-code'
                assert app.desktopFileName()=='lumen-code'
                assert app.windowIcon().name()=='lumen-code'
                from types import SimpleNamespace
                self.library=SimpleNamespace(root=Path('/unused-code-icon-test'))
        class ExistingSocket:
            def connectToServer(self,*_):pass
            def waitForConnected(self,*_):return True
            def write(self,*_):pass
            def waitForBytesWritten(self,*_):pass
            def disconnectFromServer(self):pass
        previous=(app.applicationName(),app.applicationDisplayName(),app.desktopFileName(),app.windowIcon())
        try:
            app.setWindowIcon(QIcon())
            with patch.object(code_app,'create_app',return_value=app),patch.object(code_app,'CollectionWindow',ExistingCollection),patch.object(code_app,'QLocalSocket',ExistingSocket):
                self.assertEqual(code_app.main([]),0)
        finally:
            app.setApplicationName(previous[0]);app.setApplicationDisplayName(previous[1]);app.setDesktopFileName(previous[2]);app.setWindowIcon(previous[3])

if __name__=='__main__':unittest.main()
