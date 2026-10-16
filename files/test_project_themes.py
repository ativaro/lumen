"""Project surfaces and open dialogs follow the shared live theme."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from appearance import apply_design
from tools_workbench import Workbench


class ProjectThemeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')

    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.dict(os.environ, LUMEN_TOOLS_DATA=str(root),
            LUMEN_DATA=str(root/'state'), XDG_CONFIG_HOME=str(root/'config')))
        apply_design(self.app, 'glass')
        self.window = Workbench(root)
        self.key = self.window.library.create('Theme check', notes='Synthetic project', resources=[], references=[])
        self.window.home.choose(self.key)
        self.window.resize(1180, 820)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def assert_role(self, widget, role, expected):
        self.assertEqual(widget.palette().color(role).name(), self.app.palette().color(expected).name(), widget.objectName())

    def test_existing_surfaces_and_dialogs_switch_between_all_themes(self):
        from project_dialogs import open_dialog
        w = self.window
        w.journal.tabs.setCurrentIndex(2)
        w.journal.add_source.click()
        picker = w.journal.source_picker
        details = open_dialog(w)
        for theme in ('glass', 'atelier', 'graphite', 'midnight', 'clear', 'system', 'glass'):
            with self.subTest(theme=theme):
                apply_design(self.app, theme)
                QTest.qWait(20)
                self.assert_role(w.home, QPalette.Window, QPalette.Window)
                self.assert_role(w.journal.findChild(QWidget, 'journalPage'), QPalette.Window, QPalette.Window)
                self.assert_role(w.journal.findChild(QLabel, 'journalMuted'), QPalette.WindowText, QPalette.PlaceholderText)
                self.assert_role(w.home.overview.cards[0], QPalette.Button, QPalette.Base)
                self.assert_role(w.home.new_project, QPalette.Button, QPalette.Highlight)
                self.assert_role(w.home.new_project, QPalette.ButtonText, QPalette.HighlightedText)
                self.assert_role(picker, QPalette.Window, QPalette.Window)
                self.assert_role(details, QPalette.Window, QPalette.Window)
                self.assert_role(details.title, QPalette.Base, QPalette.Base)
                self.assert_role(details.apply, QPalette.Button, QPalette.Highlight)
        QTest.keyClick(details, Qt.Key_Escape)
        QTest.keyClick(picker, Qt.Key_Escape)
        self.assertFalse(details.isVisible())
        self.assertFalse(picker.isVisible())
        self.assertEqual(w.library.get(self.key)['title'], 'Theme check')


if __name__ == '__main__':
    unittest.main()
