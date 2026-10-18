"""The real clipboard launcher uses private image attachments and fails closed."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ClipboardLaunchTest(unittest.TestCase):
    def launch(self, case):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, HOME=tmp, XDG_CONFIG_HOME=tmp+'/config',
                       XDG_CACHE_HOME=tmp+'/cache', XDG_DATA_HOME=tmp+'/data',
                       XDG_STATE_HOME=tmp+'/state', XDG_RUNTIME_DIR=tmp+'/run',
                       LUMEN_DATA=tmp+'/lumen', LUMEN_TOOLS_DATA=tmp+'/tools',
                       LUMEN_LANGUAGE=os.environ.get('LUMEN_LANGUAGE','de'), QT_QPA_PLATFORM='offscreen',
                       DBUS_SESSION_BUS_ADDRESS='unix:path='+tmp+'/absent')
            result = subprocess.run([sys.executable, '-c', PROBE, case, tmp,
                                    os.environ.get('LUMEN_TEST_PROGRAM', str(Path(__file__).resolve().parents[1]/'agent-app/main.py'))],
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_image_bytes_become_private_attachment(self): self.launch('image')
    def test_secret_image_is_never_saved_or_sent(self): self.launch('secret')
    def test_empty_clipboard_is_rejected(self): self.launch('empty')
    def test_local_file_url_remains_supported(self): self.launch('url')
    def test_nonempty_local_path_remains_supported(self): self.launch('path')
    def test_save_failure_does_not_send_unattached_prompt(self): self.launch('failure')


PROBE = r'''
import importlib.util, sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QMimeData, QTimer, QUrl
from PySide6.QtGui import QImage, QColor
case, temporary, program = sys.argv[1:]
spec=importlib.util.spec_from_file_location('clipboard_launch', program)
d=importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
app=d.create_app(); mime=QMimeData()
image=QImage(10,10,QImage.Format_ARGB32); image.fill(QColor('red'))
if case in ('image','secret','failure'): mime.setImageData(image)
if case=='secret': mime.setData('x-kde-passwordManagerHint', b'secret')
source=Path(temporary)/'image.png'; image.save(str(source))
if case=='url': mime.setUrls([QUrl.fromLocalFile(str(source))])
if case=='path': mime.setText(str(source))
app.clipboard().setMimeData(mime); sent=[]; errors=[]
class Window:
 def __init__(self, directory):
  self.chat=SimpleNamespace(action_titles={}, backend=SimpleNamespace(shutdown=lambda:None),
   begin_context=lambda action, paths, **kw: sent.append(paths), show_error=errors.append)
 def show(self): pass
 def show_page(self, page): pass
with patch.object(d,'create_app',return_value=app), patch.object(d,'LumenWindow',Window), \
 patch('lumen_migrate.migrate_user'), patch('lumen_crash.attach'), \
 patch.object(sys,'argv',['lumen','--clipboard-image','--prompt=Describe synthetic image']):
 if case=='failure':
  with patch('clipboard_image.save', side_effect=OSError('Synthetic full disk')):
   QTimer.singleShot(100,app.quit); d.main()
 else:
  QTimer.singleShot(100,app.quit); d.main()
try:
 if case in ('secret','empty','failure'):
  assert errors and not sent, (case,errors,sent)
  if case=='secret': assert not list((Path(temporary)/'cache').rglob('clipboard-*.png'))
 else:
  assert not errors and len(sent)==1 and len(sent[0])==1, (case,errors,sent)
  path=Path(sent[0][0]); assert str(path) and path.is_file(), sent
  if case=='image':
   assert path.parent==Path(temporary)/'cache/lumen/clipboard'
   assert path.stat().st_mode&0o777==0o600
   assert QImage(str(path)).pixelColor(0,0)==QColor('red')
  else: assert path==source
finally: app.clipboard().clear()
'''


if __name__ == '__main__': unittest.main()
