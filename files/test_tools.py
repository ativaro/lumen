import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools_data import Library, validate_segments, meeting_result, selected_sources, fetch_article, ArticleParser, web_url, Cancelled
from tools_ui import Job


class ToolsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()

    def test_private_import_update_archive_and_cancel(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'original.txt'; source.write_text('Handbuch')
            store=Library('household',root); job=Job(lambda _:None)
            asset=store.import_file(source,job); key=store.create('Drucker',attachments=[asset],notes='Alt')
            store.update(key,notes='Neu'); reopened=Library('household',root)
            self.assertEqual(reopened.get(key)['notes'],'Neu'); self.assertTrue(reopened.all(query='Handbuch')==[])
            self.assertEqual(reopened.asset(asset['asset']).read_text(),'Handbuch')
            store.archive(key); self.assertFalse(store.all()); self.assertEqual(len(store.all(True)),1)
            store.archive(key,False); self.assertTrue(source.exists())
            with self.assertRaises(ValueError): store.asset('../escape')
            job.cancelled.set()
            with self.assertRaises(Cancelled): store.import_file(source,job)
            self.assertEqual(len(list(store.assets.iterdir())),1)
            self.assertEqual(store.db.stat().st_mode & 0o777,0o600)

    def test_segment_and_answer_boundaries(self):
        segments=validate_segments([{'offsets':{'from':0,'to':1500},'text':' Hallo '},{'offsets':{'from':1500,'to':3000},'text':'Weiter'}])
        self.assertEqual(segments[0]['text'],'Hallo')
        with self.assertRaises(ValueError): validate_segments([{'offsets':{'from':5,'to':1},'text':'bad'}])
        answer=dict(summary='Erledigt',decisions=[dict(text='Ja',segment=0)],actions=[])
        self.assertEqual(meeting_result(json.dumps(answer),2),answer)
        answer['decisions'][0]['segment']=9
        with self.assertRaises(ValueError): meeting_result(json.dumps(answer),2)
        parser=ArticleParser(); parser.feed('<h1>Titel</h1><script>hidden()</script><p>Inhalt &amp; mehr</p>')
        self.assertEqual(parser.text(),'Titel\nInhalt & mehr')
        with self.assertRaises(ValueError): web_url('file:///etc/passwd')
        with self.assertRaises(ValueError): web_url('https://user:pw@example.com')
        self.assertEqual(len(selected_sources([dict(text='yes'),dict(text='no',selected=False)])),1)
        with self.assertRaises(ValueError): selected_sources([dict(text='x'*70001)])

    def test_meeting_ui_persists_edits_and_job_results(self):
        from tools_meetings import Meetings
        from PyQt5.QtCore import Qt
        with tempfile.TemporaryDirectory() as root:
            w=Meetings(root); w.error=lambda message:self.fail(message)
            key=w.library.create('Besprechung',recording={'name':'sample.wav','asset':'sample.wav'},duration=3000,
                segments=[dict(start=0,end=3000,text='Alt')],summary='',results=[])
            w.focus_record(key); w.transcript.item(0,1).setText('Korrigiert'); w.save()
            self.assertEqual(w.library.get(key)['segments'][0]['text'],'Korrigiert')
            w.library.update(key,segments=[dict(start=100,end=2500,text='Neu')]); w.focus_record(key)
            self.assertEqual(w.transcript.item(0,1).text(),'Neu')
            with patch.object(w.player,'play_at') as play:
                w.seek_segment(0,0); play.assert_called_once_with(100)
            w.archive(); self.assertTrue(w.library.all(True)); w.close()

if __name__=='__main__': unittest.main()
