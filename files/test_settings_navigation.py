import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QSettings, Qt, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtTest import QTest
from app import create_app
from settings_dialog import SettingsDialog


class SettingsNavigationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or create_app()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {'LUMEN_DATA':self.tmp.name+'/state'}); self.env.start(); self.addCleanup(self.env.stop)
        self.settings = QSettings(self.tmp.name+'/assistant.ini', QSettings.IniFormat)
        self.files = QSettings(self.tmp.name+'/files.ini', QSettings.IniFormat)
        self.dialog = SettingsDialog(assistant_settings=self.settings, files_settings=self.files, load_system=False)
        self.addCleanup(self.dispose)

    def dispose(self):
        self.dialog.close(); self.dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_system_category_entry_launches_app_on_first_click(self):
        d = self.dialog; d.show(); QTest.qWait(30)
        with patch('lumen_apps.QProcess.startDetached', return_value=(True, 42)) as launch:
            # Programmatic settings navigation must not launch another app.
            d.open_page(d.hardware_page); launch.assert_not_called()
            for category in (3, 5):
                d.navigation.show_category(category); self.app.processEvents()
                entry = next(b for b in d.navigation.overview.findChildren(QPushButton)
                             if b.isVisible() and b.accessibleName().startswith('Lumen System.'))
                QTest.mouseClick(entry, Qt.LeftButton)
                self.assertTrue(launch.call_args, 'The first click must start Lumen System')
                self.assertTrue(launch.call_args.args[0].endswith('lumen-system'))
                self.assertEqual(d.stack.currentIndex(), d.hardware_page)
                launch.reset_mock()

    def test_system_search_launches_but_policy_target_only_opens_settings(self):
        d = self.dialog
        with patch('lumen_apps.QProcess.startDetached', return_value=(True, 42)) as launch:
            d.navigation.search.setText('Lumen System')
            d.navigation.activate_first()
            self.assertEqual(launch.call_count, 1)
            launch.reset_mock()
            d.navigation.activate_page(d.hardware_page, d.stack.widget(d.hardware_page))
            launch.assert_not_called()
        with patch('lumen_apps.launch', side_effect=OSError('Launch unavailable')):
            d.open_system(); self.assertEqual(d.status.text(), 'Launch unavailable')

    def test_section_rows_have_readable_labels_after_category_switch(self):
        from PySide6.QtWidgets import QLabel
        d = self.dialog; d.show(); QTest.qWait(20)
        for index in (1, 3, 0):
            d.nav.setCurrentRow(index); self.app.processEvents()
            entries = [b for b in d.navigation.overview.findChildren(QPushButton) if b.isVisible()]
            self.assertTrue(entries)
            for entry in entries:
                self.assertGreaterEqual(entry.height(), 72)
                for caption in entry.findChildren(QLabel):
                    self.assertGreater(caption.height(), 0)

    def test_overview_and_details_share_the_panorama_content_edge(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QLabel
        from desktop_design import NAV_WIDTH
        d = self.dialog; d.resize(960, 640); d.show(); QTest.qWait(30)
        d.navigation.show_category(0); self.app.processEvents()
        overview_title = next(label for label in d.navigation.overview.findChildren(QLabel)
                              if label.text() == d.navigation.categories[0]['title'])
        overview_x = overview_title.mapTo(d, QPoint()).x()
        page = next(index for index in range(d.stack.count())
                    if d.apply_appearance in d.stack.widget(index).findChildren(QPushButton))
        d.open_page(page); self.app.processEvents()
        detail_title = next(label for label in d.stack.widget(page).findChildren(QLabel)
                            if label.text() == d.page_info[page]['title'])
        self.assertEqual(detail_title.mapTo(d, QPoint()).x(), overview_x)
        self.assertEqual(d.navigation.nav.width(), NAV_WIDTH)
        title = next(label for label in d.navigation.findChildren(QLabel)
                     if label.objectName() == 'desktopAppTitle')
        self.assertEqual(title.font().pixelSize(), 26)

    def test_compact_design_action_scrolls_into_view_and_works_from_keyboard(self):
        from PySide6.QtCore import QPoint, QPointF
        from PySide6.QtGui import QWheelEvent
        d = self.dialog; d.resize(960, 640); d.show(); QTest.qWait(30)
        page = next(index for index in range(d.stack.count())
                    if d.apply_appearance in d.stack.widget(index).findChildren(QPushButton))
        d.open_page(page); self.app.processEvents()
        scroll = d.stack.widget(page); viewport = scroll.viewport()
        point = viewport.rect().center()
        wheel = QWheelEvent(QPointF(point), QPointF(viewport.mapToGlobal(point)),
                            QPoint(), QPoint(0, -360), Qt.NoButton, Qt.NoModifier,
                            Qt.NoScrollPhase, False)
        QApplication.sendEvent(viewport, wheel); self.app.processEvents()
        bounds = d.apply_appearance.rect().translated(d.apply_appearance.mapTo(viewport, QPoint()))
        self.assertTrue(viewport.rect().contains(bounds), bounds)
        d.apply_appearance.setFocus(Qt.TabFocusReason)
        with patch.object(d, 'perform') as perform:
            QTest.keyClick(d.apply_appearance, Qt.Key_Space)
            self.assertEqual(perform.call_args.args[0], 'appearance')

    def test_wizard_changes_refresh_shared_voice_fields_without_reverting_them(self):
        from PySide6.QtWidgets import QFormLayout
        d = self.dialog
        def wizard(*args, **kwargs):
            self.settings.setValue('speechEngine', 'qwen'); self.settings.setValue('speechSpeaker', 'Aiden')
            self.settings.setValue('speechLanguage', 'en'); self.settings.setValue('speechVocabulary', 'New term')
        with patch('setup_dialog.open_setup', side_effect=wizard): d.open_setup_wizard(2)
        self.assertEqual(d.voice_form.itemAt(0, QFormLayout.FieldRole).widget().currentData(), 'qwen')
        self.assertEqual(d.voice_form.itemAt(1, QFormLayout.FieldRole).widget().currentText(), 'Aiden')
        self.assertEqual(d.recognition_form.itemAt(0, QFormLayout.FieldRole).widget().currentData(), 'en')
        self.assertEqual(d.recognition_form.itemAt(1, QFormLayout.FieldRole).widget().text(), 'New term')

    def test_six_categories_cover_every_old_page_and_new_speech_pages(self):
        d = self.dialog
        self.assertEqual(d.nav.count(),6)
        represented = {row['page'] for group in d.navigation.categories for row in group['sections']}
        self.assertEqual(represented,set(range(d.stack.count())))
        self.assertEqual(d.navigation.content.currentIndex(),0)
        self.assertEqual(self.settings.allKeys(),[]); self.assertEqual(self.files.allKeys(),[])
        for index in range(d.stack.count()):
            d.open_page(index); self.assertEqual(d.stack.currentIndex(),index)
            self.assertEqual(d.navigation.content.currentIndex(),1)
        for key,index in d.app_pages.items():
            d.open_page(index); self.assertEqual(d.stack.currentIndex(),index,key)

    def test_setting_search_opens_hidden_control_and_preserves_unsaved_values(self):
        d = self.dialog; d.show(); self.app.processEvents()
        d.delay.setValue(700)
        selected_design = d.appearance.checkedButton()
        d.open_page(3); d.theme_buttons['midnight'].setFocus()
        d.nav_search.setFocus(); d.nav_search.setText('Tipp-Pause')
        self.assertGreater(d.navigation.results.count(),0)
        QTest.keyClick(d.nav_search, Qt.Key_Return); QTest.qWait(10)
        self.assertEqual(d.stack.currentIndex(),1)
        self.assertTrue(d.delay.isVisible()); self.assertEqual(d.delay.value(),700)
        self.assertIs(d.appearance.checkedButton(), selected_design)
        self.assertEqual(self.files.allKeys(),[])
        d.nav_search.setText('Stimme')
        self.assertTrue(any(page==d.speech_output_page for page,target,category in d.navigation.hits))
        d.nav_search.setText('this-does-not-exist')
        self.assertFalse(d.navigation.empty.isHidden())
        self.assertEqual(d.navigation.results.count(),0)
        d.nav_search.clear(); self.assertEqual(d.stack.currentIndex(),1)
        self.assertEqual(self.settings.allKeys(),[])

    def test_search_does_not_index_personal_values_or_trigger_system_actions(self):
        d = self.dialog; d.workdir.setText('/private-unique-folder')
        d.perform = lambda *args: self.fail('Navigation must not perform system writes')
        d.nav_search.setText('private-unique-folder'); self.assertEqual(d.navigation.results.count(),0)
        d.nav_search.setText('Fensterdekoration')
        hit = next((i for i,(page,target,category) in enumerate(d.navigation.hits) if target and isinstance(target,QPushButton) and 'Fensterdekoration' in target.text()),None)
        self.assertIsNotNone(hit)
        d.show(); d.navigation.activate_result(d.navigation.results.item(hit)); QTest.qWait(10)
        self.assertEqual(d.stack.currentIndex(),3)
        self.assertTrue(d.navigation.hits[hit][1].isVisible())
        self.assertEqual(self.settings.allKeys(),[])

    def test_category_switch_keeps_drafts_and_back_returns_to_overview(self):
        d = self.dialog; d.open_page(1); d.hidden.setChecked(True)
        d.nav.setCurrentRow(5); self.assertEqual(d.navigation.content.currentIndex(),0)
        d.open_page(1); self.assertTrue(d.hidden.isChecked())
        d.navigation.back.click(); self.assertEqual(d.navigation.content.currentIndex(),0)
        self.assertEqual(self.files.allKeys(),[])

    def test_troubleshooter_is_in_maintenance_and_routes_repairs_without_changing_settings(self):
        d = self.dialog; d.show(); d.nav.setCurrentRow(5); self.app.processEvents()
        entry = next(b for b in d.navigation.overview.findChildren(QPushButton)
                     if b.isVisible() and b.accessibleName().startswith('Lumen Troubleshooter.'))
        QTest.mouseClick(entry, Qt.LeftButton)
        self.assertEqual(d.stack.currentIndex(), d.troubleshooter_page)
        self.assertIsNone(d.troubleshooter.job)
        d.troubleshooter.show_report(dict(checked_at='2026-10-05T12:00:00+00:00', checks=[
            dict(title='Engine', state='warning', message='Needs setup', action='model')]))
        self.assertTrue(d.troubleshooter.copy.isEnabled())
        with patch.object(d, 'open_setup_wizard') as wizard:
            action = d.troubleshooter.results.itemAt(0).widget().findChild(QPushButton)
            QTest.mouseClick(action, Qt.LeftButton); wizard.assert_called_once_with(1)
        d.troubleshooter.copy.click(); self.assertIn('Needs setup', self.app.clipboard().text())
        self.app.clipboard().clear()
        self.assertEqual(self.settings.allKeys(), []); self.assertEqual(self.files.allKeys(), [])

    def test_troubleshooter_worker_finishes_and_can_be_cancelled(self):
        from assistant_backend import ENGINE_VERSION
        from PySide6.QtCore import QProcess
        tool = Path(self.tmp.name)/'opencode'
        tool.write_text('#!/bin/sh\nprintf "%s\\n" "' + ENGINE_VERSION + '"\n'); tool.chmod(0o700)
        t = self.dialog.troubleshooter
        with patch.dict(os.environ, LUMEN_OPENCODE_BIN=str(tool), PATH=self.tmp.name):
            t.run()
            self.assertFalse(t.start.isEnabled())
            for _ in range(100):
                if t.job is None: break
                QTest.qWait(30)
            self.assertIsNone(t.job); self.assertTrue(t.copy.isEnabled(), t.status.text())
            self.assertEqual(t.results.count(), 7); self.assertTrue(t.start.isEnabled())
            t.run(); job = t.job; t.stop()
            self.assertIsNone(t.job); self.assertEqual(job.state(), QProcess.NotRunning)
            self.assertTrue(t.start.isEnabled()); self.assertFalse(t.copy.isEnabled())


if __name__ == '__main__': unittest.main()
