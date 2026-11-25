"""Regression checks for the reviewed native titles and compact actions."""
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QEvent, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea
from app import create_app
from plan_dialog import PlanDialog


class NativeCraftTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or create_app('graphite')

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.windows = []

    def tearDown(self):
        for window in self.windows: window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def flow(self):
        d = PlanDialog(None, dict(name='Unterlagen prüfen', roots=[str(self.root)],
            steps=[dict(action='write', path=str(self.root/'Ergebnis.txt'), text='Prüfergebnis')],
            prompt='', approved=False), file_action=True)
        self.windows.append(d); d.resize(320, 640); d.show(); QTest.qWait(40)
        return d

    def test_compact_actions_stay_inside_the_scrolling_content(self):
        d = self.flow()
        viewport = d.findChild(QScrollArea).viewport()
        for text in ['Aktion ergänzen', 'KI-Auftrag bearbeiten', 'Ordner && Freigabe']:
            button = next(b for b in d.findChildren(QPushButton) if b.text() == text)
            left = button.mapTo(viewport, QPoint()).x()
            self.assertGreaterEqual(left, 0, text)
            self.assertLessEqual(left + button.width(), viewport.width(), text)
        self.assertLessEqual(d.width(), 320)

    def test_single_folder_uses_the_singular(self):
        d = self.flow()
        self.assertTrue(d.native_sentence.summary.text().startswith('1 freigegebener Ordner ·'))
