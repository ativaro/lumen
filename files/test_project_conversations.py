"""Project drafts link only the conversation created by an actual send."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from tools_data import Library


class ProjectConversationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.tmp)
        self.enterContext(patch.dict(os.environ, LUMEN_TOOLS_DATA=self.tmp, LUMEN_DATA=self.tmp+'/state'))
        self.app = QApplication.instance() or QApplication([])
        self.enterContext(patch('desktop_backend.DesktopBackend.refresh_sessions'))
        from assistant import ChatPanel
        self.panel = ChatPanel(self.tmp)
        self.library = Library('workbench')
        self.project = self.library.create('Evidence', resources=[], references=[])
        self.addCleanup(self.close)

    def close(self):
        self.panel.backend.busy = False
        self.panel.tracker.interrupt()
        self.panel.context_tools.close()
        self.panel.backend.shutdown()
        self.panel.deleteLater()
        self.app.processEvents()

    def send(self, session):
        def accepted(*args, **kwargs):
            self.panel.backend.busy = True
            self.panel.backend.session = session
            self.panel.backend.sessionChanged.emit(session)
            return True
        with patch.object(self.panel.backend, 'send', side_effect=accepted):
            self.panel.submit(self.panel.composer.toPlainText())
        self.panel.backend.busy = False

    def test_sent_draft_is_linked_once_and_visible_in_project_conversations(self):
        from tools_workbench import Workbench
        p = self.panel
        self.assertTrue(p.prepare_draft('What does VCF cost?', project=self.project))
        self.assertEqual(self.library.get(self.project)['references'], [])
        self.send('ses_project')
        refs = self.library.get(self.project)['references']
        self.assertEqual(refs, [dict(kind='chat', title='What does VCF cost?',
                                    chat=dict(directory=self.tmp, session='ses_project'))])
        p.backend.sessionChanged.emit('ses_project')
        window = Workbench(self.root)
        try:
            window.focus_record(self.project)
            window.journal.tabs.setCurrentIndex(2)
            self.assertEqual(window.journal.visible_titles, ['What does VCF cost?'])
        finally:
            window.close(); window.deleteLater(); self.app.processEvents()

    def test_abandoned_or_replaced_draft_never_links_an_unrelated_session(self):
        p = self.panel
        p.prepare_draft('Unsent', project=self.project)
        p.new_conversation()
        p.composer.setPlainText('Unrelated')
        self.send('ses_unrelated')
        p.prepare_draft('Unsent again', project=self.project)
        p.prepare_draft('Other draft')
        self.send('ses_other')
        self.assertEqual(self.library.get(self.project)['references'], [])

    def test_current_project_changes_are_preserved_and_archive_blocks_link(self):
        p = self.panel
        p.prepare_draft('Question', project=self.project)
        self.library.update(self.project, notes='Edited elsewhere', references=[dict(kind='task', title='Keep', id='a'*32)])
        self.send('ses_first')
        record = self.library.get(self.project)
        self.assertEqual(record['notes'], 'Edited elsewhere')
        self.assertEqual(len(record['references']), 2)
        p.prepare_draft('Second question', project=self.project)
        self.library.archive(self.project)
        self.send('ses_archived')
        self.assertEqual(self.library.get(self.project)['references'], record['references'])
        from lumen_i18n import tr
        self.assertTrue(p.error.text().startswith(tr('Gespräch konnte dem Projekt nicht zugeordnet werden: ')))

    def test_reader_cannot_prepare_a_project_draft(self):
        self.library.update(self.project, server_bound=True, server_role='reader')
        self.assertFalse(self.panel.prepare_draft('Question', project=self.project))
        self.assertEqual(self.library.get(self.project)['references'], [])

    def test_real_send_creates_reference_and_saved_answer_can_be_reused(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtTest import QTest
        from project_folder_search import search
        p = self.panel; backend = p.backend
        backend.selected_model = 'synthetic/model'
        p.prepare_draft('VCF question', project=self.project)
        def request(method, path, body=None, callback=None):
            if path == '/session':
                QTimer.singleShot(0, lambda: callback(dict(id='ses_actual')))
            elif path.endswith('/prompt_async'):
                QTimer.singleShot(0, lambda: callback({}))
        with patch.object(backend, 'ensure_server', side_effect=lambda callback: callback()), patch.object(backend, 'request', side_effect=request), patch.object(backend, 'poll'):
            p.send(); QTest.qWait(20)
            self.assertEqual(self.library.get(self.project)['references'][0]['chat']['session'], 'ses_actual')
            backend.set_busy(False)
            backend.completed.emit(True, 'VCF evidence from saved answer')
        result = search(self.project, 'VCF')
        self.assertTrue(any(item.get('role') == 'assistant' and 'saved answer' in item['snippet'] for item in result['items']))

    def test_unsent_project_draft_survives_recovery(self):
        p = self.panel
        p.prepare_draft('Recover question', project=self.project)
        state = p.recovery_state()
        p.new_conversation(); p.restore_recovery(state)
        self.assertEqual(p.draft_project, self.project)
        self.send('ses_recovered')
        self.assertEqual(self.library.get(self.project)['references'][0]['chat']['session'], 'ses_recovered')


if __name__ == '__main__':
    unittest.main()
