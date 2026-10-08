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
        self.assertEqual(set(self.window.nav_buttons), {0,4,8,10})

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
        chat, space, surface = self.window.chat, self.window.workspace, self.window.studio
        chat.mode.setCurrentIndex(chat.mode.findData('build'))
        chat.dont_ask.setChecked(True); self.assertIn('Automatische', chat.mode_hint.text())
        chat.dont_ask.setChecked(False); self.assertEqual(chat.mode_hint.text(), 'Mit Freigaben')
        chat.mode.setCurrentIndex(chat.mode.findData('plan')); self.assertEqual(chat.mode_hint.text(), 'Nur lesen')
        for theme in ('graphite', 'atelier', 'midnight', 'glass'):
            apply_design(self.app, theme); QTest.qWait(30)
            for widget in (chat, surface, self.window.navigation, space.tasks_page):
                self.assertEqual(widget.palette().color(QPalette.Window), self.app.palette().color(QPalette.Window))
        surface.result_tabs.setCurrentIndex(1); self.assertTrue(surface.execution_detail.isVisible())
        surface.result_tabs.setCurrentIndex(0); self.assertTrue(surface.answer.isVisible())
    def test_results_have_their_own_preview_selection_and_actions(self):
        space = self.window.workspace
        pending = space.store.create_task('Pending', directory=self.tmp, status='paused')
        done = space.store.create_task('Done', directory=self.tmp, status='completed')
        space.store.update_task(done, result='Saved output')
        space.select_task(pending)
        self.window.navigation.show_results(); self.assertTrue(self.window.navigation.results.isChecked())
        self.assertFalse(self.window.navigation.buttons[4].isChecked())
        self.assertNotEqual(self.window.pages.currentWidget(), space.tasks_page)
        results = self.window.results_page
        self.assertEqual(results.preview.toPlainText(), 'Saved output')
        self.assertEqual(space.tasks.currentItem().data(Qt.UserRole), pending)
        with patch('lumen_workspace.QFileDialog.getSaveFileName', return_value=(self.tmp+'/result.md', '')):
            results.export.click()
        self.assertEqual(Path(self.tmp+'/result.md').read_text(), 'Saved output')
        results.search.setText('missing'); self.assertFalse(results.export.isEnabled()); self.assertEqual(results.preview.toPlainText(), '')
        self.window.navigation.navigate(4); self.assertTrue(self.window.navigation.buttons[4].isChecked())
        self.assertFalse(self.window.navigation.results.isChecked())
        self.window.resize(760,600); QTest.qWait(50)
        self.assertEqual(self.window.size().toTuple(), (760,600))
        self.assertTrue(space.task_buttons['run'].isVisible())
        self.assertLess(space.task_inspector.width(), 342)

    def test_conversation_sidebar_keeps_history_visible_and_drafts_safe(self):
        chat, navigation = self.window.chat, self.window.navigation
        chat.backend.sessionsChanged.emit([{'id':'one','title':'First'}, {'id':'two','title':'Second'}])
        chat.backend.session = 'one'; chat.backend.sessionChanged.emit('one')
        self.assertTrue(navigation.recent.isVisible()); self.assertTrue(navigation.create.isVisible())
        width = navigation.width()
        self.window.show_page(4); self.window.show_page(0)
        self.assertEqual(navigation.width(), width); self.assertTrue(navigation.recent.isVisible())
        chat.composer.setPlainText('Unsaved draft')
        with patch.object(chat.backend, 'select_session') as select:
            QTest.mouseClick(navigation.recent.viewport(), Qt.LeftButton, pos=navigation.recent.visualItemRect(navigation.recent.item(1)).center())
            select.assert_not_called()
            self.assertEqual(navigation.recent.currentItem().data(Qt.UserRole), 'one')
        self.assertEqual(chat.composer.toPlainText(), 'Unsaved draft')
        chat.composer.clear()
        with patch.object(chat.backend, 'select_session') as select:
            navigation.open_session(navigation.recent.item(1)); select.assert_called_once_with('two')

    def test_task_overview_search_controls_export_and_conversation(self):
        from lumen_workspace import selected
        space, chat = self.window.workspace, self.window.chat
        task = space.store.create_task('Küche', directory=self.tmp, roots=[self.tmp], approved=True,
            steps=[{'action': 'write', 'path': self.tmp + '/notiz.md', 'text': 'Erhaltenes Ergebnis'}])
        waiting = space.store.create_task('Rückfrage', directory=self.tmp, status='needs_input')
        space.refresh_tasks(); space.select_task(task); self.window.show_page(4)
        chat.backend.busy = True; chat.backend.busyChanged.emit(True)
        self.assertTrue(space.task_buttons['run'].isVisible())
        space.task_buttons['run'].click(); self.wait(lambda: not space.processes)
        chat.backend.busy = False; chat.backend.busyChanged.emit(False); space.refresh_tasks()
        self.assertFalse(space.task_buttons['pause'].isVisible())
        self.assertIn('notiz.md', space.task_result.toPlainText())
        result = space.store.task(task)['result']
        with patch('lumen_workspace.QFileDialog.getSaveFileName', return_value=(self.tmp + '/export.md', '')):
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
        chat, space = self.window.chat, self.window.workspace
        chat.backend.busy = True
        chat.tracker.started('Ein Auftrag', [], 'build')
        task = chat.tracker.task_id
        space.select_task(task); self.window.show_page(4)
        self.assertTrue(space.task_buttons['pause'].isVisible())
        self.window.show_page(0); self.assertTrue(chat.pause_task.isVisible())
        chat.open_task.click(); self.assertEqual(self.window.pages.currentIndex(), 4)
        with patch.object(chat.backend, 'stop', side_effect=lambda: chat.backend.completed.emit(False, 'Abgebrochen')) as stop:
            space.task_buttons['pause'].click(); stop.assert_called_once()
        self.assertEqual(space.store.task(task)['status'], 'paused')
        chat.backend.busy = False; chat.backend.busyChanged.emit(False)
        with patch.object(chat.tracker, 'resume') as resume:
            space.task_buttons['run'].click(); resume.assert_called_once_with(task, chat)
        space.store.update_task(task, status='running'); chat.backend.busy = True; chat.backend.execution = 'server'
        space.refresh_tasks(); self.window.show_page(4)
        self.assertFalse(space.task_buttons['pause'].isVisible()); self.assertTrue(space.task_buttons['cancel'].isVisible())
        with patch.object(chat.backend, 'stop') as stop:
            with self.assertRaises(ValueError): space.stop_task('paused')
            stop.assert_not_called()
        chat.backend.execution = 'local'; chat.backend.busy = False

    def test_result_actions_follow_answer_identity_not_last_tracked_task(self):
        chat, space, surface = self.window.chat, self.window.workspace, self.window.studio
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
        with patch('lumen_workspace.QFileDialog.getSaveFileName', return_value=(self.tmp + '/antwort.md', '')):
            surface.export_answer.trigger()
        self.assertEqual(Path(self.tmp + '/antwort.md').read_text(), 'Antwort eins')
        surface.task_link.click(); self.assertEqual(space.tasks.currentItem().data(Qt.UserRole), first)
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
