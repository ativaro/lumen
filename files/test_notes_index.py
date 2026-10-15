import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lumen_store import Store
from wissen_data import Notebook, parse


class IndexTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name); self.store = Store(self.home/'state')
        self.book = Notebook(self.store, self.home/'notes', create=True)
        (self.book.root/'one.md').write_text('# One\n#test\nGrüße 🌍 漢字')

    def test_restart_reuses_parse_but_reads_current_bytes(self):
        first = self.book.scan()
        with patch('wissen_data.parse', wraps=parse) as parser:
            self.assertEqual(Notebook(self.store,self.book.root).scan(), first)
            self.assertEqual(parser.call_count, 0)
            path = self.book.root/'one.md'; stamp = path.stat()
            path.write_text('# Two\n#test\nGrüße 🌍 漢字'); os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            changed = self.book.scan()
            self.assertEqual(changed['notes'][0]['title'], 'Two')
            self.assertEqual(parser.call_count, 1)

    def test_deleted_symlink_unreadable_and_offline_never_use_cache(self):
        self.book.scan(); path = self.book.root/'one.md'; path.unlink()
        self.assertEqual(self.book.scan()['notes'], [])
        path.symlink_to(self.home/'outside.md'); (self.home/'outside.md').write_text('# Secret')
        self.assertEqual(self.book.scan()['notes'], [])
        path.unlink(); path.write_text('# Again'); self.book.scan()
        with patch.object(self.book, '_read', side_effect=PermissionError):
            scan = self.book.scan(); self.assertEqual(scan['notes'], []); self.assertEqual(scan['errors'], 1)
        self.book.root.rename(self.home/'disconnected')
        with self.assertRaises(FileNotFoundError): self.book.scan()

    def test_cache_failure_is_optional_and_private(self):
        import sqlite3,json
        from notes_index import cache_path
        self.book.scan(); path = cache_path(self.book)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with sqlite3.connect(path) as db:
            checksum,payload=json.loads(db.execute('SELECT value FROM notes').fetchone()[0])
            db.execute('UPDATE notes SET value=?',(json.dumps([checksum,payload.replace('One','Wrong')]),))
        db.close()
        self.assertEqual(self.book.scan()['notes'][0]['title'],'One')
        path.write_bytes(b'broken sqlite')
        self.assertEqual(self.book.scan()['notes'][0]['title'], 'One')
        path.unlink(); outside = self.home/'untouched'; outside.write_text('keep')
        path.symlink_to(outside)
        self.assertEqual(self.book.scan()['notes'][0]['title'], 'One')
        self.assertEqual(outside.read_text(), 'keep')

    def test_notebook_and_parser_boundaries(self):
        self.book.scan()
        other = Notebook(self.store,self.home/'second',create=True)
        (other.root/'one.md').write_text('# Other')
        self.assertEqual(other.scan()['notes'][0]['title'],'Other')
        with patch('notes_index.VERSION', 'next'), patch('wissen_data.parse', wraps=parse) as parser:
            self.book.scan(); self.assertEqual(parser.call_count,1)

    def test_exact_limits_are_complete_and_excess_is_explicit(self):
        with patch('wissen_data.MAX_SCAN_NOTES',1):
            self.assertFalse(self.book.scan()['limited'])
            (self.book.root/'two.md').write_text('# Two')
            self.assertTrue(self.book.scan()['limited'])
        total=sum(p.stat().st_size for p in self.book.root.glob('*.md'))
        with patch('wissen_data.MAX_SCAN_BYTES',total): self.assertFalse(self.book.scan()['limited'])
        with patch('wissen_data.MAX_SCAN_BYTES',total-1): self.assertTrue(self.book.scan()['limited'])
        with (self.book.root/'oversized.md').open('wb') as stream:stream.truncate(1024*1024+1)
        result=self.book.scan();self.assertEqual(len(result['notes']),2);self.assertEqual(result['errors'],1);self.assertFalse(result['limited'])

    def test_worker_compression_and_delta_keep_changes_and_deletions(self):
        import subprocess
        from wissen_data import worker
        class Job:
            def command(self,args,data,**ignored): return subprocess.check_output(args,input=data)
        def scan(**values):return worker(Job(),self.store,'scan',str(self.book.root),identity=self.book.identity,**values)
        initial=scan(); known={n['path']:[n['hash'],n['modified']] for n in initial['notes']}
        self.assertEqual(initial['notes'][0]['text'],self.book.read('one.md')['text'])
        delta=scan(known=known);self.assertEqual(delta['notes'],[]);self.assertEqual(delta['unchanged'],['one.md'])
        (self.book.root/'one.md').write_text('# Changed');(self.book.root/'new.md').write_text('# New')
        delta=scan(known=known);self.assertEqual(len(delta['notes']),2);self.assertEqual(delta['unchanged'],[])
        (self.book.root/'one.md').unlink()
        self.assertEqual([n['path'] for n in scan(known=known)['notes']],['new.md'])
        with patch('wissen_data.MAX_RESULT',10):
            with self.assertRaises(ValueError):scan()

    def test_link_index_matches_resolver_for_ambiguous_and_qualified_targets(self):
        from wissen_data import link_lookup,resolve_link,connections
        notes={p:parse(p,text.encode()) for p,text in {
            'Folder/One.md':'# One\n[[Two#Heading]]',
            'A/Two.md':'# Alias', 'B/Two.md':'# Another',
            'Unique.md':'# Only Title', 'Title.md':'# Two',
            'Ref.md':'# Ref\n[[Unique]] [[Only Title]] [[Absent]]'}.items()}
        lookup=link_lookup(notes)
        for origin in notes:
            for target in ['Two','One','Only Title','Other/Only Title','A/Two','Unique','Absent','../Unique','https://example.org','Two#Heading','/?document=']:
                self.assertEqual(resolve_link(origin,target,notes,lookup),resolve_link(origin,target,notes),(origin,target))
        outgoing,incoming=connections(notes)
        self.assertEqual(outgoing['Ref.md'],{'Unique.md'});self.assertEqual(incoming['Unique.md'],{'Ref.md'})

    def test_property_cache_changes_with_source(self):
        from wissen_data import search
        from notes_views import ordered
        note=parse('one.md',b'---\nstatus: open\ndue: 2026-10-14\n---\n# One')
        with patch('notes_properties.values',side_effect=AssertionError('Unchanged metadata reparsed')):
            self.assertEqual(search([note],'[status=open]'),[note]);self.assertEqual(ordered([note],'date'),[note])
        note['text']=note['text'].replace('open','closed')
        self.assertEqual(search([note],'[status=open]'),[]);self.assertEqual(search([note],'[status=closed]'),[note])

    def test_process_wait_keeps_output_bounds_timeout_and_cancellation(self):
        import sys,threading
        from lumen_jobs import Job
        from tools_data import Cancelled
        job=Job(lambda _:None)
        self.assertEqual(job.command([sys.executable,'-c','print("ready")']),b'ready\n')
        with self.assertRaises(ValueError):job.command([sys.executable,'-c','print("large")'],max_output=2)
        pid=self.home/'pid'
        command=[sys.executable,'-c',f'import os,time;open({str(pid)!r},"w").write(str(os.getpid()));time.sleep(60)']
        with self.assertRaises(ValueError):job.command(command,timeout=.05)
        with self.assertRaises(ProcessLookupError):os.kill(int(pid.read_text()),0)
        pid.unlink();timer=threading.Timer(.08,job.cancelled.set);timer.start()
        try:
            with self.assertRaises(Cancelled):job.command(command)
        finally:timer.cancel();timer.join()
        with self.assertRaises(ProcessLookupError):os.kill(int(pid.read_text()),0)


class IndexUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def wait(self,check):
        from PySide6.QtTest import QTest
        for _ in range(500):
            QTest.qWait(10)
            if check():return
        self.fail('Notes index UI timed out')

    def test_delta_keeps_selection_and_updates_links_without_losing_draft(self):
        from PySide6.QtCore import QEvent
        from tools_wissen import Wissen
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'LUMEN_DATA':root+'/state','XDG_CONFIG_HOME':root+'/config'}):
            w=Wissen(Path(root)/'tools');w.show()
            try:
                self.wait(lambda:w.book and not w.job and not w.poller);w.poll_timer.stop()
                a=w.book.create('One','[[Two]]');b=w.book.create('Two','Body');w.scanned(w.book.scan());w.show_note(b)
                item=w.note_items[b['path']];w.show_note(w.book.read(a['path']));w.show_note(w.book.read(b['path']))
                self.assertIs(w.note_items[b['path']],item);self.assertIs(w.entries.currentItem(),item)
                self.assertIn(a['path'],w.connections_index[1][b['path']])
                a=w.book.write(a['path'],'# One\nNo link',a['hash'])
                w.scanned(dict(notes=[a],unchanged=[b['path']],folders=[],errors=0,limited=False))
                self.assertEqual(len(w.notes),2);self.assertEqual(w.doc['path'],b['path']);self.assertNotIn(b['path'],w.connections_index[1])
                w.editor.appendPlainText('Local draft');w.autosave_timer.stop()
                b=w.book.write(b['path'],'# Two\nExternal edit',b['hash'])
                w.scanned(dict(notes=[b],unchanged=[a['path']],folders=[],errors=0,limited=False))
                self.assertTrue(w.conflict);self.assertIn('Local draft',w.editor.toPlainText())
                w.scanned(dict(notes=[],unchanged=[b['path']],folders=[],errors=0,limited=False))
                self.assertNotIn(a['path'],w.notes);self.assertIn('Local draft',w.editor.toPlainText())
                w.dirty=False
            finally:
                self.wait(lambda:not w.job and not w.poller and not w.live_preview.job);w.close();w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)


if __name__ == '__main__': unittest.main()
