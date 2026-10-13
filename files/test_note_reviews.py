import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lumen_store import Store
from wissen_data import Notebook, activate, resolve_link
from lumen_memory import Memory
from note_reviews import propose, decide, rows

class NoteReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'state');activate(self.store)
        self.book=Notebook(self.store);self.memory=Memory(self.store);self.memory.configure(True,False)
        self.a=self.book.create('Quelle 日本語','Test source');self.b=self.book.create('Verwandt','Evidence')
        for n in (self.a,self.b):self.memory.share(n['path'],True)
    def proposal(self):
        return propose(self.store,self.a['path'],self.a['hash'],'Gemeinsame Quelle',targets=[self.b['path']])['id']
    def test_preview_reference_approval_and_undo(self):
        id=self.proposal();self.assertEqual(id,self.proposal())
        self.assertEqual(self.book.read(self.a['path'])['hash'],self.a['hash'])
        saved=decide(self.store,id,'apply');note=self.book.read(self.a['path'])
        self.assertEqual(resolve_link(note['path'],note['links'][0],{self.b['path']:self.b}),self.b['path'])
        self.assertEqual(saved['state'],'applied');self.assertIn('Gemeinsame',saved['reason'])
        decide(self.store,id,'undo');self.assertEqual(self.book.read(self.a['path'])['text'],self.a['text'])
    def test_stale_source_target_or_revoked_consent_fail_closed(self):
        id=self.proposal();self.memory.share(self.b['path'],False)
        with self.assertRaises(ValueError):decide(self.store,id,'apply')
        self.memory.share(self.b['path'],True)
        self.book.write(self.b['path'],'Changed',self.b['hash'])
        with self.assertRaises(ValueError):decide(self.store,id,'apply')
        self.assertEqual(self.book.read(self.a['path'])['hash'],self.a['hash'])
        edit=propose(self.store,self.a['path'],self.a['hash'],'Preview',text='New body')['id']
        self.book.write(self.a['path'],'External',self.a['hash'])
        with self.assertRaises(ValueError):decide(self.store,edit,'apply')
    def test_reject_expiry_and_undo_conflict(self):
        id=self.proposal();decide(self.store,id,'reject')
        with self.assertRaises(ValueError):decide(self.store,id,'apply')
        id=self.proposal()
        with patch('note_reviews.time.time',return_value=rows(self.store)[0]['created']+86401):
            with self.assertRaises(ValueError):decide(self.store,id,'apply')
        decide(self.store,id,'apply');n=self.book.read(self.a['path']);self.book.write(n['path'],'Later edit',n['hash'])
        with self.assertRaises(ValueError):decide(self.store,id,'undo')
        self.assertEqual(self.book.read(n['path'])['text'],'Later edit')
    def test_server_reference_resolves_by_identity_after_rename(self):
        from uuid import uuid4
        target=self.book.write(self.b['path'],self.b['text'],self.b['hash'],note_id=str(uuid4()))
        url='/?document='+target['note_id']
        self.assertEqual(resolve_link(self.a['path'],url,{'Renamed.md':target}),'Renamed.md')
        id=self.proposal();record=next(r for r in rows(self.store) if r['id']==id)
        self.assertIn(url,record['after'])

    def test_ui_uses_plain_text_and_can_close(self):
        from PySide6.QtWidgets import QApplication, QDialog, QPlainTextEdit
        from PySide6.QtCore import QTimer
        from types import SimpleNamespace
        from note_reviews import show_reviews
        app=QApplication.instance() or QApplication([])
        from PySide6.QtWidgets import QWidget
        panel=QWidget();panel.tracker=SimpleNamespace(store=self.store);self.proposal()
        def check():
            dialog=panel.findChild(QDialog)
            self.assertEqual(len(dialog.findChildren(QPlainTextEdit)),2)
            dialog.reject()
        QTimer.singleShot(20,check);show_reviews(panel)
