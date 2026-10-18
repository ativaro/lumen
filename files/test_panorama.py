"""Native navigation uses existing app routes and does not change the open document."""
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtTest import QTest
from appearance import apply_design
from panorama import install
from PySide6.QtGui import QIcon
from panorama import AppIcon


class PanoramaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_shared_bar_preserves_current_app_and_keyboard_focus(self):
        window = QMainWindow()
        self.addCleanup(window.close)
        with patch('lumen_apps.launch') as launch:
            bar = install(window, 'files')
            self.assertIs(install(window, 'files'), bar)
            window.resize(760, 600); window.show()
            actions = [a for a in bar.actions() if a.isCheckable()]
            current = next(a for a in actions if a.isChecked())
            for theme in ('glass', 'graphite', 'atelier', 'midnight'):
                apply_design(self.app, theme); QTest.qWait(10)
                self.assertTrue(bar.isVisible())
                self.assertGreaterEqual(bar.height(), 44)
            actions[1].trigger()
            launch.assert_called_once_with('wissen')
            self.assertTrue(current.isChecked())
            self.assertEqual(window.width(), 760)
            current.trigger()
            self.assertEqual(launch.call_count, 1)

    def test_web_halo_icons_remain_transparent_in_all_native_themes(self):
        for theme in ('glass', 'graphite', 'atelier', 'midnight'):
            apply_design(self.app, theme)
            for key in ('lumen', 'wissen', 'workbench', 'code', 'meetings', 'files', 'inbox', 'vault'):
                image = QIcon(AppIcon(key)).pixmap(32, 32).toImage()
                self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
                self.assertTrue(any(image.pixelColor(x, y).alpha() for x in range(32) for y in range(32)))


if __name__ == '__main__': unittest.main()
