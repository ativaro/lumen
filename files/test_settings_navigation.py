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


if __name__ == '__main__': unittest.main()
