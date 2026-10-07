"""Native Studio navigation, actual file previews and shared chat protections."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt, QCoreApplication, QEvent
from PySide6.QtGui import QImage, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton


class StudioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()
        path = Path(__file__).resolve().parents[1] / 'agent-app/main.py'
        spec = importlib.util.spec_from_file_location('studio_test_main', path)
        cls.desktop = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.desktop)

    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {'LUMEN_DATA': self.tmp + '/state'}))
        self.settings = QSettings(self.tmp + '/prefs.ini', QSettings.IniFormat)
        with patch.object(self.desktop, 'QSettings', return_value=self.settings):
            self.window = self.desktop.LumenWindow(self.tmp)
        self.window.chat.backend.refresh_sessions = lambda: None
        self.window.resize(1480, 900); self.window.show(); self.app.processEvents()

    def tearDown(self):
        self.window.chat.backend.busy = False
        self.window.close(); self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def wait(self, condition):
        until = time.monotonic() + 8
        while not condition() and time.monotonic() < until: QTest.qWait(20)
        self.assertTrue(condition())

    def present(self, paths, title='Results'):
        from lumen_mcp_tools import invoke
        result = invoke('lumen_present_files', dict(paths=paths, title=title))
        messages = [{'info': {'role': 'assistant'}, 'parts': [{'type': 'tool',
            'tool': 'cachyos_lumen_present_files', 'state': {'status': 'completed',
            'output': json.dumps(result)}}]}]
        self.window.chat.backend.messages = messages
        self.window.chat.backend.messagesChanged.emit(messages)
        return messages

    def test_answer_cards_keep_message_order_actions_and_session_isolation(self):
        from PySide6.QtWidgets import QCheckBox
        chat = self.window.chat
        def message(role, text, identity):
            return dict(info=dict(role=role, id=identity), parts=[dict(type='text', text=text)])
        history = [message('user', 'First', 'u1'), message('assistant', '- [ ] Review', 'a1')]
        chat.backend.session = 'one'
        chat.show_messages(history); QTest.qWait(30)
        first = chat.transcript.rows[1][2]
        first.findChild(QCheckBox).click()
        history.append(message('user', 'Second', 'u2'))
        chat.show_messages(history); QTest.qWait(30)
        history.append(message('assistant', 'Next answer', 'a2'))
        chat.show_messages(history); QTest.qWait(30)
        positions = [chat.transcript.box.indexOf(row[0]) for row in chat.transcript.rows]
        self.assertEqual(positions, sorted(positions))
        chat.transcript.answer_actions.findChildren(QPushButton)[0].click()
        self.assertEqual(self.app.clipboard().text(), 'Next answer')
        self.assertTrue(first.findChild(QCheckBox).isChecked())
        chat.backend.session = 'two'; chat.backend.sessionChanged.emit('two'); QTest.qWait(30)
        self.assertFalse(first.findChild(QCheckBox).isChecked())

    def test_notification_discussion_is_a_draft_and_preserves_existing_work(self):
        from unittest.mock import MagicMock
        activation = self.desktop.DesktopActivation()
        activation.window = self.window
        self.window.chat.backend.messages = []
        self.window.chat.composer.clear()
        with patch.object(self.window.chat.backend, 'send') as send:
            self.assertFalse(activation.DiscussNotification('x' * 101, '', ''))
            self.assertTrue(activation.DiscussNotification('Test app', 'Example', '$(touch /not-executed)'))
            original = self.window.chat.composer.toPlainText()
            self.assertIn('$(touch /not-executed)', original)
            self.assertIn('Test app', original)
            send.assert_not_called()
            other = MagicMock()
            with patch.object(self.desktop, 'LumenWindow', return_value=other) as create:
                self.assertTrue(activation.DiscussNotification('Second app', 'Other', 'Context'))
                create.assert_called_once()
            self.assertEqual(self.window.chat.composer.toPlainText(), original)
            other.chat.composer.setPlainText.assert_called_once()
            other.chat.backend.send.assert_not_called()

    def test_new_answer_scrolls_to_start_and_stream_preserves_position(self):
        from assistant import ChatPanel
        panels = [self.window.chat, ChatPanel(self.tmp, settings=self.settings)]
        panels[1].resize(800, 700); panels[1].show()
        def message(role, text, key):
            return dict(info=dict(role=role, id=key), parts=[dict(type='text', text=text)])
        try:
            for chat in panels:
                with self.subTest(surface=type(chat).__name__):
                    history = [message('user', 'Question', 'u1'), message('assistant', 'Old answer\n\n' * 80, 'a1'), message('user', 'Next question', 'u2')]
                    chat.show_messages(history); QTest.qWait(80)
                    scroll = chat.transcript.verticalScrollBar(); scroll.setValue(0)
                    answer = message('assistant', 'New answer\n\n' * 80, 'a2')
                    chat.show_messages(history + [answer]); QTest.qWait(80)
                    start = scroll.value()
                    self.assertGreater(start, 500)
                    self.assertLess(start, scroll.maximum() - 200)
                    answer['parts'][0]['text'] += 'More text\n\n' * 30
                    chat.show_messages(history + [answer]); QTest.qWait(80)
                    self.assertAlmostEqual(scroll.value(), start, delta=2)
                    scroll.setValue(120)
                    answer['parts'][0]['text'] += 'Another chunk'
                    chat.show_messages(history + [answer]); QTest.qWait(80)
                    self.assertAlmostEqual(scroll.value(), 120, delta=2)
                    chat.show_messages(history + [answer, message('user', 'Again', 'u3'), message('assistant', 'Third answer\n\n' * 80, 'a3')]); QTest.qWait(80)
                    self.assertGreater(scroll.value(), start + 500)
        finally:
            panels[1].close(); panels[1].deleteLater()

    def test_enter_sends_shift_enter_inserts_line_break(self):
        chat = self.window.chat
        chat.composer.setFocus(); QTest.qWait(20)
        with patch.object(chat.backend, 'send') as send:
            chat.composer.setPlainText('First line')
            chat.composer.moveCursor(chat.composer.textCursor().MoveOperation.End)
            QTest.keyClick(chat.composer, Qt.Key_Return, Qt.ShiftModifier)
            self.assertEqual(chat.composer.toPlainText(), 'First line\n')
            send.assert_not_called()
            chat.composer.insertPlainText('Second line')
            QTest.keyClick(chat.composer, Qt.Key_Return)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args.args[0], 'First line\nSecond line')
            self.assertEqual(chat.composer.toPlainText(), '')
            chat.composer.setPlainText('Keypad enter')
            QTest.keyClick(chat.composer, Qt.Key_Enter)
            self.assertEqual(send.call_count, 2)
            chat.backend.busy = True
            chat.composer.setPlainText('Keep while busy')
            QTest.keyClick(chat.composer, Qt.Key_Return)
            self.assertEqual(send.call_count, 2)
            self.assertEqual(chat.composer.toPlainText(), 'Keep while busy')

    def test_session_history_title_and_busy_navigation_use_backend(self):
        chat = self.window.chat
        sessions = [{'id':'one','title':'Research','time':{'updated':1}}, {'id':'two','title':'Photos','time':{'updated':2}}]
        chat.backend.sessionsChanged.emit(sessions)
        recent = self.window.navigation.recent
        self.assertEqual(recent.item(0).text(), 'Photos')
        with patch.object(chat.backend, 'select_session') as select:
            self.window.navigation.open_session(recent.item(0)); select.assert_called_once_with('two')
            chat.backend.busy = True; chat.backend.busyChanged.emit(True)
            self.assertFalse(recent.isEnabled())
            self.window.navigation.open_session(recent.item(1)); select.assert_called_once()
        chat.backend.busy = False; chat.backend.session = 'two'; chat.backend.sessionChanged.emit('two')
        self.assertEqual(chat.heading.text(), 'Photos')
        self.assertEqual(set(self.window.nav_buttons), {0,4,8,9})

    def test_real_image_preview_strip_close_and_compact_view(self):
        paths = []
        for i in range(2):
            path = Path(self.tmp)/f'image{i}.png'
            image = QImage(160, 120, QImage.Format_RGB32); image.fill(QColor('blue')); image.save(str(path)); paths.append(str(path))
        chat = self.window.chat; surface = self.window.studio
        self.present(paths)
        self.wait(lambda: surface.preview.proc is None and not surface.preview.pixmap.isNull())
        self.assertTrue(surface.pane.isVisible()); self.assertEqual(str(surface.preview.path), paths[0])
        surface.preview.filmstrip.chosen.emit(1)
        self.assertEqual(str(surface.preview.path), paths[1]); self.assertEqual(surface.choice.currentData(), paths[1])
        surface.close_preview.click(); self.assertFalse(surface.pane.isVisible())
        self.assertIsNone(surface.preview.proc); self.assertIsNone(surface.preview.filmstrip.loader.proc)
        chat.preview_button.click(); self.assertTrue(surface.pane.isVisible())
        self.window.resize(900, 680); surface.narrow_preview = False; self.app.processEvents(); surface.update_visibility()
        self.assertFalse(surface.pane.isVisible()); self.assertTrue(chat.isVisible())
        chat.preview_button.click(); self.assertTrue(surface.pane.isVisible()); self.assertFalse(chat.isVisible())
        surface.close_preview.click(); self.assertTrue(chat.isVisible())
        self.assertEqual(chat.paths, [])

    def test_text_and_pdf_preview_and_result_replacement(self):
        from test_pdf_fixtures import document
        pdf=Path(self.tmp)/'sample.pdf';document(['Preview sample']*2,position=(30,30)).save(pdf)
        chat = self.window.chat; preview = self.window.studio.preview
        self.present([str(pdf)])
        self.wait(lambda: preview.proc is None and preview.pages == 2)
        preview.next.click(); self.wait(lambda: preview.proc is None)
        self.assertEqual(preview.page, 2)
        text = Path(self.tmp)/'note.txt'; text.write_text('An actual local note')
        self.present([str(text)])
        self.wait(lambda: preview.proc is None and 'actual local note' in preview.text.toPlainText())
        self.assertEqual(preview.path, text)
        self.present([]); self.assertFalse(self.window.studio.pane.isVisible())
        self.assertIsNone(preview.path)

    def test_context_menu_permission_and_transcript_safety_are_preserved(self):
        chat = self.window.chat
        self.assertFalse(chat.dont_ask.isChecked()); self.assertFalse(chat.options_box.isVisible())
        chat.options.click(); self.assertTrue(chat.dont_ask.isVisible()); self.assertTrue(chat.persona.isVisible())
        self.assertGreaterEqual(len(chat.attach.menu().actions()), 6)
        with patch.object(chat.backend, 'permission_reply') as reply:
            chat.show_requests([{'id':'permission-test', 'permission':'edit','patterns':['example.txt']}], [])
            self.assertTrue(chat.requests.isVisible())
            buttons = chat.requests.widget().findChildren(QPushButton)
            buttons[0].click(); reply.assert_called_once_with('permission-test', False)
        chat.show_messages([{'info':{'role':'assistant'},'parts':[{'type':'text','text':'**Visible answer**\n<img src="file:///private-test">'}]}])
        self.assertIn('Visible answer', chat.transcript.toPlainText())
        self.assertIsNone(chat.transcript.loadResource(2, None))
        chat.output_menu.aboutToShow.emit()
        self.assertTrue(chat.output_menu.actions()[0].isEnabled())
        self.assertEqual(chat.backend.auto_approve, False)

    def test_results_are_independent_of_attachments_and_reset_with_session(self):
        file = Path(self.tmp)/'result.txt'; file.write_text('Lumen result')
        attachment = Path(self.tmp)/'input.txt'; attachment.write_text('User input')
        chat, surface = self.window.chat, self.window.studio
        chat.paths = [str(attachment)]; chat.update_context()
        self.assertEqual(surface.paths, []); self.assertFalse(surface.pane.isVisible())
        messages = self.present([str(file)], 'Created document')
        self.wait(lambda: 'Lumen result' in surface.preview.text.toPlainText())
        self.assertEqual(surface.heading.text(), 'Created document')
        chat.context_tools.clear(); self.assertEqual(surface.paths, [str(file)])
        surface.close_pane(); chat.backend.messagesChanged.emit(messages)
        self.assertFalse(surface.pane.isVisible())
        file.write_text('Updated result'); self.present([str(file)])
        self.wait(lambda: 'Updated result' in surface.preview.text.toPlainText())
        state = self.window.recovery_state()
        chat.backend.new_conversation()
        self.assertEqual(surface.paths, []); self.assertFalse(surface.pane.isVisible())
        with patch.object(chat.backend, 'send') as send:
            self.window.restore_recovery(state); send.assert_not_called()
        self.assertEqual(surface.paths, [str(file)])
        chat.backend.new_conversation(); chat.backend.messagesChanged.emit(messages)
        self.assertEqual(surface.paths, [str(file)])

    def test_recovery_keeps_draft_and_persona_without_replaying(self):
        chat = self.window.chat; chat.composer.setPlainText('Unsaved draft')
        chat.backend.pending_persona = 'professional'
        state = self.window.recovery_state()
        chat.composer.clear()
        with patch.object(chat.backend, 'send') as send:
            self.window.restore_recovery(state); send.assert_not_called()
        self.assertEqual(chat.composer.toPlainText(), 'Unsaved draft')
        self.assertEqual(chat.backend.persona_choice(), 'professional')


if __name__ == '__main__': unittest.main()
