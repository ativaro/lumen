"""Real QWidget/QML paste paths with synthetic clipboard data and no AI calls."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ClipboardImagesTest(unittest.TestCase):
    def test_native_and_search_paste_and_submission(self):
        program=Path(os.environ.get('LUMEN_TEST_PROGRAM',str(Path(__file__).resolve().parents[1]/'agent-app/main.py')))
        with tempfile.TemporaryDirectory() as tmp:
            env=dict(os.environ,HOME=tmp,XDG_CONFIG_HOME=tmp+'/config',XDG_CACHE_HOME=tmp+'/cache',
                XDG_DATA_HOME=tmp+'/data',LUMEN_DATA=tmp+'/state',LUMEN_TOOLS_DATA=tmp+'/tools',
                LUMEN_LANGUAGE='de',QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software',
                LUMEN_OPENCODE_BIN='/nonexistent/test-engine')
            result=subprocess.run([sys.executable,'-c',PROBE,str(program),tmp],env=env,
                capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_password_manager_hint_blocks_clipboard_and_ai_editor_paste(self):
        from PySide6.QtCore import QMimeData
        from PySide6.QtGui import QClipboard
        from PySide6.QtWidgets import QApplication
        from clipboard_image import protected_clipboard
        from private_input import AssistantInput
        app=QApplication.instance() or QApplication([])
        secret=QMimeData();secret.setText('SYNTHETIC SECRET');secret.setData('x-kde-passwordManagerHint',b'secret')
        public=QMimeData();public.setText('public note')
        class Clipboard:
            def __init__(self,mime):self.mime=mime
            def mimeData(self,mode=QClipboard.Mode.Clipboard):return self.mime if mode==QClipboard.Mode.Clipboard else None
        self.assertTrue(protected_clipboard(Clipboard(secret)))
        self.assertFalse(protected_clipboard(Clipboard(public)))
        self.assertFalse(protected_clipboard(Clipboard(secret),QClipboard.Mode.Selection))
        editor=AssistantInput();editor.insertFromMimeData(secret);self.assertEqual(editor.toPlainText(),'')
        editor.insertFromMimeData(public);self.assertEqual(editor.toPlainText(),'public note')
        editor.close()


PROBE=r'''
import importlib.util,os,sys
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QMimeData,QBuffer,QIODevice
from PySide6.QtGui import QImage,QColor
from PySide6.QtTest import QTest
from PySide6.QtQuickControls2 import QQuickStyle
program,root=sys.argv[1:];QQuickStyle.setStyle('Basic')
spec=importlib.util.spec_from_file_location('desktop',program);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
app=d.create_app()
with patch('desktop_backend.DesktopBackend.refresh_sessions'):
 w=d.LumenWindow(root);w.show();p=w.chat;editor=p.composer;editor.setFocus();QTest.qWait(30)
 try:
  image=QImage(80,60,QImage.Format_ARGB32);image.fill(QColor('red'))
  def clip(secret=False,text=False):
   mime=QMimeData();mime.setImageData(image)
   if text:mime.setText('Image fallback must not be pasted')
   if secret:mime.setData('x-kde-passwordManagerHint',b'secret')
   app.clipboard().setMimeData(mime)
  with patch.object(p.backend,'send',return_value=True) as send,patch.object(p.backend,'preflight',return_value=True):
   editor.setPlainText('Keep draft');clip(text=True)
   QTest.keyClick(editor,Qt.Key_V,Qt.ControlModifier)
   assert len(p.paths)==1 and editor.toPlainText()=='Keep draft'
   path=Path(p.paths[0]);assert path.is_file()
   assert QImage(str(path)).pixelColor(0,0)==QColor('red')
   assert path.stat().st_mode&0o777==0o600
   assert path.parent.stat().st_mode&0o777==0o700
   send.assert_not_called()
   assert editor.canInsertFromMimeData(app.clipboard().mimeData())
   p.context_tools.clipboard();assert p.paths==[str(path)],'duplicate clipboard image'
   clip(secret=True);assert not editor.canInsertFromMimeData(app.clipboard().mimeData());p.context_tools.clipboard();editor.paste()
   assert p.paths==[str(path)] and editor.toPlainText()=='Keep draft'
   image.fill(QColor('blue'));clip();p.backend.busy=True;editor.paste();assert len(p.paths)==1;p.backend.busy=False
   # Text paste remains ordinary cursor insertion.
   app.clipboard().setText(' text')
   editor.selectAll();editor.paste();assert editor.toPlainText()==' text'
   clip();p.context_tools.clipboard();assert len(p.paths)==2
   p.submit('Explain these images');assert len(send.call_args.args[1])==2
   assert all(mime=='image/png' for _,mime in send.call_args.args[1]);send.reset_mock()
   w.open_search();c=w.search_controller;search=w.search_window;QTest.qWait(60)
   def walk(item):
    yield item
    for child in item.childItems():yield from walk(child)
   composer=next(i for i in walk(search.contentItem()) if i.objectName()=='composer')
   c.clear_attachments();c.set_query('Describe');composer.forceActiveFocus();image.fill(QColor('green'));clip()
   QTest.keyClick(search,Qt.Key_V,Qt.ControlModifier);QTest.qWait(30)
   assert len(c.attachments)==1 and c.attachments==p.paths and c.query=='Describe'
   send.assert_not_called()
   clip(secret=True,text=True);QTest.keyClick(search,Qt.Key_V,Qt.ControlModifier);assert c.query=='Describe' and len(c.attachments)==1
   app.clipboard().setText(' appended');QTest.keyClick(search,Qt.Key_V,Qt.ControlModifier);QTest.qWait(20)
   assert ' appended' in c.query
   c.submit(True);assert send.call_args.args[1]==[(c.attachments[0],'image/png')]
   send.reset_mock();c.clear_attachments();assert not c.attachments and not p.paths
   assert path.exists(),'draft/recovery image should not disappear when selection is cleared'
   # Storage failure consumes image paste, reports an error, and sends nothing.
   clip()
   with patch('clipboard_image.save',side_effect=OSError('Synthetic full disk')):
    assert c.paste_image() and c.error and not c.attachments
   send.assert_not_called()
   # Browsers and screenshot tools may advertise PNG without Qt imageData.
   image.fill(QColor('purple'));raw=QBuffer();raw.open(QIODevice.WriteOnly);image.save(raw,'PNG')
   mime=QMimeData();mime.setData('image/png',raw.data());app.clipboard().setMimeData(mime)
   assert c.paste_image() and len(c.attachments)==1
   assert QImage(c.attachments[0]).pixelColor(0,0)==QColor('purple')
   c.clear_attachments()
   mime=QMimeData();mime.setData('image/png',b'not an image');app.clipboard().setMimeData(mime)
   assert c.paste_image() and c.error and not c.attachments
   # Quota does not evict images referenced by existing conversations.
   from clipboard_image import save
   quota=path.parent/'clipboard-quota.png'
   with quota.open('wb') as f:f.truncate(256*1024**2)
   image.fill(QColor('yellow'));clip()
   try:save(app.clipboard().mimeData());raise AssertionError('quota not enforced')
   except ValueError:pass
   assert path.exists();quota.unlink()
 finally:
  app.clipboard().clear();p.backend.busy=False;w.close();w.deleteLater();QTest.qWait(30)
'''
