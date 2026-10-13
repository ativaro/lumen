"""Room assignment preserves existing household IDs, fields, receipts and archive."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication
from tools_data import Library
from household_workspace import HouseholdRoom

class HouseholdWorkspaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.tmp=self.enterContext(tempfile.TemporaryDirectory())
        self.view=HouseholdRoom(Path(self.tmp));self.addCleanup(self.view.close)
        self.rooms=[dict(id='a',name='Home'),dict(id='b',name='Workshop')]
    def visible(self):
        return [self.view.entries.item(i).text() for i in range(self.view.entries.count()) if not self.view.entries.item(i).isHidden()]
    def test_second_editor_refused_and_legacy_activation_reveals_existing_record(self):
        with self.assertRaises(ValueError): HouseholdRoom(Path(self.tmp))
        from interop_data import Registry
        from PySide6.QtTest import QTest
        key=self.view.library.create('Linked record',kind='Vertrag',room_id='b',attachments=[])
        url=Registry(self.view.library.root.parent).register(dict(app='household',kind='record',id=key,title='Linked record'))
        self.view.set_room('a',self.rooms)
        reveal=Mock();self.view.revealRequested.connect(reveal)
        self.view.activate({'ref':url});QTest.qWait(350)
        self.assertEqual(self.view.current,key);self.assertEqual(self.view.scope.currentData(),'all')
        reveal.assert_called_once()
    def test_existing_unassigned_and_orphaned_records_remain_reachable(self):
        lib=self.view.library
        a=lib.create('Internet',kind='Vertrag',provider='Provider',room_id='a',remind='2026-11-01',attachments=[],notes='Keep')
        b=lib.create('Device',kind='Gerät',room_id='b',until='2020-01-01',attachments=[])
        loose=lib.create('Unassigned',kind='Gerät',attachments=[])
        orphan=lib.create('Removed room',kind='Gerät',room_id='gone',attachments=[])
        self.view.set_room('a',self.rooms);self.assertEqual(self.visible(),['Internet'])
        self.view.scope.setCurrentIndex(1);self.assertEqual(set(self.visible()),{'Unassigned','Removed room'})
        self.view.focus_record(a);self.view.assignment.setCurrentIndex(self.view.assignment.findData('b'));self.view.assign()
        self.assertEqual(lib.get(a)['room_id'],'b');self.assertEqual(lib.get(a)['notes'],'Keep')
        self.assertEqual(lib.get(a)['remind'],'2026-11-01')
        self.view.set_room('b',self.rooms);self.assertEqual(set(self.visible()),{'Internet','Device'})
        self.view.focus_record(a);self.view.archive();self.assertTrue(lib.get(a)['_archived'])
        self.view.archived.setChecked(True);self.view.focus_record(a);self.view.archive()
        self.assertFalse(lib.get(a)['_archived']);self.assertEqual(lib.get(a)['provider'],'Provider')
        self.assertEqual({r['id'] for r in lib.all()}, {a,b,loose,orphan})
    def test_room_change_saves_edits_and_busy_import_prevents_close(self):
        key=self.view.library.create('Device',kind='Gerät',room_id='a',attachments=[])
        self.view.set_room('a',self.rooms);self.view.focus_record(key)
        self.view.notes.setPlainText('Saved before changing rooms')
        self.view.set_room('b',self.rooms)
        self.assertEqual(self.view.library.get(key)['notes'],'Saved before changing rooms')
        self.assertFalse(self.view.body.isEnabled());self.assertEqual(self.view.current,'')
        self.view.job=Mock()
        try:
            self.assertFalse(self.view.can_close())
            with self.assertRaises(ValueError):self.view.set_room('a',self.rooms)
        finally:self.view.job=None
