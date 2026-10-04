"""Synthetic preview behavior and the hard boundary against real credential input."""
import unittest
from unittest.mock import patch
from PySide6.QtCore import QObject, QPointF, Qt, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from vault_preview import VaultPreview, create_window


class VaultPreviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QGuiApplication.instance() or QGuiApplication([])
    def setUp(self): self.controller = VaultPreview()
    def tearDown(self):
        self.controller.lock(); self.controller.theme_timer.stop(); self.controller.deleteLater()
        self.app.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_starts_locked_and_has_no_secret_input_or_persistence_api(self):
        c = self.controller
        self.assertTrue(c.locked); self.assertEqual(c.entries,[]); self.assertEqual(c.detail,{})
        for method in ('save','import_file','set_password','unlock','copy_password','create'):
            self.assertFalse(hasattr(c,method),method)
        c.filter('private text'); c.reveal(); c.select('mail')
        self.assertEqual(c.query,''); self.assertEqual(c.entries,[])

    def test_filter_favorites_trash_and_restore_are_only_in_memory(self):
        c = self.controller; c.show_demo()
        self.assertEqual(len(c.entries),6)
        self.assertNotIn('secret',c.entries[0]); self.assertNotIn('DEMO-',c.detail['secret'])
        c.choose_category('favorites'); self.assertEqual(len(c.entries),3)
        c.favorite(); self.assertEqual(len(c.entries),2)
        c.choose_category('all'); c.filter('nas'); self.assertEqual([r['id'] for r in c.entries],['nas'])
        c.trash(); self.assertEqual(c.entries,[])
        c.choose_category('trash'); self.assertEqual(c.entries[0]['id'],'nas')
        c.trash(); self.assertEqual(c.entries,[])
        c.lock(); self.assertEqual(c.rows,[]); self.assertEqual(c.detail,{})
        c.show_demo(); self.assertEqual(len(c.entries),6)
        self.assertTrue(c.detail['favorite'])

    def test_reveal_expires_and_is_reset_on_selection_and_lock(self):
        c = self.controller; c.show_demo(); c.hide_timer.setInterval(20); c.reveal()
        self.assertTrue(c.detail['revealed']); QTest.qWait(50); self.assertFalse(c.detail['revealed'])
        c.reveal(); c.select('api'); self.assertFalse(c.detail['revealed'])
        c.reveal(); c.screen_locked(True); self.assertTrue(c.locked); self.assertEqual(c.detail,{})
        c.show_demo(); c.lock_timer.setInterval(20); c.lock_timer.start(); QTest.qWait(50)
        self.assertTrue(c.locked)

    def test_copy_edit_new_do_not_touch_clipboard_or_files(self):
        c = self.controller; c.show_demo()
        self.app.clipboard().setText('unrelated clipboard')
        for action in ('copy','new','edit','access','collection'): c.explain(action); self.assertTrue(c.status)
        self.assertEqual(self.app.clipboard().text(),'unrelated clipboard')
        self.assertEqual(len(c.entries),6)

    def test_mcp_reports_unavailable_without_opening_library(self):
        from lumen_mcp_tools import invoke
        with patch('tools_data.Library',side_effect=AssertionError('Must not open a library')):
            result=invoke('lumen_vault_secrets_status',{})
        self.assertEqual(result,dict(available=False,stage='design_preview',real_secrets_supported=False,
                                   engine_qualified=False,independent_review_completed=False))

    def test_application_starts_with_a_real_session_bus(self):
        import os, shutil, subprocess, sys
        from pathlib import Path
        if not shutil.which('dbus-run-session'): self.skipTest('dbus-run-session unavailable')
        source = """
from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
import vault_preview
original = vault_preview.create_window
def create(controller):
    result = original(controller)
    QTimer.singleShot(50, QGuiApplication.instance().quit)
    return result
vault_preview.create_window = create
raise SystemExit(vault_preview.main())
"""
        env=dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONPATH=str(Path(__file__).resolve().parent))
        result=subprocess.run(['dbus-run-session','--',sys.executable,'-c',source],env=env,
                              capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_launcher_routes_preview_separately_and_preserves_backup_arguments(self):
        import json, shutil, subprocess, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'bin').mkdir(); (root/'files').mkdir()
            launcher=root/'bin/lumen-vault'
            shutil.copy2(Path(__file__).resolve().parents[1]/'bin/lumen-vault',launcher)
            python=root/'bin/lumen-python'
            python.write_text('#!/usr/bin/python3\nimport sys,json\nprint(json.dumps(sys.argv[1:]))\n')
            python.chmod(0o755)
            for name in ('tools_app.py','vault_preview.py'): (root/'files'/name).touch()
            preview=json.loads(subprocess.check_output([str(launcher),'--preview'],text=True))
            self.assertEqual(Path(preview[0]).name,'vault_preview.py'); self.assertEqual(len(preview),1)
            backup=json.loads(subprocess.check_output([str(launcher),'--handoff','reference'],text=True))
            self.assertEqual(Path(backup[0]).name,'tools_app.py')
            self.assertEqual(backup[1:],['vault','--handoff','reference'])

    def test_actual_qml_buttons_and_loader_destroy_models_on_lock(self):
        c=self.controller; engine,w=create_window(c); w.show(); QTest.qWait(60)
        try:
            button=w.findChild(QObject,'showDemo'); self.assertIsNotNone(button)
            center=button.mapToScene(QPointF(button.property('width')/2,button.property('height')/2)).toPoint()
            QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,center);QTest.qWait(50)
            self.assertFalse(c.locked)
            search=w.findChild(QObject,'vaultDemoSearch'); self.assertIsNotNone(search)
            search.setProperty('text','API'); QTest.qWait(30)
            self.assertEqual([r['id'] for r in c.entries],['api'])
            lock=w.findChild(QObject,'lockPreview')
            center=lock.mapToScene(QPointF(lock.property('width')/2,lock.property('height')/2)).toPoint()
            QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,center);QTest.qWait(50)
            self.assertTrue(c.locked); self.assertEqual(c.detail,{})
            self.assertIsNone(w.findChild(QObject,'vaultDemoSearch'))
            self.assertIsNone(w.findChild(QObject,'vaultDemoEntries'))
        finally:
            w.close(); engine.deleteLater(); self.app.sendPostedEvents(None,QEvent.DeferredDelete)


if __name__=='__main__':unittest.main()
