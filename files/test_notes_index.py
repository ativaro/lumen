import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lumen_store import Store
from wissen_data import Notebook, parse


class IndexTest(unittest.TestCase):
    """Scans of the notebook core (native/service/src/notebook.rs; its limits are tested there)."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name); self.store = Store(self.home/'state')
        self.book = Notebook(self.store, self.home/'notes', create=True)
        (self.book.root/'one.md').write_text('# One\n#test\nGrüße 🌍 漢字')

    def test_scan_reads_current_bytes_and_keeps_no_parse_cache(self):
        first = self.book.scan()
        self.assertEqual(Notebook(self.store,self.book.root).scan(), first)
        path = self.book.root/'one.md'; stamp = path.stat()
        path.write_text('# Two\n#test\nGrüße 🌍 漢字'); os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        self.assertEqual(self.book.scan()['notes'][0]['title'], 'Two')
        self.assertEqual(list(self.store.directory.glob('notes-index-*')), [])

    def test_deleted_symlink_unreadable_and_offline(self):
        self.book.scan(); path = self.book.root/'one.md'; path.unlink()
        self.assertEqual(self.book.scan()['notes'], [])
        path.symlink_to(self.home/'outside.md'); (self.home/'outside.md').write_text('# Secret')
        self.assertEqual(self.book.scan()['notes'], [])
        path.unlink(); path.write_text('# Again'); path.chmod(0)
        scan = self.book.scan(); self.assertEqual(scan['notes'], []); self.assertEqual(scan['errors'], 1)
        path.chmod(0o600)
        with (self.book.root/'oversized.md').open('wb') as stream:stream.truncate(1024*1024+1)
        result=self.book.scan();self.assertEqual(len(result['notes']),1);self.assertEqual(result['errors'],1);self.assertFalse(result['limited'])
        self.book.root.rename(self.home/'disconnected')
        with self.assertRaises(FileNotFoundError): self.book.scan()

    def test_worker_delta_keeps_changes_and_deletions(self):
        from wissen_data import worker
        class Job:
            def check(self): pass
        def scan(**values):return worker(Job(),self.store,'scan',str(self.book.root),identity=self.book.identity,**values)
        initial=scan(); known={n['path']:[n['hash'],n['modified']] for n in initial['notes']}
        self.assertEqual(initial['notes'][0]['text'],self.book.read('one.md')['text'])
        delta=scan(known=known);self.assertEqual(delta['notes'],[]);self.assertEqual(delta['unchanged'],['one.md'])
        (self.book.root/'one.md').write_text('# Changed');(self.book.root/'new.md').write_text('# New')
        delta=scan(known=known);self.assertEqual(len(delta['notes']),2);self.assertEqual(delta['unchanged'],[])
        (self.book.root/'one.md').unlink()
        self.assertEqual([n['path'] for n in scan(known=known)['notes']],['new.md'])

    def test_link_index_matches_resolver_for_ambiguous_and_qualified_targets(self):
        from notes_query import link_lookup,resolve_link,connections
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
        from notes_query import search
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



if __name__ == '__main__': unittest.main()
