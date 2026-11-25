"""Old local project draft links are never written by native chat."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from tools_data import Library

class ProjectConversationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=self.enterContext(tempfile.TemporaryDirectory());self.root=Path(self.tmp)
        self.enterContext(patch.dict(os.environ,LUMEN_TOOLS_DATA=self.tmp,LUMEN_DATA=self.tmp+'/state'))
        self.app=QApplication.instance() or QApplication([])
        self.enterContext(patch('desktop_backend.DesktopBackend.refresh_sessions'))
        from assistant import ChatPanel
        self.panel=ChatPanel(self.tmp)
        self.library=Library('workbench');self.project=self.library.create('Original',resources=[],references=[])
        self.addCleanup(self.close)

    def close(self):
        self.panel.backend.busy=False;self.panel.tracker.interrupt();self.panel.context_tools.close()
        self.panel.backend.shutdown();self.panel.deleteLater();self.app.processEvents()

    def test_local_project_parameter_is_rejected_without_touching_original(self):
        before=self.library.get(self.project)
        self.assertFalse(self.panel.prepare_draft('Question',project=self.project))
        self.assertEqual(self.library.get(self.project),before)
        self.assertIn('Lumen Server',self.panel.error.text())

    def test_recovery_keeps_draft_text_and_discards_no_originals(self):
        self.panel.prepare_draft('Unsent text')
        state=self.panel.recovery_state();state['draft_project']=self.project
        self.panel.new_conversation();self.panel.restore_recovery(state)
        self.assertEqual(self.panel.composer.toPlainText(),'Unsent text')
        self.assertNotIn('draft_project',self.panel.recovery_state())
        self.assertEqual(self.library.get(self.project)['references'],[])
