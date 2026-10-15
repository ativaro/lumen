"""References share originals, guard stale changes, and never submit conversations/tasks."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools_data import Library
from projects_references import change, open_reference, validate
from projects_mcp import invoke
from lumen_store import Store


class ReferencesTest(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory()); self.root = Path(self.temp)
        self.enterContext(patch.dict(os.environ, LUMEN_TOOLS_DATA=self.temp, LUMEN_DATA=str(self.root/'state')))
        self.library = Library('workbench', self.root)
        self.project = self.library.create('One', resources=[], references=[])

    def revision(self, project=None):
        return invoke('lumen_project_read', dict(id=project or self.project))['item']['revision']

    def test_shared_file_unlink_stale_revision_and_archive_preserve_original(self):
        source = self.root/'file'; source.write_text('original')
        ref = dict(kind='file', title='Document', target=str(source))
        other = self.library.create('Two')
        change(self.library, self.project, self.revision(), ref)
        change(self.library, other, self.revision(other), ref)
        stale = self.revision()
        change(self.library, self.project, stale, dict(ref,title='Renamed'))
        with self.assertRaises(ValueError): change(self.library,self.project,stale,ref,True)
        self.assertEqual(len(self.library.get(self.project)['resources']),1)
        change(self.library,self.project,self.revision(),ref,True)
        self.assertEqual(self.library.get(self.project)['resources'],[])
        self.assertEqual(len(self.library.get(other)['resources']),1)
        current = self.revision(); self.library.archive(self.project)
        with self.assertRaises(ValueError): change(self.library,self.project,current,ref)
        self.assertEqual(source.read_text(),'original')

    def test_task_and_chat_open_are_display_only_and_bad_references_rejected(self):
        store=Store(self.root/'state'); task=store.create_task('Saved',status='completed')
        ref=dict(kind='task',title='Saved',id=task)
        change(self.library,self.project,self.revision(),ref)
        chat=dict(kind='chat',title='Conversation',chat=dict(directory=self.temp,session='ses_saved'))
        change(self.library,self.project,self.revision(),chat)
        self.assertEqual(len(invoke('lumen_project_read',dict(id=self.project))['references']['items']),2)
        with patch('PySide6.QtCore.QProcess.startDetached',return_value=(True,123)) as launch:
            open_reference(ref,store); args=launch.call_args.args[1]
            self.assertEqual(args[-2:],['--task',task])
            open_reference(chat,store); args=launch.call_args.args[1]
            self.assertEqual(args[-4:],['--directory',self.temp,'--session','ses_saved'])
            self.assertNotIn('--prompt',args)
        self.assertEqual(store.task(task)['status'],'completed')
        for bad in (dict(ref,id=None),dict(chat,chat=dict(directory='relative',session='x')),
                    dict(chat,chat=dict(directory=self.temp,session='bad\nvalue')),
                    dict(kind='url',title='Bad',target='https://u:pw@example.org'),
                    dict(kind='object',title='Bad',target=None),dict(ref,run=True)):
            with self.assertRaises(ValueError):validate(bad)
        with patch('PySide6.QtCore.QProcess.startDetached') as launch:
            with self.assertRaises(ValueError):open_reference(dict(chat,chat=dict(directory=str(self.root/'missing'),session='ses_saved')),store)
            launch.assert_not_called()

    def test_native_reference_tab_keeps_unsaved_project_notes(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QCoreApplication,QEvent
        from tools_workbench import Workbench
        app=QApplication.instance() or QApplication([])
        window=Workbench(self.root);window.error=lambda text:self.fail(text)
        try:
            window.focus_record(self.project);window.notes.setPlainText('My unsaved note')
            pane=window.reference_pane
            pane.apply(dict(kind='task',title='Missing task remains a reference',id='a'*32))
            self.assertEqual(window.notes.toPlainText(),'My unsaved note')
            self.assertEqual(pane.items.count(),1)
            pane.items.setCurrentRow(0);pane.unlink()
            self.assertEqual(pane.items.count(),0)
            self.assertEqual(self.library.get(self.project)['notes'],'My unsaved note')
        finally:
            window.close();window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()

if __name__=='__main__':unittest.main()
