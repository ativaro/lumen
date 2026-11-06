"""Conversation-focused details keep steps separate and files explicitly reachable."""
from pathlib import Path
import os
import unittest
from unittest.mock import patch
from PySide6.QtTest import QTest
from lumen_i18n import tr, language
import test_studio


class ConversationFocusTest(unittest.TestCase):
    conversation_focus = True
    setUpClass = classmethod(test_studio.StudioTest.setUpClass.__func__)
    setUp = test_studio.StudioTest.setUp
    tearDown = test_studio.StudioTest.tearDown
    wait = test_studio.StudioTest.wait
    present = test_studio.StudioTest.present

    def test_only_steps_on_right_and_conversation_keeps_priority(self):
        chat, surface = self.window.chat, self.window.studio
        self.assertTrue(surface.conversation_focus)
        self.assertEqual(surface.heading.text(), tr('Arbeitsschritte'))
        self.assertTrue(surface.result_tabs.isHidden())
        self.assertEqual(surface.result_pages.count(), 1)
        self.assertTrue(surface.execution_detail.isVisible())
        self.assertFalse(surface.answer.isVisible())
        self.assertGreater(chat.width(), surface.pane.width()*2)
        self.assertEqual(chat.preview_button.accessibleName(), tr('Arbeitsschritte anzeigen'))
        self.assertTrue(surface.save_answer.isVisible())
        self.assertFalse(surface.pane.isAncestorOf(surface.save_answer))
        backend=chat.backend; backend.session='focused'; backend.message_id='turn'
        backend.messages=[dict(info=dict(role='assistant',parentID='turn'),parts=[
            dict(type='reasoning',text='Inspect the source'),
            dict(type='tool',tool='read',state=dict(status='completed',title='Source checked')),
            dict(type='text',text='Final answer only in the conversation')])]
        backend.messagesChanged.emit(backend.messages); QTest.qWait(20)
        self.assertIn('Final answer only', chat.transcript.toPlainText())
        self.assertNotIn('Final answer only', surface.execution_detail.toPlainText())
        self.assertIn('Inspect the source', surface.execution_detail.toPlainText())
        self.assertIn('Source checked', surface.execution_detail.toPlainText())
        if output := os.environ.get('LUMEN_DETAIL_SCREENSHOTS'):
            output=Path(output); output.mkdir(parents=True,exist_ok=True)
            self.window.grab().save(str(output/('detail-steps-'+language()+'.png')))
        backend.set_busy(True); backend.set_busy(False); backend.completed.emit(True,chat.last_answer)
        self.assertTrue(surface.execution_detail.isVisible()); self.assertFalse(surface.answer.isVisible())
        surface.copy_answer.click(); self.assertEqual(self.app.clipboard().text(),chat.last_answer)
        with patch.object(chat,'capture_knowledge') as save:
            surface.result_menu.actions()[0].trigger()
            self.assertEqual(save.call_args.kwargs['text'],chat.last_answer)
        surface.close_preview.click(); self.assertFalse(surface.pane.isVisible())
        backend.set_busy(True); backend.set_busy(False)
        self.assertFalse(surface.pane.isVisible())
        for width in (760,1100,1480):
            self.window.resize(width,800); QTest.qWait(20)
            self.assertTrue(chat.isVisible()); self.assertFalse(surface.pane.isVisible())
        chat.preview_button.click(); self.assertTrue(surface.pane.isVisible())
        self.assertTrue(chat.isVisible())
        backend.execution='server'; surface.update_execution()
        self.assertIn(tr('Der Server stellt hier keinen Live-Modellverlauf bereit.'),surface.execution_detail.toPlainText())

    def test_explicit_files_stay_available_without_replacing_steps(self):
        surface=self.window.studio; path=Path(self.tmp)/'result.txt'; path.write_text('File contents')
        self.window.chat.composer.setPlainText('Keep draft')
        self.present([str(path)])
        self.assertTrue(surface.files_button.isVisible())
        self.assertFalse(surface.file_dialog.isVisible())
        self.assertTrue(surface.execution_detail.isVisible())
        surface.files_button.click()
        self.wait(lambda: surface.preview.proc is None and 'File contents' in surface.preview.text.toPlainText())
        self.assertTrue(surface.file_dialog.isVisible()); self.assertTrue(surface.preview.isVisible())
        surface.file_dialog.reject(); self.assertIsNone(surface.preview.proc)
        self.assertEqual(self.window.chat.composer.toPlainText(),'Keep draft')
        surface.files_button.click(); self.window.close()
        self.assertFalse(surface.file_dialog.isVisible())
        self.present([]); self.assertFalse(surface.files_button.isVisible())

    def test_save_icon_uses_actual_text_color_after_theme_changes(self):
        from PySide6.QtGui import QIcon, QPalette
        from appearance import apply_design
        from test_button_icons import ButtonIconTest
        action = self.window.studio.save_answer
        self.window.chat.composer.setPlainText('Keep draft through theme changes')
        for theme in ('graphite', 'glass', 'atelier', 'midnight'):
            apply_design(self.app, theme)
            for enabled in (True, False):
                action.setEnabled(enabled); action.ensurePolished(); self.app.processEvents()
                group = QPalette.Active if enabled else QPalette.Disabled
                expected = action.palette().color(group, QPalette.ButtonText).getRgb()[:3]
                colors = ButtonIconTest.colors(self, action.icon(), QIcon.Normal if enabled else QIcon.Disabled)
                self.assertTrue(all(max(abs(a-b) for a,b in zip(color, expected)) <= 1 for color in colors), (theme, enabled))
            self.assertEqual(self.window.chat.composer.toPlainText(), 'Keep draft through theme changes')


if __name__ == '__main__': unittest.main()
