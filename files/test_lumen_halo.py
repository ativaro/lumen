"""Working marks follow real backend state and stop when waiting or hidden."""
import unittest
from test_search_qml import Qt6SearchTest


class HaloTests(unittest.TestCase):
    run_qt6 = Qt6SearchTest.run_qt6

    def test_working_waiting_hidden_and_reduced_motion(self):
        self.run_qt6('''
from unittest.mock import patch
import tempfile
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from studio_chat import StudioChat
from search_controller import SearchController
from search_qml import create_window
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
with tempfile.TemporaryDirectory() as tmp, patch('desktop_backend.DesktopBackend.refresh_sessions'):
 p=StudioChat(tmp);p.resize(960,700);p.show();c=SearchController(tmp,panel=p,applications=[])
 e,w=create_window(app,c);w.show();QTest.qWait(80)
 def walk(i):
  yield i
  for x in i.childItems():yield from walk(x)
 mark=next(i for i in walk(w.contentItem()) if i.objectName()=='lumenThinkingMark')
 try:
  assert mark.implicitWidth()>0 and not p.work_mark.mark.isNull()
  p.backend.set_busy(True);QTest.qWait(90)
  assert p.work_mark.timer.isActive() and mark.property('rotation')!=0
  p.backend.permissions=[dict(id='p',permission='read',patterns=['synthetic'])]
  p.backend.requestsChanged.emit(p.backend.permissions,[]);QTest.qWait(40)
  assert not p.work_mark.timer.isActive() and mark.property('rotation')==0
  p.backend.permissions=[];p.backend.requestsChanged.emit([],[]);QTest.qWait(90)
  assert p.work_mark.timer.isActive() and mark.property('rotation')!=0
  mark.setProperty('reduceMotion',True);QTest.qWait(40)
  assert mark.property('rotation')==0
  original=p.work_mark.accessibility
  class Reduced:
   def motionPreference(self):return Qt.ReducedMotion
  p.work_mark.accessibility=Reduced();p.work_mark.update_running()
  assert not p.work_mark.timer.isActive() and p.work_mark.angle==0
  p.work_mark.accessibility=original
  mark.setProperty('reduceMotion',False);p.work_mark.update_running();QTest.qWait(60)
  p.hide();w.hide();QTest.qWait(40)
  assert not p.work_mark.timer.isActive() and mark.property('rotation')==0
  p.show();w.show();QTest.qWait(60)
  assert p.work_mark.timer.isActive() and mark.property('rotation')!=0
  p.backend.set_busy(False);QTest.qWait(40)
  assert not p.work_mark.timer.isActive() and mark.property('rotation')==0
  from lumen_halo import LumenHalo
  with patch('lumen_halo.QApplication.styleHints',return_value=object()):
   legacy=LumenHalo();legacy.show();legacy.setActive(True)
   assert legacy.accessibility is None and legacy.timer.isActive()
   legacy.hide();assert not legacy.timer.isActive()
 finally:
  c.shutdown();w.hide();e.deleteLater();p.context_tools.close();p.backend.shutdown();p.close();QTest.qWait(20)
''')
