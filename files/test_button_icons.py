"""Primary action glyphs retain the text's live palette contrast."""
import unittest
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QIcon, QPalette
from PySide6.QtWidgets import QApplication
from appearance import apply_design
from tools_ui import button


class ButtonIconTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.app = QApplication.instance() or create_app('graphite')

    def colors(self, icon, mode=QIcon.Normal):
        image = icon.pixmap(24, 24, mode).toImage()
        colors = [image.pixelColor(x, y).getRgb()[:3]
                  for x in range(image.width()) for y in range(image.height())
                  if image.pixelColor(x, y).alpha() > (64 if mode == QIcon.Disabled else 128)]
        self.assertTrue(colors, {'mode':str(mode),'maximum_alpha':max((image.pixelColor(x,y).alpha() for x in range(image.width()) for y in range(image.height())),default=0),'size':(image.width(),image.height())})
        return colors

    def test_loaded_previous_typography_module_keeps_buttons_working(self):
        import studio_design
        with patch.object(studio_design, 'button_icon', None):
            action = button('Speichern', lambda: None, 'document-save', True)
        self.assertFalse(action.icon().isNull())
        action.deleteLater(); QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_primary_icon_follows_text_across_themes_and_disabled_state(self):
        apply_design(self.app, 'graphite')
        action = button('Speichern', lambda: None, 'document-save', True)
        try:
            for theme in ('graphite', 'glass', 'atelier', 'midnight', 'clear'):
                apply_design(self.app, theme); action.ensurePolished()
                for enabled, role in ((True, QPalette.HighlightedText), (False, QPalette.PlaceholderText)):
                    action.setEnabled(enabled); self.app.processEvents()
                    expected = self.app.palette().color(role).getRgb()[:3]
                    mode = QIcon.Normal if enabled else QIcon.Disabled
                    for actual in self.colors(action.icon(), mode):
                        self.assertLessEqual(max(abs(a-b) for a,b in zip(actual, expected)), 1,
                                             (theme, enabled, actual, expected))
                    if enabled:
                        self.assertTrue(all(max(abs(a-b) for a,b in zip(color, expected)) <= 1
                                            for color in self.colors(action.icon(), QIcon.Active)))
        finally:
            action.deleteLater(); QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_normal_icon_is_unchanged_and_late_primary_marking_is_supported(self):
        apply_design(self.app, 'graphite')
        action = button('Neu', lambda: None, 'list-add')
        try:
            self.assertEqual(self.colors(action.icon()), self.colors(QIcon.fromTheme('list-add')))
            action.setObjectName('primary'); action.ensurePolished()
            expected = self.app.palette().color(QPalette.HighlightedText).getRgb()[:3]
            self.assertTrue(all(max(abs(a-b) for a,b in zip(color, expected)) <= 1
                                for color in self.colors(action.icon())))
            retained = QIcon(action.icon())
        finally:
            action.deleteLater(); QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertFalse(retained.pixmap(24, 24).isNull())
