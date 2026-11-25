"""Boundary checks; all images, windows and engine replies are synthetic."""
import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QBuffer, QIODevice, QSettings, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from screen_companion import Companion, FrameGate
from screen_capture import capture, accessibility_state
from assistant_backend import OpenCodeBackend


class CompanionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.root = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, LUMEN_DATA=self.root, XDG_RUNTIME_DIR=self.root))
        self.image = QImage(320,200,QImage.Format_RGB32); self.image.fill(Qt.white)
        buffer=QBuffer(); buffer.open(QIODevice.WriteOnly); self.image.save(buffer,'PNG')
        self.png=bytes(buffer.data()); self.data=dict(protection='clear',png=base64.b64encode(self.png).decode())

    def guide(self):
        guide=Companion(); self.addCleanup(guide.close)
        guide.target=dict(uuid='{00000000-0000-0000-0000-000000000001}',pid=123,app='test',caption='test')
        guide.active=True; guide.show(); self.app.processEvents()
        return guide

    def test_embedded_history_keeps_readonly_session_and_clears_window_on_leave(self):
        from PySide6.QtWidgets import QWidget
        from unittest.mock import Mock
        parent = QWidget(); self.addCleanup(parent.close); leave = Mock()
        guide = Companion(parent, leave=leave); self.addCleanup(guide.close)
        guide.backend.session = 'private-window-help'
        guide.backend.messages = [dict(info=dict(role=role, id=str(i)), parts=[dict(type='text', text=text)])
                                  for i, (role, text) in enumerate([('user','First question'),('assistant','First answer'),('user','Next question'),('assistant','Next answer')])]
        guide.history.setChecked(True)
        self.assertIn('First answer', guide.answer.toPlainText())
        self.assertIn('Next answer', guide.answer.toPlainText())
        guide.active=True; guide.png=self.png; guide.image=self.image
        guide.leave_help(); leave.assert_called_once()
        self.assertFalse(guide.png); self.assertFalse(guide.active)
        self.assertEqual(guide.backend.session, 'private-window-help')
        self.assertTrue(guide.backend.read_only); self.assertTrue(guide.backend.screen_guidance)
        self.assertFalse(guide.closing)

    def test_review_then_send_once_and_pause_clears_sensitive_state(self):
        guide=self.guide(); guide.pending='Help with setup'
        with patch.object(guide.backend,'send') as send:
            guide.captured(self.data,False)
            self.assertTrue(guide.approve.isVisible()); send.assert_not_called()
            guide.send_image(); send.assert_called_once_with('Help with setup',screen_image=self.png,context_data={'goal': ''})
            self.assertFalse(guide.png); guide.send_image(); self.assertEqual(send.call_count,1)
            guide.pause(); guide.captured(self.data,True)
            self.assertFalse(guide.active); self.assertFalse(guide.png); self.assertTrue(guide.image.isNull())
            self.assertFalse(guide.reviewed); self.assertFalse(guide.timer.isActive())

    def test_auto_unknown_password_limit_and_enter(self):
        guide=self.guide(); guide.reviewed=True; guide.auto.setChecked(True)
        with patch.object(guide.backend,'send') as send:
            guide.captured(dict(protection='unknown'),True)
            self.assertFalse(guide.active); self.assertFalse(guide.auto.isChecked()); send.assert_not_called()
            guide.active=True; guide.captured(dict(protection='password'),False)
            self.assertFalse(guide.active); self.assertFalse(guide.png); send.assert_not_called()
        guide.active=True; guide.reviewed=True; guide.auto.setChecked(True); guide.turns=30
        with patch.object(guide,'run_worker') as worker:
            guide.observe(); worker.assert_not_called(); self.assertFalse(guide.active)
            guide.composer.setPlainText('A goal')
            QTest.keyClick(guide.composer,Qt.Key_Return,Qt.ShiftModifier)
            self.assertIn('\n',guide.composer.toPlainText()); worker.assert_not_called()
            QTest.keyClick(guide.composer,Qt.Key_Return)
            self.assertEqual(worker.call_args.args[0],'capture')

    def test_typed_turn_interrupts_active_voice_before_capturing(self):
        guide=self.guide(); guide.voice.active=True; guide.voice.state='listening'
        with patch.object(guide.voice,'cancel_process') as cancel, patch.object(guide,'run_worker') as worker:
            guide.submit('Next question'); cancel.assert_called_once()
            self.assertEqual(guide.voice.state,'thinking'); worker.assert_called_once()
        guide.voice.active=False

    def test_password_and_unknown_are_checked_before_capture(self):
        target=dict(uuid='fixed-window',pid=123,app='test',caption='test')
        with patch('screen_capture.window_info',return_value=target), patch('screen_capture.accessibility_state',return_value='password'), patch('screen_capture.subprocess.run') as run:
            self.assertEqual(capture(None,target),dict(protection='password')); run.assert_not_called()
        with patch('screen_capture.window_info',return_value=target), patch('screen_capture.accessibility_state',return_value='unknown'), patch('screen_capture.subprocess.run') as run:
            self.assertEqual(capture(None,target,True),dict(protection='unknown')); run.assert_not_called()

    def test_capture_callbacks_after_pause_cannot_send(self):
        guide=self.guide(); guide.auto.setChecked(True); guide.reviewed=True
        guide.pending='Help'; guide.pause()
        with patch.object(guide.backend,'send') as send:
            guide.captured(self.data,False); guide.completed(True,'Late answer')
            send.assert_not_called(); self.assertFalse(guide.png)
            self.assertFalse(guide.approve.isVisible()); self.assertFalse(guide.timer.isActive())

    def test_accessibility_uses_roles_not_language_or_field_contents(self):
        import gi
        gi.require_version('Atspi','2.0')
        from gi.repository import Atspi
        from unittest.mock import Mock
        def node(role, children=()):
            item=Mock(); item.get_child_count.return_value=len(children)
            item.get_child_at_index.side_effect=lambda i: children[i]
            item.get_state_set.return_value.contains.side_effect=lambda state: state == Atspi.StateType.SHOWING
            item.get_role.return_value=role
            return item
        field=node(Atspi.Role.TEXT); window=node(Atspi.Role.FRAME,[field])
        window.get_name.return_value='設定'; app=node(Atspi.Role.APPLICATION,[window]); app.get_process_id.return_value=123
        desktop=node(Atspi.Role.DESKTOP_FRAME,[app])
        with patch.object(Atspi,'get_desktop',return_value=desktop), patch.object(Atspi,'set_timeout'):
            target=dict(pid=123,caption='設定')
            self.assertEqual(accessibility_state(target),'clear')
            field.get_role.return_value=Atspi.Role.PASSWORD_TEXT
            self.assertEqual(accessibility_state(target),'password')
            self.assertEqual(accessibility_state(dict(pid=999,caption='設定')),'unknown')
            field.get_text.assert_not_called()

    def test_frame_stability_and_small_noise(self):
        gate=FrameGate(); gate.mark(self.image)
        self.assertFalse(gate.changed(self.image))
        changed=self.image.copy(); changed.fill(Qt.black)
        self.assertFalse(gate.changed(changed)); self.assertTrue(gate.changed(changed))
        gate.mark(changed); self.assertFalse(gate.changed(changed))
        changed.setPixelColor(0,0,Qt.white); self.assertFalse(gate.changed(changed))

    def test_guidance_denies_tools_and_skips_memory_even_with_auto_approval(self):
        backend=OpenCodeBackend(self.root); self.addCleanup(backend.shutdown)
        backend.settings=QSettings(self.root+'/settings.ini',QSettings.IniFormat)
        backend.settings.setValue('model','test/vision'); backend.screen_guidance=True; backend.auto_approve=True
        turns=[]; asks=[]; started=[]; backend.started.connect(lambda *args:started.append(args))
        # The service denies the session every tool and writes the companion's system text
        # (native/service: each_mode_has_its_system_text_and_tools, the_window_image_and_selection_are_checked_data).
        # The service prepares no memory for the companion (native/service/src/turn.rs, `recall`).
        with patch.object(backend,'begin',side_effect=turns.append), patch.object(backend,'ask',side_effect=lambda op,*a,**k:asks.append(op)):
            backend.send('Help me',screen_image=self.png)
            turn=turns[-1]
            self.assertTrue(turn['screen_guidance']); self.assertFalse(turn['memory_context'])
            self.assertEqual(base64.b64decode(turn['screen_image']),self.png)
            self.assertFalse(started)
            backend.permissions=[dict(id='permission',permission='bash')]; backend.publish_requests()
            self.assertEqual(asks,[])

if __name__=='__main__': unittest.main()
