"""Real native project editing with synthetic projects and isolated paths."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from appearance import apply_design
from tools_workbench import Workbench


class ProjectEditorPanoramaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')

    def setUp(self):
        root=Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.dict(os.environ,LUMEN_DATA=str(root/'state'),LUMEN_TOOLS_DATA=str(root/'tools'),XDG_CONFIG_HOME=str(root/'config')))
        apply_design(self.app,'glass')
        with patch('projects_sync_ui.install'):self.w=Workbench(root)
        self.w.error=lambda text:self.fail(text)
        self.project=self.w.library.create('Haus',notes='Project notes',resources=[],references=[])
        self.owner=self.w.projects.add(self.project,'','Umbau','initiative')
        self.task=self.w.projects.add(self.project,self.owner,'Compare','research',goal='Original goal',notes='Keep task notes',interval=7200,deep=True)
        self.w.home.choose(self.project);self.w.navigate(self.project,self.task)
        self.w.resize(1440,1000);self.w.show();self.app.processEvents()

    def tearDown(self):
        self.w.editor.discard();self.w.journal.question.clear();self.w.close();self.w.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);self.app.processEvents()

    def test_editor_has_room_and_small_windows_show_one_content_area(self):
        w=self.w
        self.assertGreaterEqual(w.editor.width(),520)
        self.assertTrue(w.home.pane.isVisible());self.assertFalse(w.journal.side.isVisible())
        for size in ((1040,900),(840,660)):
            w.resize(*size);self.app.processEvents()
            self.assertTrue(w.editor.isVisible());self.assertFalse(w.home.pane.isVisible())
            self.assertGreater(w.goal.width(),700)
            self.assertTrue(w.editor.rect().contains(w.editor.apply.mapTo(w.editor,w.editor.apply.rect().bottomRight())))
        w.editor.close_editor();self.app.processEvents()
        self.assertTrue(w.home.pane.isVisible());self.assertTrue(w.journal.side.isVisible())
        self.assertEqual(w.projects.get(self.task)['goal'],'Original goal')

    def test_keyboard_navigation_disclosure_and_result_views(self):
        w=self.w
        w.title.setFocus();QTest.keyClick(w.title,Qt.Key_Tab)
        self.assertTrue(w.goal.hasFocus())
        self.assertFalse(w.editor.advanced.isVisible());self.assertFalse(w.interval.isVisible())
        w.editor.more_fields.setFocus();QTest.keyClick(w.editor.more_fields,Qt.Key_Space)
        self.assertTrue(w.editor.advanced.isVisible());self.assertTrue(w.notes.isVisible())
        w.editor.navigation.setFocus();w.editor.navigation.setCurrentIndex(0)
        QTest.keyClick(w.editor.navigation,Qt.Key_Right)
        self.assertEqual(w.tabs.currentIndex(),1);self.assertFalse(w.title.isVisible())
        QTest.keyClick(w.editor.navigation,Qt.Key_Right)
        self.assertEqual(w.tabs.currentIndex(),3);self.assertTrue(w.result.isVisible())
        QTest.keyClick(w.editor.navigation,Qt.Key_Left);QTest.keyClick(w.editor.navigation,Qt.Key_Left)
        self.assertEqual(w.tabs.currentIndex(),2);self.assertTrue(w.title.isVisible())

    def test_save_cancel_repetition_and_readonly_keep_existing_data(self):
        w=self.w
        w.title.setText('Updated');w.goal.setPlainText('Updated goal');w.editor.commit()
        saved=w.projects.get(self.task)
        self.assertEqual((saved['title'],saved['goal'],saved['notes'],saved['interval'],saved['deep']),('Updated','Updated goal','Keep task notes',7200,True))
        w.navigate(self.project,self.task);w.schedule.setChecked(True)
        self.assertTrue(w.interval.isVisible());self.assertEqual(w.interval.currentData(),7200)
        with patch('projects_runner.install_timer') as timer:w.editor.commit()
        timer.assert_called_once();self.assertTrue(w.projects.get(self.task)['enabled'])
        w.library.update(self.project,server_bound=True,server_role='reader')
        w.navigate(self.project,self.task)
        self.assertFalse(w.editor.apply.isEnabled());self.assertTrue(w.goal.isReadOnly())
        self.assertFalse(w.schedule.isEnabled());self.assertFalse(w.interval.isEnabled())

    def test_cancel_keeps_the_draft_and_discard_restores_the_journal(self):
        w=self.w;w.goal.setPlainText('Unfinished draft')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):w.editor.close_editor()
        self.assertTrue(w.editor.isVisible());self.assertEqual(w.goal.toPlainText(),'Unfinished draft')
        self.assertFalse(w.journal.side.isVisible())
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Discard):w.editor.close_editor()
        self.assertFalse(w.editor.isVisible());self.assertTrue(w.journal.side.isVisible())
        self.assertEqual(w.projects.get(self.task)['goal'],'Original goal')

    def test_new_task_uses_explicit_assignment_and_themes_keep_geometry(self):
        w=self.w;w.editor.close_editor();w.home.select_initiative(self.owner);w.create_task()
        self.assertTrue(w.editor.assignment.isVisible());self.assertEqual(w.editor.owner.currentData(),self.owner)
        w.title.setText('Another task');w.goal.setPlainText('Another result')
        for theme in ('glass','graphite','atelier','midnight'):
            apply_design(self.app,theme);self.app.processEvents()
            self.assertTrue(w.editor.apply.isVisible());self.assertFalse(w.journal.side.isVisible())
        w.editor.commit();saved=w.projects.get(w.scope)
        self.assertEqual((saved['parent'],saved['kind'],saved['goal']),(self.owner,'research','Another result'))

if __name__=='__main__':unittest.main()
