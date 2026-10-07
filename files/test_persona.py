import tempfile
import unittest
from PySide6.QtCore import QSettings
from lumen_persona import load, save, effective, normalize, instruction, PRESETS

class PersonaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.settings = QSettings(self.tmp+'/settings.ini', QSettings.IniFormat)

    def test_defaults_and_corrupt_preferences(self):
        self.assertEqual(load(self.settings)['preset'], 'guide')
        for bad in ('broken', '[]', 'null', '{"preset": []}'):
            self.settings.setValue('personaProfile', bad)
            self.assertEqual(load(self.settings)['preset'], 'guide')

    def test_save_only_personality_and_override_preserves_identity(self):
        self.settings.setValue('autoApproveTools', False)
        save(self.settings, dict(preset='companion', name='Nova', user_name='Alex', autoApproveTools=True))
        result = effective(self.settings, 'professional')
        self.assertEqual(result['name'], 'Nova')
        self.assertEqual(result['length'], 'short')
        self.assertEqual(load(self.settings)['preset'], 'companion')
        self.assertFalse(self.settings.value('autoApproveTools', type=bool))
        self.assertEqual(set(self.settings.allKeys()), {'personaProfile', 'autoApproveTools'})

    def test_validation_and_task_boundaries(self):
        value = normalize(dict(preset='professional', length='invalid', name='x'*100, user_name='a\nb'))
        self.assertEqual(value['length'], 'short'); self.assertEqual(len(value['name']),60)
        self.assertNotIn('\n', value['user_name'])
        for preset in PRESETS:
            prompt = instruction(dict(preset=preset))
            self.assertIn('grants no new tools', prompt)
            self.assertIn('structured', prompt)

class PersonaIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()

    def setUp(self):
        import os
        from unittest.mock import patch
        from assistant_backend import OpenCodeBackend
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {'LUMEN_DATA': self.tmp+'/data'}))
        self.backend = OpenCodeBackend(self.tmp)
        self.settings = QSettings(self.tmp+'/assistant.ini', QSettings.IniFormat)
        self.backend.settings = self.settings
        self.backend.selected_model = 'test/model'
        self.backend.ensure_server = lambda callback: callback()
        self.calls = []
        def request(method, path, body=None, callback=None, error=None):
            self.calls.append((path, body))
            if path == '/session' and method == 'POST': callback({'id': 'ses_test'})
        self.backend.request = request
        self.enterContext(patch('lumen_memory.options', return_value={'enabled':False}))
        self.addCleanup(self.dispose)

    def dispose(self):
        from PySide6.QtCore import QCoreApplication, QEvent
        self.backend.shutdown(); self.backend.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def prompt(self, **kwargs):
        self.backend.send('Test', **kwargs)
        result = next(body for path, body in reversed(self.calls) if path.endswith('/prompt_async'))
        self.backend.set_busy(False)
        return result

    def test_actual_request_refreshes_global_settings_and_excludes_proposals(self):
        save(self.settings, dict(preset='companion', name='Nova'))
        first = self.prompt()
        self.assertIn('Nova', first['system']); self.assertIn('companion', first['system'])
        save(QSettings(self.settings.fileName(), QSettings.IniFormat), dict(preset='professional', name='Atlas'))
        second = self.prompt()
        self.assertIn('Atlas', second['system']); self.assertIn('professional', second['system'])
        self.assertEqual(first['parts'], second['parts'])
        self.assertEqual(first['agent'], second['agent'])
        self.assertFalse(self.backend.auto_approve)
        proposal = self.prompt(proposal=True)
        self.assertNotIn('Conversation style', proposal['system'])
        self.assertEqual(proposal['tools'], {'*':False})

    def test_session_override_survives_switch_and_new_chat_resets(self):
        from lumen_store import Store
        self.assertTrue(self.backend.set_persona('challenger'))
        result = self.prompt()
        self.assertIn('challenger', result['system'])
        self.assertEqual(Store().setting('persona/session/ses_test'), 'challenger')
        self.backend.new_conversation(); self.assertEqual(self.backend.persona_choice(), '')
        self.backend.select_session('ses_test'); self.assertEqual(self.backend.persona_choice(), 'challenger')
        self.assertTrue(self.backend.set_persona(''))
        self.assertEqual(self.backend.persona_choice(), '')
        self.backend.set_busy(True)
        self.assertFalse(self.backend.set_persona('maker'))
        self.backend.set_busy(False)
        self.assertFalse(self.backend.set_persona(['bad']))

    def test_editor_unsaved_preview_identity_and_conflicting_window(self):
        from persona_settings import PersonaEditor
        editor = PersonaEditor(self.settings, lambda: None)
        other = PersonaEditor(self.settings, lambda: None)
        try:
            editor.fields['name'].setText('Nova')
            editor.preset.setCurrentIndex(editor.preset.findData('professional'))
            editor.choose_preset(0)
            self.assertEqual(editor.fields['name'].text(), 'Nova')
            self.assertEqual(load(self.settings)['name'], 'Lumen')
            self.assertEqual(editor.fields['length'].currentData(), 'short')
            editor.commit(); self.assertEqual(load(self.settings)['name'], 'Nova')
            other.fields['name'].setText('Conflict'); other.commit()
            self.assertEqual(load(self.settings)['name'], 'Nova')
            self.assertIn('anderen Fenster', other.description.text())
        finally: editor.deleteLater(); other.deleteLater()
