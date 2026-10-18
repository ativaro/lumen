"""Small native layout checks; no imported documents or provider actions."""
import os
import tempfile
import unittest
from unittest.mock import patch


class ReadingLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.env=patch.dict(os.environ,{'QT_QPA_PLATFORM':'offscreen','LUMEN_DATA':cls.tmp.name+'/data','LUMEN_TOOLS_DATA':cls.tmp.name+'/tools','LUMEN_LANGUAGE':'de','XDG_CONFIG_HOME':cls.tmp.name+'/config'})
        cls.env.start();cls.addClassCleanup(cls.env.stop)
        from PySide6.QtWidgets import QApplication
        from app import create_app
        cls.app=QApplication.instance() or create_app()

    def test_compose_separates_original_and_result_without_hiding_actions(self):
        from tools_translate import Translate
        from PySide6.QtCore import QPoint
        from PySide6.QtTest import QTest
        w=Translate();self.addCleanup(w.close);w.show()
        for width,height in ((1280,800),(960,640)):
            w.resize(width,height);QTest.qWait(30)
            gap=w.output.mapTo(w,QPoint(0,0)).x()-w.input.mapTo(w,QPoint(w.input.width(),0)).x()
            self.assertGreaterEqual(gap,12)
            self.assertTrue(w.rect().contains(w.run_button.mapTo(w,w.run_button.rect().bottomRight())))
            self.assertIsNone(w.engine)

    def test_compact_reading_preserves_note_and_existing_panel_toggle(self):
        from tools_reader import Reader
        from PySide6.QtWidgets import QPushButton
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        w=Reader();self.addCleanup(w.close);w.body.setEnabled(True);w.show();w.resize(1280,800);QTest.qWait(30)
        w.note.setPlainText('Nicht gespeicherte Randnotiz');note=w.note
        toggle=next(b for b in w.findChildren(QPushButton) if b.text()=='Lesemodus')
        w.resize(960,640);QTest.qWait(30)
        self.assertFalse(w.sidebar.isVisible());self.assertFalse(w.rail.isVisible())
        self.assertGreater(w.views.width(),w.width()*.7)
        self.assertEqual(w.content.contentsMargins().left(),0)
        self.assertIn('Bibliothek',toggle.text());self.assertEqual(toggle.accessibleName(),toggle.text())
        w.resize(1280,800);QTest.qWait(20)
        self.assertTrue(w.sidebar.isVisible());self.assertTrue(w.rail.isVisible())
        self.assertEqual(w.content.contentsMargins().left(),16)
        w.resize(960,640);QTest.qWait(20)
        QTest.mouseClick(toggle,Qt.LeftButton);QTest.qWait(20)
        self.assertTrue(w.sidebar.isVisible());self.assertTrue(w.rail.isVisible())
        self.assertIs(w.note,note);self.assertEqual(w.note.toPlainText(),'Nicht gespeicherte Randnotiz')
        self.assertEqual(w.content.contentsMargins().left(),16)
        w.resize(1280,800);QTest.qWait(20);self.assertTrue(w.rail.isVisible())
        QTest.mouseClick(toggle,Qt.LeftButton);w.resize(960,640);QTest.qWait(20);w.resize(1280,800);QTest.qWait(20)
        self.assertFalse(w.rail.isVisible());self.assertEqual(w.note.toPlainText(),'Nicht gespeicherte Randnotiz')

    def test_embedded_reader_keeps_its_existing_host_navigation(self):
        from tools_reader import Reader
        from PySide6.QtWidgets import QWidget,QVBoxLayout
        from PySide6.QtTest import QTest
        host=QWidget();self.addCleanup(host.close);layout=QVBoxLayout(host)
        w=Reader();w.setParent(host);w.setMinimumSize(0,0);layout.addWidget(w);host.show();host.resize(960,640);QTest.qWait(30)
        self.assertFalse(w.sidebar.isHidden());self.assertFalse(w.rail.isHidden())

    def test_empty_compact_reader_keeps_document_selection_reachable(self):
        from tools_reader import Reader
        from PySide6.QtTest import QTest
        w=Reader();self.addCleanup(w.close);w.show();w.resize(960,640);QTest.qWait(30)
        self.assertTrue(w.sidebar.isVisible());self.assertTrue(w.add_button.isEnabled())
        w.body.setEnabled(True);QTest.qWait(20);self.assertFalse(w.sidebar.isVisible())
        w.body.setEnabled(False);QTest.qWait(20);self.assertTrue(w.sidebar.isVisible())


if __name__=='__main__':unittest.main()
