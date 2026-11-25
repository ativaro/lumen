"""The real Qt entry point consumes one bound start, including after a parent failure."""
from pathlib import Path
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import lumen_connect as client


class DesktopDeliveryEntryTests(unittest.TestCase):
    def test_real_gui_entry_point_claims_only_the_matching_start_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);identity=str(uuid4())
            config=dict(server='https://synthetic.example.test',token='synthetic',device_id=str(uuid4()))
            (root/'connection.json').write_text(json.dumps(config));(root/'connection.json').chmod(0o600)
            with patch.object(client,'ROOT',root),patch.object(client,'request',return_value=[dict(id=identity)]),patch.object(client.subprocess,'Popen',side_effect=OSError('injected parent launch failure')):
                with self.assertRaises(OSError):client.desktop_requests(config)
            program='''
from pathlib import Path
import sys
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QDialog
import lumen_connect_gui as gui
root,option,identity=sys.argv[1:]
class Dialog(QDialog):
 def __init__(self,value):super().__init__();self.value=value
 def show(self):
  super().show()
  with (Path(root)/'shown').open('a') as target:target.write(self.value+'\\n')
  QTimer.singleShot(0,QApplication.instance().quit)
sys.argv=['synthetic-gui','--config-dir',root,'--delivery',identity,option,identity]
with patch.object(gui,'ArtifactDialog',Dialog),patch('appearance.apply_design'):
 raise SystemExit(gui.main())
'''
            env={**os.environ,'QT_QPA_PLATFORM':'offscreen','LUMEN_DESKTOP_FILES':str(Path(__file__).resolve().parent)}
            for option in ('--launch','--artifact','--artifact'):
                result=subprocess.run([sys.executable,'-c',program,str(root),option,identity],env=env,capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode,0,result.stderr[-1200:])
            self.assertEqual((root/'shown').read_text().splitlines(),[identity])
            with sqlite3.connect(root/'memory.sqlite3') as db:
                self.assertEqual(db.execute('SELECT id FROM desktop_requests').fetchall(),[(identity,)])
                self.assertEqual(db.execute('SELECT count(*) FROM desktop_request_starts').fetchone()[0],0)
