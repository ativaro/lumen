"""Native System interaction, worker lifecycle and settings integration."""
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QObject, QPoint, QPointF, QProcess, Qt, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from system_app import SystemController, create_window


def sample(at=None):
    return dict(measured=at or time.time(),cpu=24,cpuName='Example CPU',cores=8,
        memory=dict(total=32*1024**3,used=12*1024**3,percent=37.5),
        disk=dict(total=1024**4,used=256*1024**3,available=768*1024**3),
        network=dict(receive=10000,send=2000),gpus=[dict(name='Example GPU',usage=12)],
        processes=[dict(pid=12,name='<script>user process</script>',cpu=24,memory=20*1024**2),
                   dict(pid=13,name='Second',cpu=10,memory=40*1024**2)],
        hardware=dict(measured=at or time.time(), sensors=[dict(device='Example GPU',name='Temperature',value=48,unit='°C')]))


class SystemUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.controller=SystemController(start=False)
        self.controller.accept(sample())
        self.engine,self.window=create_window(self.controller); self.window.show(); QTest.qWait(50)

    def tearDown(self):
        self.controller.shutdown(); self.window.close(); self.engine.deleteLater(); QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete); self.app.processEvents()

    def click(self,name):
        def descendants(item):
            yield item
            for child in item.childItems(): yield from descendants(child)
        item=next((i for i in descendants(self.window.contentItem()) if i.objectName()==name),None)
        self.assertIsNotNone(item,name)
        pos=item.mapToScene(item.boundingRect().center()).toPoint()
        QTest.mouseClick(self.window,Qt.LeftButton,Qt.NoModifier,pos); self.app.processEvents()

    def test_navigation_ranges_sort_and_missing_values(self):
        self.click('page1'); self.assertEqual(self.window.property('page'),1)
        self.click('range900'); self.assertEqual(self.controller.data['seconds'],900)
        self.controller.set_sort('memory'); self.assertEqual(self.controller.data['processes'][0]['pid'],13)
        self.click('page2'); self.assertEqual(self.window.property('page'),2)
        self.controller.latest={}; self.controller.refresh()
        self.assertEqual(self.controller.data['metrics'][0]['value'],'—')
        self.assertEqual(self.controller.data['devices'],[])

    def test_stale_and_paused_are_explicit(self):
        self.controller.last_received=time.monotonic()-10; self.controller.refresh()
        self.assertTrue(self.controller.data['stale'])
        self.click('pause'); self.assertTrue(self.controller.paused)
        self.assertEqual(self.controller.proc.state(),QProcess.NotRunning)

    def test_panorama_geometry_matches_native_header_at_compact_and_normal_width(self):
        from desktop_design import AppHeader, PAGE_MARGIN, NAV_WIDTH
        self.assertEqual(self.controller.theme.get('pageMargin'), PAGE_MARGIN)
        self.assertEqual(self.controller.theme.get('navWidth'), NAV_WIDTH)
        header = AppHeader('Lumen System'); header.ensurePolished(); header.title.ensurePolished()
        try:
            for width in (960, 1280):
                self.window.resize(width, 800); QTest.qWait(30)
                navigation = self.window.findChild(QQuickItem, 'systemNavigation')
                heading = self.window.findChild(QQuickItem, 'systemPageHeading')
                self.assertIsNotNone(navigation); self.assertIsNotNone(heading)
                self.assertEqual(navigation.width(), NAV_WIDTH)
                self.assertEqual(heading.property('font').pixelSize(), header.title.font().pixelSize())
                self.assertEqual(heading.property('font').weight(), header.title.font().weight())
                left = heading.mapToScene(QPointF()).x() - navigation.mapToScene(QPointF(navigation.width(), 0)).x()
                self.assertEqual(left, PAGE_MARGIN)
        finally:
            header.deleteLater()

    def test_english_work_mode_copy_describes_setup_without_a_project_context(self):
        from lumen_i18n import tr
        with patch('lumen_i18n.language', return_value='en'):
            self.assertEqual(tr('Ein Klick, ein passender Arbeitsplatz.'), 'One click to the right setup.')

    def test_analysis_is_explicit_and_passed_as_argument(self):
        with patch('system_app.QProcess.startDetached',return_value=(True,42)) as launch:
            self.controller.accept(sample()); launch.assert_not_called()
            self.controller.investigate()
            args=launch.call_args.args[1]
            self.assertEqual(args[:3],['--page','chat','--prompt'])
            self.assertIn('<script>user process</script>',args[3])
            self.assertEqual(len(args),4)

    def test_settings_entry_opens_system_and_keeps_policy(self):
        from settings_dialog import SettingsDialog
        from PySide6.QtWidgets import QPushButton
        from hardware_ui import HardwareView
        from lumen_store import Store
        d=SettingsDialog(load_system=False,application='system'); d.show(); QTest.qWait(30)
        try:
            self.assertEqual(d.stack.currentIndex(),d.hardware_page)
            b=d.findChild(QPushButton,'openSystem')
            with patch('lumen_apps.QProcess.startDetached',return_value=(True,42)) as launch:
                QTest.mouseClick(b,Qt.LeftButton)
                self.assertTrue(launch.call_args.args[0].endswith('lumen-system'))
            view=d.findChild(HardwareView)
            view.games.setChecked(False)
            self.assertFalse(Store().setting('modelPolicy',{})['pause_on_activity'])
        finally:d.close();d.deleteLater()

    def test_actual_worker_produces_data_and_stops(self):
        self.controller.latest={}; self.controller.start()
        for _ in range(60):
            QTest.qWait(100)
            if self.controller.latest.get('cpu') is not None:break
        self.assertIsNotNone(self.controller.latest.get('cpu'))
        self.controller.shutdown(); self.assertEqual(self.controller.proc.state(),QProcess.NotRunning)

if __name__=='__main__':unittest.main()
