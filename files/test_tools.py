import sys
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
        from PySide6.QtWidgets import QApplication
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


    def test_household_deadlines_and_document_persistence(self):
        from tools_household import Household, deadlines
        from datetime import date
        from PySide6.QtCore import QDate
        with tempfile.TemporaryDirectory() as root:
            w=Household(root); key=w.library.create('Waschmaschine',attachments=[],notes='')
            w.focus_record(key); w.notes.setPlainText('Handbuch im Karton'); w.fields['model'].setText('W-100')
            w.dates['until'].setDate(QDate(2030,1,2)); w.save(); w.close()
            w=Household(root); w.focus_record(key)
            self.assertEqual(w.fields['model'].text(),'W-100'); self.assertIn('Handbuch',w.notes.toPlainText())
            self.assertIn('heute',deadlines({'remind':'2030-01-02'},date(2030,1,2)))
            self.assertIn('überschritten',deadlines({'until':'2029-01-02'},date(2030,1,2)))
            self.assertEqual(len(w.library.all(query='W-100')),1); w.close()



    def test_jobs_cancel_running_processes_and_fetch_only_readable_pages(self):
        import sys, threading, time
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        job=Job(lambda _:None); timer=threading.Timer(.1,job.cancelled.set); timer.start(); started=time.monotonic()
        try:
            with self.assertRaises(Cancelled): job.command([sys.executable,'-c','import time; time.sleep(60)'],timeout=2)
        finally: timer.cancel()
        self.assertLess(time.monotonic()-started,1.5)
        class Page(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8' if self.path=='/article' else 'application/octet-stream'); self.end_headers()
                self.wfile.write('<h1>Testartikel</h1><p>Lesbarer Text.</p><script>Ignorieren</script>'.encode())
            def log_message(self,*args): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Page); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            job=Job(lambda _:None); url=f'http://127.0.0.1:{server.server_port}'
            result=fetch_article(url+'/article',job); self.assertEqual(result['text'],'Testartikel\nLesbarer Text.')
            with self.assertRaises(ValueError): fetch_article(url+'/binary',job)
        finally: server.shutdown(); server.server_close(); thread.join()

if __name__=='__main__': unittest.main()
