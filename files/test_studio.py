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
    conversation_focus = False
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
        self.launch = self.enterContext(patch('lumen_detail_routes.launch'))
        self.settings = QSettings(self.tmp + '/prefs.ini', QSettings.IniFormat)
        if not self.conversation_focus:
            from studio_preview import StudioSurface
            self.enterContext(patch.object(self.desktop, 'StudioSurface', side_effect=lambda chat, **_: StudioSurface(chat)))
        with patch.object(self.desktop, 'QSettings', return_value=self.settings):
            self.window = self.desktop.LumenWindow(self.tmp)
        self.window.chat.backend.refresh_sessions = lambda: None
        self.window.resize(1480, 900); self.window.show(); self.app.processEvents()

    def tearDown(self):
        self.window.chat.backend.busy = False
        self.window.close(); self.window.deleteLater()
        for widget in self.app.topLevelWidgets():
            widget.close(); widget.deleteLater()
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

    def test_turn_anchor_stream_reading_and_latest(self):
        chat = self.window.chat
        def message(role, text, key):
            return dict(info=dict(role=role, id=key), parts=[dict(type='text', text=text)])
        history = [message('user', 'Question', 'u1'), message('assistant', 'Old answer\n\n' * 80, 'a1'), message('user', 'Next question', 'u2')]
        view = chat.transcript; scroll = view.verticalScrollBar()
        chat.show_messages(history); QTest.qWait(150)
        self.assertAlmostEqual(scroll.value(), view.rows[2][0].y(), delta=2)
        answer = message('assistant', '| A | B |\n|---|---|\n' + '| one | two |\n' * 60, 'a2')
        chat.show_messages(history + [answer]); QTest.qWait(150)
        self.assertAlmostEqual(scroll.value(), view.rows[2][0].y(), delta=2)
        self.assertTrue(view.latest.isVisible())
        view.reading(); scroll.setValue(120)
        answer['parts'][0]['text'] += '\nMore text\n\n' * 30
        chat.show_messages(history + [answer]); QTest.qWait(150)
        self.assertAlmostEqual(scroll.value(), 120, delta=2)
        view.latest.click(); QTest.qWait(50)
        self.assertFalse(view.latest.isVisible())
        position = scroll.value()
        answer['parts'][0]['text'] += '\nAnother paragraph\n\n' * 30
        chat.show_messages(history + [answer]); QTest.qWait(150)
        self.assertAlmostEqual(scroll.value(), position, delta=2)
        self.assertTrue(view.latest.isVisible())
        chat.show_messages(history + [answer, message('user', 'Again', 'u3')]); QTest.qWait(150)
        self.assertAlmostEqual(scroll.value(), view.rows[4][0].y(), delta=2)
        self.window.resize(1100, 700); QTest.qWait(150)
        self.assertAlmostEqual(scroll.value(), view.rows[4][0].y(), delta=2)

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
        self.window.open_search(); controller = self.window.search_controller; chat = self.window.chat
        sessions = [{'id':'one','title':'Research','time':{'updated':1}}, {'id':'two','title':'Photos','time':{'updated':2}}]
        chat.backend.sessionsChanged.emit(sessions)
        self.assertEqual(controller.sessions[1]['title'], 'Photos')
        with patch.object(chat.backend, 'select_session') as select:
            controller.select_session('two'); select.assert_called_once_with('two')
            chat.backend.busy = True; controller.select_session('one'); select.assert_called_once()
        chat.backend.busy = False; chat.backend.session = 'two'; chat.backend.sessionChanged.emit('two')
        self.assertEqual(chat.heading.text(), 'Photos')
        self.assertEqual(self.window.navigation.recent.count(), 2)
        self.assertEqual(self.window.navigation.recent.currentItem().data(Qt.UserRole), 'two')

    def test_context_bar_routes_without_changing_conversation(self):
        bar, chat = self.window.context_bar, self.window.chat
        self.assertEqual(bar.objectName(), 'studioContextBar'); self.assertTrue(self.window.context_timer.isActive())
        chat.composer.setPlainText('Keep draft'); chat.paths = [self.tmp + '/attached.txt']
        with patch.object(chat.backend, 'new_conversation') as new:
            self.window.show_page(8)
            self.assertEqual(self.launch.call_args.args, ('lumen-workbench', ['--section','projects']))
            new.assert_not_called()
        self.assertEqual(chat.composer.toPlainText(), 'Keep draft'); self.assertEqual(len(chat.paths), 1)
        self.assertEqual(self.window.pages.count(), 1)
        self.window.resize(760, 600); self.app.processEvents()
        directory = self.window.context_directory
        self.assertTrue(self.window.context_compact.isVisible()); self.assertTrue(directory.isVisible())
        self.assertEqual(directory.text(), Path(chat.backend.directory).name or '/'); self.assertEqual(directory.toolTip(), chat.backend.directory)
        chat.backend.busy = True; self.window.context_timer.timeout.emit(); self.assertFalse(directory.isEnabled())
        chat.backend.busy = False; self.window.context_timer.timeout.emit(); self.assertTrue(directory.isEnabled())
        self.window.present_action('explain'); self.assertFalse(bar.isVisible()); self.assertFalse(self.window.context_timer.isActive())
        self.window.present_action(''); self.assertTrue(bar.isVisible()); self.assertTrue(self.window.context_timer.isActive())
        chat.composer.clear(); chat.paths = []

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
        self.window.resize(760, 680); surface.narrow_preview = False; self.app.processEvents(); surface.update_visibility()
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
        self.present([]); self.assertTrue(self.window.studio.pane.isVisible())
        self.assertTrue(self.window.studio.answer.isVisible())
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
        self.assertEqual(surface.paths, []); self.assertTrue(surface.pane.isVisible())
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
        self.assertEqual(surface.paths, []); self.assertTrue(surface.pane.isVisible())
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

    def test_workbench_answer_copy_and_session_reset(self):
        chat, surface = self.window.chat, self.window.studio
        self.assertTrue(surface.pane.isVisible()); self.assertFalse(surface.save_answer.isEnabled())
        chat.show_messages([{'info': {'role': 'assistant', 'id': 'answer'}, 'parts': [
            {'type': 'text', 'text': '**Ergebnis**\n<img src="file:///private-test">'}]}])
        self.assertIn('Ergebnis', surface.answer.toPlainText())
        self.assertIsNone(surface.answer.loadResource(2, None))
        surface.copy_answer.click(); self.assertEqual(self.app.clipboard().text(), chat.last_answer)
        chat.backend.busy = True; chat.backend.busyChanged.emit(True)
        self.assertFalse(surface.save_answer.isEnabled())
        chat.backend.busy = False; chat.backend.new_conversation()
        self.assertNotIn('private-test', surface.answer.toPlainText())
        self.assertFalse(surface.copy_answer.isEnabled())

    def test_theme_and_permission_hint(self):
        from PySide6.QtGui import QPalette
        from appearance import apply_design
        chat, space, surface = self.window.chat, self.window.task_controller, self.window.studio
        chat.mode.setCurrentIndex(chat.mode.findData('build'))
        chat.dont_ask.setChecked(True); self.assertIn('Automatische', chat.mode_hint.text())
        chat.dont_ask.setChecked(False); self.assertEqual(chat.mode_hint.text(), 'Mit Freigaben')
        chat.mode.setCurrentIndex(chat.mode.findData('plan')); self.assertEqual(chat.mode_hint.text(), 'Nur lesen')
        for theme in ('graphite', 'atelier', 'midnight', 'glass'):
            apply_design(self.app, theme); QTest.qWait(30)
            for widget in (chat, surface, self.window.context_bar, space.tasks_page):
                self.assertEqual(widget.palette().color(QPalette.Window), self.app.palette().color(QPalette.Window))
        surface.result_tabs.setCurrentIndex(1); self.assertTrue(surface.execution_detail.isVisible())
        surface.result_tabs.setCurrentIndex(0); self.assertTrue(surface.answer.isVisible())
    def test_open_result_pane_follows_work_until_a_result_is_ready(self):
        backend, surface = self.window.chat.backend, self.window.studio
        self.assertTrue(surface.pane.isVisible())
        backend.session = 'auto-tabs'; backend.message_id = 'old-turn'
        old_file = Path(self.tmp) / 'old.md'; old_file.write_text('Old file')
        old_presentation = self.present([str(old_file)])
        old_presentation[0]['info']['parentID'] = 'old-turn'
        backend.messages = old_presentation + [{'info': {'role': 'assistant', 'parentID': 'old-turn'},
            'parts': [{'type': 'text', 'text': 'Old result'}]}]
        backend.messagesChanged.emit(backend.messages)
        backend.set_busy(True)
        self.assertEqual(surface.result_tabs.currentIndex(), 1)
        backend.message_id = 'new-turn'
        backend.messages.append({'info': {'role': 'assistant', 'parentID': 'new-turn'},
            'parts': [{'type': 'text', 'text': 'Partial answer'}]})
        backend.messagesChanged.emit(backend.messages); backend.set_busy(True)
        self.assertEqual(surface.result_tabs.currentIndex(), 1)
        surface.result_tabs.setCurrentIndex(0); backend.set_busy(True)
        self.assertEqual(surface.result_tabs.currentIndex(), 0)
        surface.result_tabs.setCurrentIndex(1)
        backend.messages[-1]['parts'][0]['text'] = 'Final answer'; backend.messagesChanged.emit(backend.messages)
        backend.set_busy(False); backend.completed.emit(True, 'Final answer')
        self.assertEqual(surface.result_tabs.currentIndex(), 0)
        self.assertTrue(surface.answer.isVisible()); self.assertFalse(surface.preview.isVisible())
        self.assertIn('Final answer', surface.answer.toPlainText()); self.assertIsNone(surface.choice.currentData())
        surface.result_tabs.setCurrentIndex(1); backend.messagesChanged.emit(backend.messages)
        self.assertEqual(surface.result_tabs.currentIndex(), 1)
        surface.close_pane(); backend.set_busy(True)
        self.assertFalse(surface.pane.isVisible())
        surface.toggle_preview()
        self.assertTrue(surface.pane.isVisible()); self.assertEqual(surface.result_tabs.currentIndex(), 1)
        backend.set_busy(False); backend.completed.emit(False, 'Abgebrochen')
        self.assertEqual(surface.result_tabs.currentIndex(), 1)
        backend.set_busy(True)
        file = Path(self.tmp) / 'ready.md'; file.write_text('Ready file')
        self.present([str(file)])
        backend.messages[0]['info']['parentID'] = backend.message_id
        backend.messages[0]['parts'].append({'type': 'text', 'text': 'Here is the ready file'})
        backend.messagesChanged.emit(backend.messages); backend.set_busy(True)
        self.assertEqual(surface.result_tabs.currentIndex(), 0)
        self.wait(lambda: 'Ready file' in surface.preview.text.toPlainText())
        backend.set_busy(False); backend.completed.emit(True, 'Here is the ready file')
        self.assertTrue(surface.preview.isVisible()); self.assertEqual(surface.choice.currentData(), str(file))
        backend.set_busy(True); surface.close_pane()
        backend.set_busy(False); backend.completed.emit(True, 'Ready while closed')
        self.assertFalse(surface.pane.isVisible())
        surface.toggle_preview(); self.assertEqual(surface.result_tabs.currentIndex(), 0)
        backend.set_busy(True); backend.set_busy(False); backend.completed.emit(True, '')
        self.assertEqual(surface.result_tabs.currentIndex(), 1)

    def test_execution_tab_streams_model_parts_and_preserves_reading_position(self):
        backend, surface = self.window.chat.backend, self.window.studio
        backend.session = 'stream-session'; backend.message_id = 'turn-one'; backend.set_busy(True)
        surface.result_tabs.setCurrentIndex(1)
        reasoning = {'type': 'reasoning', 'text': '**Prüfe Dateien**\n\n' + 'Schritt\n\n' * 80}
        tool = {'type': 'tool', 'tool': 'read', 'state': {'status': 'running', 'input': {'path': '/tmp/example'}}}
        backend.messages = [{'info': {'role': 'assistant', 'parentID': 'older'}, 'parts': [{'type': 'text', 'text': 'OLD ANSWER'}]},
            {'info': {'role': 'assistant', 'id': 'stream-answer', 'parentID': 'turn-one'}, 'parts': [reasoning, tool]}]
        backend.messagesChanged.emit(backend.messages); QTest.qWait(30)
        stream = surface.execution_detail
        self.assertIn('Prüfe Dateien', stream.toPlainText()); self.assertNotIn('**Prüfe', stream.toPlainText())
        self.assertNotIn('OLD ANSWER', stream.toPlainText()); self.assertIn('/tmp/example', stream.toPlainText())
        scroll = stream.verticalScrollBar(); self.assertGreater(scroll.maximum(), 0)
        self.assertEqual(scroll.value(), scroll.maximum())
        reasoning['text'] += 'Fortsetzung\n\n' * 20
        backend.messagesChanged.emit(backend.messages); QTest.qWait(30)
        self.assertIn('Fortsetzung', stream.toPlainText()); self.assertEqual(scroll.value(), scroll.maximum())
        scroll.setValue(60)
        tool['state'].update(status='completed', output='<img src="file:///private-test">\nTOOL OUTPUT')
        backend.messages[1]['parts'].append({'type': 'text', 'text': '**Final answer**'})
        backend.messagesChanged.emit(backend.messages); QTest.qWait(30)
        self.assertIn('TOOL OUTPUT', stream.toPlainText()); self.assertIn('<img src=', stream.toPlainText())
        self.assertIn('Final answer', stream.toPlainText()); self.assertAlmostEqual(scroll.value(), 60, delta=2)
        self.assertIn('Final answer', surface.answer.toPlainText())
        backend.message_id = 'turn-two'; backend.statusChanged.emit('Working')
        self.assertNotIn('Final answer', stream.toPlainText())
        backend.messages.append({'info': {'role': 'assistant', 'parentID': 'turn-two'},
            'parts': [{'type': 'tool', 'tool': 'read', 'state': {'status': 'error', 'error': 'PERMISSION DENIED'}}]})
        backend.messagesChanged.emit(backend.messages)
        self.assertIn('PERMISSION DENIED', stream.toPlainText())
        backend.set_busy(False); backend.message_id = ''
        backend.messagesChanged.emit(backend.messages)
        self.assertIn('PERMISSION DENIED', stream.toPlainText())
        backend.execution = 'server'; backend.statusChanged.emit('Server')
        self.assertNotIn('PERMISSION DENIED', stream.toPlainText()); self.assertIn('Server', stream.toPlainText())
        backend.execution = 'local'; backend.new_conversation()
        self.assertNotIn('PERMISSION DENIED', stream.toPlainText())

    def test_results_have_their_own_preview_selection_and_actions(self):
        from studio_saved_results import StudioSavedResults
        space = self.window.task_controller
        pending = space.store.create_task('Pending', directory=self.tmp, status='paused')
        done = space.store.create_task('Done', directory=self.tmp, status='completed')
        space.store.update_task(done, result='Saved output'); space.select_task(pending)
        self.window.show_page(10)
        self.assertEqual(self.launch.call_args.args, ('lumen-wissen', ['--section','results']))
        results = StudioSavedResults(space); results.refresh()
        results.setParent(self.window)
        self.assertEqual(results.preview.toPlainText(), 'Saved output')
        self.assertEqual(space.tasks.currentItem().data(Qt.UserRole), pending)
        with patch('task_controller.QFileDialog.getSaveFileName', return_value=(self.tmp+'/result.md', '')): results.export.click()
        self.assertEqual(Path(self.tmp+'/result.md').read_text(), 'Saved output')
        results.search.setText('missing'); self.assertFalse(results.export.isEnabled()); self.assertEqual(results.preview.toPlainText(), '')

    def test_detail_has_no_management_sidebar_at_either_size(self):
        for width in (760,1480):
            self.window.resize(width, 860); self.app.processEvents()
            self.assertIsNone(self.window.findChild(QPushButton, 'studioAccount'))
            self.assertEqual(self.window.pages.count(), 1)
            self.assertTrue(self.window.context_bar.isVisible())
            self.assertGreater(self.window.studio.width(), width-20)

    def test_compact_history_keeps_drafts_and_attachments_safe(self):
        chat = self.window.chat
        self.window.open_search(); controller = self.window.search_controller
        chat.backend.session = 'one'; chat.composer.setPlainText('Unsaved draft')
        with patch.object(chat.backend, 'select_session') as select:
            controller.select_session('two'); select.assert_not_called()
            self.assertEqual(chat.composer.toPlainText(), 'Unsaved draft')
            chat.composer.clear(); chat.paths = [self.tmp+'/attachment.txt']
            controller.select_session('two'); select.assert_not_called()
            self.assertEqual(chat.paths, [self.tmp+'/attachment.txt'])
            chat.paths = []; controller.select_session('two'); select.assert_called_once_with('two')

    def test_task_overview_search_controls_export_and_conversation(self):
        from plan_dialog import selected
        space, chat = self.window.task_controller, self.window.chat
        task = space.store.create_task('Küche', directory=self.tmp, roots=[self.tmp], approved=True,
            steps=[{'action': 'write', 'path': self.tmp + '/notiz.md', 'text': 'Erhaltenes Ergebnis'}])
        waiting = space.store.create_task('Rückfrage', directory=self.tmp, status='needs_input')
        space.refresh_tasks(); space.select_task(task); space.tasks_page.show()
        chat.backend.busy = True; chat.backend.busyChanged.emit(True)
        self.assertTrue(space.task_buttons['run'].isVisible())
        space.task_buttons['run'].click(); self.wait(lambda: not space.processes)
        chat.backend.busy = False; chat.backend.busyChanged.emit(False); space.refresh_tasks()
        self.assertFalse(space.task_buttons['pause'].isVisible())
        self.assertIn('notiz.md', space.task_result.toPlainText())
        result = space.store.task(task)['result']
        with patch('task_controller.QFileDialog.getSaveFileName', return_value=(self.tmp + '/export.md', '')):
            space.export_task()
        self.assertEqual(Path(self.tmp + '/export.md').read_text(), result)
        space.task_search.setText('Rückfrage'); self.assertEqual(selected(space.tasks), waiting)
        space.task_search.setText('nicht vorhanden'); self.assertIsNone(space.tasks.currentItem())
        self.assertTrue(space.tasks_empty.isVisible()); self.assertFalse(space.task_save.isEnabled())
        space.select_task(task); self.assertEqual(space.task_search.text(), '')
        self.assertEqual(space.task_result.toPlainText(), result)
        space.store.update_task(task, session='origin-session'); space.refresh_tasks()
        chat.composer.setPlainText('Mein Entwurf')
        with patch.object(chat.backend, 'select_session') as select, patch.object(chat.backend, 'send') as send:
            with self.assertRaises(ValueError): space.open_task_conversation()
            self.assertEqual(chat.composer.toPlainText(), 'Mein Entwurf'); select.assert_not_called()
            chat.composer.clear(); space.open_task_conversation()
            select.assert_called_once_with('origin-session'); send.assert_not_called()
        space.select_task(task); space.close_task.click()
        self.assertEqual(space.store.task(task)['result'], result)
        self.assertFalse(any(space.tasks.item(i).data(Qt.UserRole) == task for i in range(space.tasks.count())))

    def test_pause_uses_tracker_and_is_not_offered_as_server_cancel(self):
        chat, space = self.window.chat, self.window.task_controller
        chat.backend.busy = True
        chat.tracker.started('Ein Auftrag', [], 'build')
        task = chat.tracker.task_id
        space.select_task(task); space.tasks_page.show()
        self.assertTrue(space.task_buttons['pause'].isVisible())
        self.window.show_page(0); self.assertTrue(chat.pause_task.isVisible())
        chat.open_task.click(); self.assertEqual(self.launch.call_args.args, ('lumen-system', ['--task', task]))
        with patch.object(chat.backend, 'stop', side_effect=lambda: chat.backend.completed.emit(False, 'Abgebrochen')) as stop:
            space.task_buttons['pause'].click(); stop.assert_called_once()
        self.assertEqual(space.store.task(task)['status'], 'paused')
        chat.backend.busy = False; chat.backend.busyChanged.emit(False)
        with patch.object(chat.tracker, 'resume') as resume:
            space.task_buttons['run'].click(); resume.assert_called_once_with(task, chat)
        space.store.update_task(task, status='running'); chat.backend.busy = True; chat.backend.execution = 'server'
        space.refresh_tasks(); space.tasks_page.show()
        self.assertFalse(space.task_buttons['pause'].isVisible()); self.assertTrue(space.task_buttons['cancel'].isVisible())
        with patch.object(chat.backend, 'stop') as stop:
            with self.assertRaises(ValueError): space.stop_task('paused')
            stop.assert_not_called()
        chat.backend.execution = 'local'; chat.backend.busy = False

    def test_result_actions_follow_answer_identity_not_last_tracked_task(self):
        chat, space, surface = self.window.chat, self.window.task_controller, self.window.studio
        def answer(session, text, turn='turn'):
            chat.backend.session = session
            chat.show_messages([{'info': {'role': 'assistant', 'id': 'answer', 'parentID': turn}, 'parts': [{'type': 'text', 'text': text}]}])
        first = space.store.create_task('Erstes Ergebnis', directory=self.tmp, status='completed')
        second = space.store.create_task('Zweites Ergebnis', directory=self.tmp, status='completed')
        space.store.update_task(first, session='one', result='Antwort eins')
        space.store.update_task(second, session='two', result='Antwort zwei')
        space.store.event(first, 'conversation_turn', json.dumps(['one', 'turn']))
        space.store.event(second, 'conversation_turn', json.dumps(['two', 'turn']))
        chat.tracker.task_id = second; space.select_task(second)
        answer('one', 'Antwort eins')
        self.assertEqual(chat.answer_task()['id'], first)
        with patch('file_actions.save_action') as save:
            chat.save_as_file_action(); self.assertEqual(save.call_args.args[2]['id'], first)
        with patch('task_controller.QFileDialog.getSaveFileName', return_value=(self.tmp + '/antwort.md', '')):
            surface.export_answer.trigger()
        self.assertEqual(Path(self.tmp + '/antwort.md').read_text(), 'Antwort eins')
        surface.task_link.click(); self.assertEqual(self.launch.call_args.args, ('lumen-system', ['--task',first]))
        answer('two', 'Noch nicht gespeichert', 'new-turn')
        self.assertIsNone(chat.answer_task()); self.assertFalse(surface.export_answer.isEnabled())
        with patch('file_actions.save_action') as save:
            chat.save_as_file_action(); save.assert_not_called()

    def test_multi_message_turn_binding_and_right_hand_memory_selection(self):
        from PySide6.QtGui import QTextCursor
        chat, surface = self.window.chat, self.window.studio
        chat.backend.session = 'same-session'; chat.backend.message_id = 'turn-one'
        chat.tracker.started('Prüfen', [], 'build')
        first = chat.tracker.task_id
        history = [{'info': {'role': 'assistant', 'id': key, 'parentID': 'turn-one'},
                    'parts': [{'type': 'text', 'text': text}]} for key, text in [('a1', 'Ich prüfe …'), ('a2', 'Fertig')]]
        chat.backend.messages = history; chat.show_messages(history)
        chat.tracker.finished(True, 'Ich prüfe …\n\nFertig')
        self.assertEqual(chat.answer_task()['id'], first)
        chat.backend.message_id = 'turn-two'; chat.tracker.started('Anderer Auftrag', [], 'build')
        chat.tracker.finished(True, 'Ich prüfe …\n\nFertig')
        self.assertEqual(chat.answer_task()['id'], first)
        # Both turns have identical text; only the recorded identity selects the first.
        left = chat.transcript.rows[0][2].findChildren(__import__('answer_widget').AnswerText)[0]
        cursor = left.textCursor(); cursor.select(QTextCursor.Document); left.setTextCursor(cursor)
        with patch.object(chat, 'capture_knowledge') as capture:
            surface.result_menu.actions()[1].trigger()
            capture.assert_called_once_with(True, text='Fertig')
        cursor = surface.answer.textCursor(); cursor.setPosition(0); cursor.setPosition(3, QTextCursor.KeepAnchor); surface.answer.setTextCursor(cursor)
        with patch.object(chat, 'capture_knowledge') as capture:
            surface.result_menu.actions()[0].trigger()
            capture.assert_called_once_with(False, text='Fer')
        saved = chat.recovery_state()
        chat.restore_recovery(saved)
        self.assertEqual(chat.answer_task()['id'], first)


if __name__ == '__main__': unittest.main()
