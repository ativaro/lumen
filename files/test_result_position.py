"""Interactive results keep their chronological position in native chat and Search."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

class ResultPositionTest(unittest.TestCase):
    def test_table_then_streamed_text_and_followup(self):
        program=Path(os.environ.get('LUMEN_TEST_PROGRAM',str(Path(__file__).resolve().parents[1]/'agent-app/main.py')))
        with tempfile.TemporaryDirectory() as tmp:
            env=dict(os.environ,HOME=tmp,XDG_CONFIG_HOME=tmp+'/config',XDG_CACHE_HOME=tmp+'/cache',
                XDG_DATA_HOME=tmp+'/data',LUMEN_DATA=tmp+'/state',LUMEN_TOOLS_DATA=tmp+'/tools',
                QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software',LUMEN_OPENCODE_BIN='/nonexistent/test-engine')
            result=subprocess.run([sys.executable,'-c',PROBE,str(program),tmp],env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

PROBE=r'''
import importlib.util,json,sys
from unittest.mock import patch
from PySide6.QtCore import QPoint,QPointF
from PySide6.QtTest import QTest
from PySide6.QtQuickControls2 import QQuickStyle
program,root=sys.argv[1:];QQuickStyle.setStyle('Basic')
spec=importlib.util.spec_from_file_location('desktop',program);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
from rich_result import present
app=d.create_app()
with patch('desktop_backend.DesktopBackend.refresh_sessions'):
 w=d.LumenWindow(root);w.show();p=w.chat;w.open_search();c=w.search_controller;search=w.search_window
 def walk(i):
  yield i
  for child in i.childItems():yield from walk(child)
 def message(role,text,key):return dict(info=dict(role=role,id=key),parts=[dict(type='text',text=text)])
 payload=present(dict(title='Synthetic table',blocks=[dict(id='rows',type='table',label='Values',columns=['Name','Value'],rows=[['One',1]])]))
 tool=dict(type='tool',tool='lumen_present_view',state=dict(status='completed',output=json.dumps(payload)))
 answer=message('assistant','Before table','a');answer['parts'].append(tool)
 history=[message('user','Question','u'),answer]
 def update():
  p.backend.messages=history;p.backend.messagesChanged.emit(history);search.show();QTest.qWait(300)
 try:
  update();p.rich.filter_table('rows','One')
  answer['parts'].append(dict(type='text',text='After table'))
  history.extend([message('user','Followup','u2'),message('assistant','Newest answer','a2')]);update()
  after=next(row[2] for row in p.transcript.rows if 'After table' in row[1][1])
  assert p.rich_widget.mapTo(p.transcript.content,QPoint(0,p.rich_widget.height())).y() <= after.mapTo(p.transcript.content,QPoint(0,0)).y(), 'Native table is pinned below later content'
  table=next(i for i in walk(search.contentItem()) if i.objectName()=='resultFilter_rows')
  text=next(i for i in walk(search.contentItem()) if i.objectName()=='answerBlockText' and 'After table' in i.property('text'))
  assert table.mapToScene(QPointF(0,table.height())).y()<text.mapToScene(QPointF(0,0)).y(), 'Search table is pinned below later content'
  assert p.rich.tables['rows']['query']=='One','Streaming must preserve filters'
  answer['parts'][-1]['text']+=' continues';update()
  assert 'continues' in str(c.messages) and p.rich.tables['rows']['query']=='One'
  from search_document import message_rows
  assert message_rows([answer])[1]=='Before table\n\nAfter table continues'
  # Starting another session must remove the old result, then restoring history reanchors it.
  history_saved=history;history=[message('assistant','Other session','other')];update()
  assert not p.rich.active
  history=history_saved;update();assert p.rich.active
  assert p.rich_widget.mapTo(p.transcript.content,QPoint(0,p.rich_widget.height())).y() <= next(row[2] for row in p.transcript.rows if 'After table' in row[1][1]).mapTo(p.transcript.content,QPoint(0,0)).y()
 finally:
  c.shutdown();search.hide();w.hide();p.backend.shutdown();QTest.qWait(20)
'''
