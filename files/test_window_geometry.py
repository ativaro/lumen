import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QSettings,QRect
from PySide6.QtWidgets import QApplication,QWidget
from window_geometry import restore,remember,fit


class WindowGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.settings=QSettings(self.temp.name+'/settings.ini',QSettings.IniFormat)
        self.window=QWidget();self.addCleanup(self.window.deleteLater)

    def test_first_open_has_readable_default_and_reopen_remembers_user_size(self):
        restore(self.window,self.settings,'geometry',(1400,900))
        self.assertEqual((self.window.width(),self.window.height()),(1400,900))
        self.window.resize(1250,810);remember(self.window,self.settings,'geometry')
        self.window.resize(500,400);restore(self.window,self.settings,'geometry',(1400,900))
        self.assertEqual((self.window.width(),self.window.height()),(1250,810))

    def test_disabled_restore_ignores_previous_geometry(self):
        self.window.resize(500,400);remember(self.window,self.settings,'geometry')
        restore(self.window,self.settings,'geometry',(1400,900),False)
        self.assertEqual((self.window.width(),self.window.height()),(1400,900))

    def test_corrupt_preference_falls_back_without_preventing_start(self):
        self.settings.setValue('geometry','old-invalid-value')
        restore(self.window,self.settings,'geometry',(1400,900))
        self.assertEqual(self.window.width(),1400)

    def test_small_or_changed_monitor_keeps_window_visible_without_increasing_minimum(self):
        screen=SimpleNamespace(availableGeometry=lambda:QRect(1800,200,1024,768))
        self.window.resize(1600,1000);self.window.move(-500,-500)
        self.window.setMinimumSize(840,600)
        with patch.object(self.window,'screen',return_value=screen):fit(self.window)
        self.assertTrue(QRect(1824,224,976,720).contains(QRect(self.window.pos(),self.window.size())))
        self.assertEqual(self.window.minimumWidth(),840)

    def test_maximized_geometry_is_preserved(self):
        self.window.showMaximized();self.app.processEvents()
        remember(self.window,self.settings,'geometry');self.window.showNormal()
        restore(self.window,self.settings,'geometry',(1400,900))
        self.assertTrue(self.window.isMaximized())
