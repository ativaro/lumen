"""Qt parsing and both production answer surfaces using synthetic content."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SAMPLE = '''## Hier lohnt sich das Aufräumen.

Downloads und doppelte Bilder belegen zusammen **20,6 GB**. Prüfe zuerst diese Bereiche.

| Bereich | Größe | Nächster Schritt |
| --- | ---: | --- |
| Downloads | 12,4 GB | Alte Downloads durchsehen |
| Doppelte Bilder | 8,2 GB | Originale vergleichen |
| Dokumente | 2,1 GB | Behalten |

- [ ] Downloads durchsehen
- [ ] Doppelte Bilder vergleichen
- [x] Sicherung vorbereitet

> Die Tabelle zeigt belegten Speicher, nicht die sicher löschbare Menge.
'''

class AnswerBlocksTest(unittest.TestCase):
    def qt(self, source):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, '-c', 'import os\nSAMPLE='+repr(SAMPLE)+'\n'+source],
                cwd=Path(__file__).parent, capture_output=True, text=True, timeout=35,
                env=dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software',
                         XDG_CONFIG_HOME=tmp+'/config', LUMEN_DATA=tmp+'/data', LUMEN_TOOLS_DATA=tmp+'/tools', LUMEN_CRASH_CHILD='1'))
            self.assertEqual(result.returncode, 0, result.stderr+result.stdout)

    def test_structure_safety_and_lossless_narrow_tables(self):
        self.qt('''
from PySide6.QtGui import QGuiApplication
from answer_blocks import blocks, table_html
app=QGuiApplication([]);result=blocks(SAMPLE)
assert [b['kind'] for b in result]==['text','table','checklist','quote']
table=result[1]
assert table['rows'][0][1]['right'] and table['rows'][1][1]['right']
for width in (300,900):
 html=table_html(table,width,'#888888','#555555')
 for value in ('Downloads','12,4 GB','Originale vergleichen','2,1 GB','Nächster Schritt'): assert value in html
assert '<table' not in table_html(table,300,'#888888','#555555')
assert [i['checked'] for i in result[2]['items']]==[False,False,True]
assert result[2]['items'][0]['key']==blocks(SAMPLE+'\\nWeiterer Text')[2]['items'][0]['key']
extra=blocks('| A | B |\\n|--|--|\\n| 日本語 | x \\| y |\\n\\n- [ ] مرحبا\\n\\n```html\\n  <script>alert(1)</script>\\n```')
assert extra[0]['rows'][1][1]['text']=='x | y'
assert extra[-1]['kind']=='code' and '&nbsp;&nbsp;&lt;script&gt;' in extra[-1]['body']
unsafe=blocks('[bad](file:///etc/passwd) ![image](https://example.com/x.png) [safe](https://example.com)\\n\\n- [ ] [bad](file:///etc/passwd)')
value=str(unsafe)
assert '<img' not in value and 'href="file:' not in value and 'href="https://example.com"' in value
value=blocks('1. First\\n2. Second\\n   - Nested\\n\\n- [ ] Task\\n\\n> Quote\\n\\n```sh\\n- [ ] not a task\\n```')
assert value[0]['kind']=='text' and '<ol' in value[0]['body']
assert value[-1]['kind']=='code' and value[-2]['kind']=='quote'
''')

    def test_native_cards_streaming_checks_and_resize(self):
        self.qt('''
from PySide6.QtWidgets import QApplication,QCheckBox
from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from answer_widget import AnswerBody,AnswerText
from appearance import apply_design
app=QApplication([]);settings=QSettings();w=AnswerBody(settings);w.resize(850,900);w.show()
w.set_answer(SAMPLE,('session',1));QTest.qWait(60)
check=w.findChildren(QCheckBox)[0];check.click();assert check.isChecked()
first=w.items[0][0]
w.set_answer(SAMPLE+'\\nMore text',('session',1));QTest.qWait(30)
assert w.items[0][0] is first and w.findChildren(QCheckBox)[0].isChecked()
w.set_answer(SAMPLE,('other-session',1));QTest.qWait(30)
assert not w.findChildren(QCheckBox)[0].isChecked()
for theme in ('glass','atelier'):
 apply_design(app,theme)
 for width in (380,850):
  w.resize(width,1100);QTest.qWait(80)
  for view in w.findChildren(AnswerText):
   assert view.horizontalScrollBar().maximum()==0,(width,view.toPlainText(),view.document().size())
   assert view.document().size().height() <= view.viewport().height()+5,(theme,width,view.toPlainText())
  if os.environ.get('LUMEN_ANSWER_ARTIFACTS'): w.grab().save(os.environ['LUMEN_ANSWER_ARTIFACTS']+'/native-'+theme+'-'+str(width)+'.png')
w.close()
''')

    def test_search_real_cards_and_checkbox_across_stream_and_session(self):
        self.qt('''
from PySide6.QtGui import QGuiApplication
from PySide6.QtCore import QPointF,Qt,qInstallMessageHandler
from PySide6.QtTest import QTest
from search_controller import SearchController
from search_qml import create_window
app=QGuiApplication([]);warnings=[]
qInstallMessageHandler(lambda kind,context,message: warnings.append(message) if any(x in message for x in ('ReferenceError','TypeError','Binding loop','Unable to assign')) else None)
c=SearchController(applications=[]);engine,w=create_window(app,c)
def walk(item):
 yield item
 for child in item.childItems():yield from walk(child)
def msg(text):return dict(info=dict(role='assistant',id='answer1'),parts=[dict(type='text',text=text)])
try:
 c.backend.session='one';c.show_conversation();c.update_messages([msg(SAMPLE)]);w.show();QTest.qWait(100)
 for width in (540,1100):
  w.setWidth(width);w.setHeight(1080);QTest.qWait(100)
  checks=[i for i in walk(w.contentItem()) if i.objectName()=='answerCheck']
  assert len(checks)==3
  if width==1100:
   point=checks[0].mapToScene(QPointF(10,12)).toPoint()
   checks[0].forceActiveFocus()
   QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,point);QTest.qWait(30)
   assert checks[0] in list(walk(w.contentItem())) and checks[0].hasActiveFocus()
   assert c.messages[0]['blocks'][2]['items'][0]['checked']
  if os.environ.get('LUMEN_ANSWER_ARTIFACTS'):
   for theme in ('glass','atelier'):
    c.settings.setValue('appearance',theme);c.reload_settings();c.update_messages([msg(SAMPLE)]);QTest.qWait(100)
    w.grabWindow().save(os.environ['LUMEN_ANSWER_ARTIFACTS']+'/search-'+theme+'-'+str(width)+'.png')
 c.update_messages([msg(SAMPLE+'\\nAnother chunk')]);QTest.qWait(30)
 assert c.messages[0]['blocks'][2]['items'][0]['checked']
 c.backend.session='two';c.update_messages([msg(SAMPLE)]);QTest.qWait(30)
 assert not c.messages[0]['blocks'][2]['items'][0]['checked']
 assert not warnings,warnings
finally:c.shutdown();w.hide();engine.deleteLater();QTest.qWait(20)
''')

if __name__ == '__main__': unittest.main()
