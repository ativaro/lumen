import tempfile
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt, QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from tools_workbench import Workbench
from tools_household import Household
from tools_meetings import Meetings
from tools_radio import Radio
from interop_open import focus
from interop_parts import FIELDS,capture_part
from interop_sources import capture


class FocusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name); self.windows = []
        self.env=patch.dict(os.environ,{'LUMEN_DATA':str(self.root/'state')});self.env.start();self.addCleanup(self.env.stop)

    def tearDown(self):
        for window in self.windows: window.close(); window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def window(self, cls):
        result = cls(self.root); self.windows.append(result); return result

    def ref(self, window, key, part, **position):
        kind,_,value=part.partition(':')
        if kind in FIELDS:
            window.focus_record(key);part=capture_part(window,kind,int(value))
        return dict(app=window.name, kind='record', id=key, title='Test', position=dict(part=part, **position))

    def test_project_resource_and_question_and_household_attachment_selection(self):
        project = self.window(Workbench); key = project.library.create('Test', notes='', resources=[dict(kind='file', target='/tmp/one', title='One'), dict(kind='file', target='/tmp/two', title='Two')], questions=[dict(text='Question', done=False)])
        focus(project, self.ref(project, key, 'resource:1'))
        self.assertEqual(project.tabs.currentIndex(), 1); self.assertEqual(project.resources.currentRow(), 1)
        focus(project, self.ref(project, key, 'question:0')); self.assertEqual(project.questions.currentRow(), 0)
        house = self.window(Household); key = house.library.create('Device', kind='Gerät', notes='', attachments=[dict(asset='one.pdf', name='One'), dict(asset='two.pdf', name='Two')])
        focus(house, self.ref(house, key, 'attachment:two.pdf'))
        self.assertEqual(house.attachments.currentItem().data(Qt.UserRole)['asset'], 'two.pdf')

    def test_meeting_agenda_result_and_radio_source_and_script_range(self):
        meeting = self.window(Meetings); key = meeting.library.create('Meeting', recording=None, duration=0, agenda='Agenda', summary='Summary', segments=[dict(start=10, end=20, text='A')], results=[dict(kind='actions', text='Action', segment=0)])
        focus(meeting, self.ref(meeting, key, 'agenda')); self.assertEqual(meeting.tabs.currentIndex(), 2)
        focus(meeting, self.ref(meeting, key, 'result:0', time=10)); self.assertEqual(meeting.tabs.currentIndex(), 1); self.assertEqual(meeting.results.currentRow(), 0)
        radio = self.window(Radio); key = radio.library.create('Radio', sources=[dict(title='Source', text='Text', url='', selected=True)], script='abcdef', minutes=5)
        focus(radio, self.ref(radio, key, 'source:0')); self.assertEqual(radio.sources.currentRow(), 0)
        focus(radio, dict(app='radio', kind='record', id=key, title='Radio', position=dict(start=1, end=4)))
        self.assertEqual(radio.script.textCursor().selectedText(), 'bcd')

    def test_missing_subobject_is_reported_instead_of_opening_another_item(self):
        project = self.window(Workbench); key = project.library.create('Test', notes='', resources=[], questions=[])
        with self.assertRaises(ValueError): focus(project, self.ref(project, key, 'resource:8'))

    def test_project_links_follow_reordered_content_and_reject_removed_duplicate_or_legacy_targets(self):
        window=self.window(Workbench)
        a=dict(kind='url',target='https://example.test/first',title='First');b=dict(kind='url',target='https://example.test/chosen',title='Chosen')
        qa=dict(text='First question',done=False);qb=dict(text='Chosen question',done=False)
        key=window.library.create('Project',notes='',resources=[a,b],questions=[qa,qb]);window.focus_record(key)
        window.tabs.setCurrentIndex(1);window.resources.setCurrentRow(1);resource=capture(window)['source']
        window.tabs.setCurrentIndex(0);window.questions.setCurrentRow(1);question=capture(window)['source']
        window.library.update(key,resources=[b,a],questions=[dict(qb,done=True),qa])
        focus(window,resource);self.assertEqual(window.resources.currentRow(),0)
        focus(window,question);self.assertEqual(window.questions.currentRow(),0)
        window.library.update(key,resources=[a],questions=[dict(qb,text='Changed question'),qa])
        for ref in (resource,question):
            with self.assertRaisesRegex(ValueError,'geändert, entfernt'):focus(window,ref)
        window.library.update(key,resources=[b,b])
        with self.assertRaisesRegex(ValueError,'mehrfach'):focus(window,resource)
        with self.assertRaisesRegex(ValueError,'Inhaltsprüfung'):
            focus(window,dict(resource,position=dict(part='resource:0')))

    def test_meeting_links_follow_reordered_segments_and_results_then_reject_removed_targets(self):
        window=self.window(Meetings)
        segments=[dict(start=10,end=20,text='First passage'),dict(start=30,end=40,text='Chosen passage')]
        results=[dict(kind='actions',text='First action',segment=0),dict(kind='actions',text='Chosen action',segment=1)]
        key=window.library.create('Meeting',recording=None,duration=100,agenda='',summary='',segments=segments,results=results);window.focus_record(key)
        window.tabs.setCurrentIndex(0);window.transcript.selectRow(1);segment=capture(window)['source']
        window.tabs.setCurrentIndex(1);window.results.selectRow(1);result=capture(window)['source']
        window.library.update(key,segments=list(reversed(segments)),results=[dict(results[1],segment=0),dict(results[0],segment=1)])
        focus(window,segment);self.assertEqual(window.transcript.currentRow(),0)
        focus(window,result);self.assertEqual(window.results.currentRow(),0)
        window.library.update(key,segments=[segments[0]],results=[results[0]])
        for ref in (segment,result):
            with self.assertRaisesRegex(ValueError,'geändert, entfernt'):focus(window,ref)

    def test_radio_sources_and_sound_rules_are_checked_before_retargeting(self):
        radio=self.window(Radio);a=dict(title='First',text='First body',url='');b=dict(title='Chosen',text='Chosen body',url='')
        key=radio.library.create('Radio',sources=[a,b],script='',minutes=5);radio.focus_record(key);radio.sources.setCurrentRow(1)
        ref=capture(radio)['source'];radio.library.update(key,sources=[b,a]);focus(radio,ref)
        self.assertEqual(radio.sources.currentRow(),0);self.assertEqual(radio.source_text.toPlainText(),'Chosen body')
        radio.library.update(key,sources=[a])
        with self.assertRaisesRegex(ValueError,'geändert, entfernt'):focus(radio,ref)
        from tools_sound import Sound
        with patch.object(Sound,'poll'):
            sound=self.window(Sound);sound.timer.stop()
            a=dict(title='First',volume=60,mute=False,sink='headphones',role='music');b=dict(title='Chosen',volume=80,mute=False,sink='headphones',role='music')
            sound.library.update(sound.current,rules=dict(first=a,chosen=b));sound.load_rules();sound.rules.setCurrentItem(sound.rules.topLevelItem(1))
            ref=capture(sound)['source'];sound.library.update(sound.current,rules=dict(chosen=b,first=a));focus(sound,ref)
            self.assertEqual(sound.rules.currentItem().data(0,Qt.UserRole),'chosen')
            sound.library.update(sound.current,rules=dict(chosen=dict(b,volume=90),first=a))
            with self.assertRaisesRegex(ValueError,'geändert, entfernt'):focus(sound,ref)

    def test_vault_snapshot_focus_is_registered_before_fast_result(self):
        from tools_vault import Vault
        window=self.window(Vault);key=window.library.create('Plan',repository='/tmp/repo',sources=[],excludes=[])
        def immediate(text,function,done,**kwargs):
            done([dict(id='chosen-snapshot',time='2026-10-03T12:00:00',paths=['/tmp/source'])]);return True
        with patch.object(window,'work',side_effect=immediate):
            focus(window,dict(app='vault',kind='record',id=key,title='Plan',position=dict(part='snapshot:chosen-snapshot')))
        self.assertEqual(window.selected(),'chosen-snapshot')

    def test_wissen_collection_in_another_notebook_and_exact_text(self):
        from tools_wissen import Wissen
        from wissen_data import Notebook
        from PySide6.QtWidgets import QMessageBox
        window=self.window(Wissen)
        def ready():
            for _ in range(300):
                QTest.qWait(20)
                if window.book and not window.job and not window.poller and not window.after_job:return
            self.fail(window.status.text())
        ready();window.poll_timer.stop()
        other=self.root/'other-notes';other.mkdir();book=Notebook(window.store,other)
        folder=book.create_collection('Reading');note=book.create('Selected',text='abcdef',folder=folder)
        book.create('Unselected',text='Other body')
        ref=dict(app='wissen',kind='collection',id='collection:folder:Reading',title='Reading',locator=dict(root=str(other),area='user'))
        with patch('PySide6.QtWidgets.QMessageBox.question',return_value=QMessageBox.Yes):focus(window,ref)
        ready()
        self.assertEqual(window.book.root,other);self.assertEqual(window.collection,'folder:Reading');self.assertEqual(window.entries.count(),1)
        self.assertEqual(window.doc['path'],note['path']);self.assertFalse(window.pending_file)
        focus(window,dict(app='wissen',kind='note',id=note['path'],title='Selected',path=str(other/note['path']),locator=ref['locator'],position=dict(start=1,end=4)))
        ready();self.assertEqual(window.editor.textCursor().selectedText(),'bcd')
        ref['id']='collection:folder:Missing'
        with self.assertRaises(ValueError):focus(window,ref)


if __name__ == '__main__': unittest.main()
