"""Old proposal history remains inspectable but cannot write local user Notes."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from lumen_store import Store
from wissen_data import Notebook, activate
from notes_query import resolve_link
from note_reviews import propose, decide, rows


class NoteReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'state');activate(self.store);self.book=Notebook(self.store)
        self.a=self.book.create('Quelle 日本語','Keep this original');self.b=self.book.create('Related','Evidence')
        rows(self.store)
        self.record=dict(id='old-pending',root=str(self.book.root),identity=self.book.identity,path=self.a['path'],title=self.a['title'],before=self.a['text'],after='Old proposal',revision=self.a['hash'],reason='Old human review',targets=[],created=time.time(),state='pending',origin='Lumen MCP')
        with self.store.connect() as db:db.execute('INSERT INTO note_reviews VALUES (?,?)',(self.record['id'],json.dumps(self.record)))

    def test_new_local_proposals_are_refused_and_original_history_is_retained(self):
        before=rows(self.store)
        with patch.object(self.book,'write') as write:
            with self.assertRaisesRegex(ValueError,'Lumen Server'):propose(self.store,self.a['path'],self.a['hash'],'Change',text='New')
            write.assert_not_called()
        self.assertEqual(rows(self.store),before);self.assertEqual(self.book.read(self.a['path'])['hash'],self.a['hash'])

    def test_old_apply_and_undo_are_refused_before_any_notebook_or_memory_access(self):
        before=rows(self.store)
        for action in ('apply','undo','invalid'):
            with patch('lumen_memory.Memory',side_effect=AssertionError('no memory writer')),patch('wissen_data.Notebook',side_effect=AssertionError('no note writer')):
                with self.assertRaises(ValueError):decide(self.store,self.record['id'],action)
        self.assertEqual(rows(self.store),before);self.assertEqual(self.book.read(self.a['path'])['hash'],self.a['hash'])

    def test_dismissing_old_pending_proposal_changes_only_review_state(self):
        result=decide(self.store,self.record['id'],'reject')
        self.assertEqual(result['state'],'revoked')
        self.assertEqual({k:v for k,v in result.items() if k not in ('state','decided')},{k:v for k,v in self.record.items() if k!='state'})
        self.assertEqual(self.book.read(self.a['path'])['hash'],self.a['hash'])
        with self.assertRaises(ValueError):decide(self.store,self.record['id'],'reject')

    def test_server_reference_helper_resolves_identity_after_rename(self):
        from uuid import uuid4
        target=self.book.write(self.b['path'],self.b['text'],self.b['hash'],note_id=str(uuid4()))
        self.assertEqual(resolve_link(self.a['path'],'/?document='+target['note_id'],{'Renamed.md':target}),'Renamed.md')

    def test_ui_has_history_and_close_without_apply_or_undo(self):
        from PySide6.QtWidgets import QApplication,QDialog,QPlainTextEdit,QPushButton,QWidget
        from PySide6.QtCore import QTimer
        from types import SimpleNamespace
        from note_reviews import show_reviews
        app=QApplication.instance() or QApplication([]);panel=QWidget();panel.tracker=SimpleNamespace(store=self.store)
        def check():
            dialog=panel.findChild(QDialog);self.assertEqual(len(dialog.findChildren(QPlainTextEdit)),2)
            labels=[b.text() for b in dialog.findChildren(QPushButton)]
            self.assertNotIn('Genau so übernehmen',labels);self.assertNotIn('Änderung rückgängig machen',labels)
            self.assertTrue(all(e.isReadOnly() for e in dialog.findChildren(QPlainTextEdit)));dialog.reject()
        QTimer.singleShot(20,check);show_reviews(panel)
