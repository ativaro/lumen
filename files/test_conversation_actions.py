import os
import tempfile
import unittest
from unittest.mock import patch
from conversation_actions import transcript_excerpt, handoff_prompt, ConversationActionDialog
from PySide6.QtWidgets import QApplication, QDialogButtonBox

class ConversationActionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def test_handoff_excludes_tool_reasoning_and_synthetic_parts(self):
        messages = [dict(info=dict(role='system'), parts=[dict(type='text',text='private')]),
                    dict(info=dict(role='user'),parts=[dict(type='text',text='你好')]),
                    dict(info=dict(role='assistant'),parts=[dict(type='text',text='Answer'),dict(type='text',text='hidden',synthetic=True),dict(type='tool',text='credential'),dict(type='reasoning',text='secret')])]
        self.assertEqual(transcript_excerpt(messages),'Du:\n你好\n\nLumen:\nAnswer')
        self.assertEqual(len(transcript_excerpt(messages, 5)), 5)
        with self.assertRaises(ValueError): handoff_prompt('x'*20000,'next')
        with self.assertRaises(ValueError): handoff_prompt('context',' ')
        self.assertIn('你好', handoff_prompt('你好','继续'))

    def test_teaching_requires_explicit_success_and_content(self):
        dialog = ConversationActionDialog(None,teaching=True,text='Steps',title='Solution')
        controls=dialog.findChild(QDialogButtonBox)
        controls.accepted.emit(); self.assertEqual(dialog.result(),0)
        dialog.confirmed.setChecked(True);controls.accepted.emit();self.assertEqual(dialog.result(),1)
        dialog.deleteLater()

    def test_verified_solution_is_retrievable_and_edit_invalidates_verification(self):
        from lumen_store import Store
        from lumen_memory import Memory
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA':tmp}):
            memory = Memory(Store(tmp)); memory.configure(True, False)
            row=memory.remember('Configure scanner','1. Connect scanner\n2. Test scan',kind='solution',verification='user')
            self.assertEqual(row['memory']['verification'],'user')
            self.assertTrue(any(n['memory']['kind']=='solution' for n in memory.eligible(tmp)))
            updated=memory.write(row['path'],'# Changed\n\nNew steps',row['hash'])
            self.assertEqual(updated['memory']['verification'],'')
            with self.assertRaises(ValueError): memory.remember('Fact','x',kind='fact',verification='user')

    def test_handoff_cancel_or_changed_destination_does_not_switch(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from conversation_actions import continue_elsewhere
        panel=SimpleNamespace(backend=Mock(busy=False,execution='local',messages=[]),show_error=Mock())
        with patch('desktop_backend.connection',return_value=({'server':'https://first.invalid'},'first')), patch('conversation_actions.ConversationActionDialog') as dialog:
            dialog.return_value.exec.return_value=0
            continue_elsewhere(panel);panel.backend.set_execution.assert_not_called()
        with patch('desktop_backend.connection',side_effect=[({'server':'https://first.invalid'},'first'),({'server':'https://second.invalid'},'second')]), patch('conversation_actions.ConversationActionDialog') as dialog:
            dialog.return_value.exec.return_value=1
            continue_elsewhere(panel);panel.backend.set_execution.assert_not_called();panel.show_error.assert_called_once()
