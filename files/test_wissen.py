import os
from pathlib import Path
import tempfile
import unittest
from lumen_store import Store
from wissen_data import Notebook,activate,draft,clear_draft,worker
from notes_query import search,resolve_link


class WissenTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.store=Store(self.root/'state')

    def test_notebook_mount_number_change_keeps_identity_but_replacement_fails(self):
        activate(self.store);book=Notebook(self.store)
        note=book.create('Keep','Body')
        fd=os.open(book.root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            # The file system's ID, as Python's os.fstatvfs read it into the stored identities.
            original=os.fstat(fd);fsid=os.fstatvfs(fd).f_fsid
            self.assertEqual(book.identity,['fsid:'+str(fsid),original.st_ino] if fsid else [original.st_dev,original.st_ino])
        finally:os.close(fd)
        self.assertEqual(len(Notebook(self.store,identity=[original.st_dev,original.st_ino]).scan()['notes']),1)
        with self.assertRaises(ValueError):Notebook(self.store,identity=[original.st_dev+1,original.st_ino]).scan()
        book.create_collection('Original');book.rename_collection('Original','Renamed')
        self.assertIn('Renamed',book.scan()['folders'])
        renamed=book.root.with_name('old-notebook');book.root.rename(renamed);book.root.mkdir()
        with self.assertRaises(ValueError):book.scan()
        self.assertTrue((renamed/note['path']).exists())

    def test_timestamps_survive_edits_noop_restore_and_notebook_copy(self):
        import shutil
        import time
        activate(self.store);book=Notebook(self.store)
        before=time.time();note=book.create('Timed','First')
        self.assertLessEqual(before,note['created']);self.assertLessEqual(note['created'],time.time());self.assertGreater(note['modified'],0)
        same=book.write(note['path'],note['text'],note['hash'])
        self.assertEqual(same['hash'],note['hash']);self.assertEqual(same['modified'],note['modified']);self.assertEqual(book.versions(),[])
        edited=book.write(note['path'],'# Timed\n\nSecond',note['hash'])
        self.assertEqual(edited['created'],note['created'])
        restored=book.restore(book.versions()[0]['id'],edited['hash']);self.assertEqual(restored['created'],note['created'])
        removed=book.remove(note['path'],restored['hash']);restored=book.restore(removed,'');self.assertEqual(restored['created'],note['created'])
        copied=self.root/'copy';shutil.copytree(book.root,copied)
        self.assertEqual(Notebook(self.store,copied).read(note['path'])['created'],note['created'])

    def test_existing_note_timestamp_is_read_only_and_frontmatter_stays_intact(self):
        activate(self.store);book=Notebook(self.store);path=book.root/'external.md'
        original='---\ntopic: example\n---\n\n# Existing\n\nKeep'
        path.write_text(original);os.utime(path,(1700000100,1700000100))
        note=book.read(path.name);self.assertEqual(note['created'],0);self.assertEqual(note['modified'],1700000100)
        self.assertEqual(book.scan()['notes'][0]['modified'],1700000100);self.assertEqual(path.read_text(),original)
        updated=book.write(path.name,original+'\nMore',note['hash'])
        self.assertEqual(updated['created'],0);self.assertTrue(path.read_text().startswith('---\ntopic: example'))

    def test_timestamp_labels_distinguish_known_creation_from_legacy_modification(self):
        from wissen_data import parse
        from notes_query import timestamp_text
        from lumen_i18n import tr
        self.assertIn(tr('Erstellt: {0}',''),timestamp_text(dict(created=1700000000,modified=1700000000)))
        self.assertIn(tr('Geändert: {0}',''),timestamp_text(dict(created=0,modified=1700000000)))
        self.assertIn(tr('Erstellt: {0}',''),timestamp_text(dict(modified=1700000000,memory=dict(created=1600000000))))
        for value in ('yesterday',True,-1,float('inf'),1e100):
            import json
            raw=('<!-- lumen: '+json.dumps(dict(created=value))+' -->\n# Safe').encode()
            self.assertEqual(parse('safe.md',raw)['created'],0)

    def test_migration_repeat_late_edits_and_deleted_notes(self):
        old=self.store.save_memory('Bücher','Eine Fundstelle','Reader Seite 2')
        activate(self.store);book=Notebook(self.store);notes=book.scan()['notes'];self.assertEqual(len(notes),1)
        self.assertIn('Eine Fundstelle',notes[0]['text']);self.assertEqual(notes[0]['source'],'Reader Seite 2')
        self.assertEqual(book.migrate(),0)
        book.write(notes[0]['path'],'# Eigener Text\n\nNicht überschreiben',notes[0]['hash'])
        with self.store.connect() as db:db.execute('UPDATE memories SET text=?,updated=updated+1 WHERE id=?',('Späte alte Sitzung',old))
        self.assertEqual(book.migrate(),1);self.assertEqual(len(book.scan()['notes']),2)
        for n in book.scan()['notes']:book.remove(n['path'],n['hash'])
        self.assertEqual(book.migrate(),0);self.assertEqual(book.scan()['notes'],[])
        self.assertEqual(len(self.store.rows('SELECT * FROM memories')),1)

    def test_conflicts_history_external_changes_and_portable_content(self):
        activate(self.store);book=Notebook(self.store);a=book.create('Über Bücher','Text #lesen\n[[Ideen]]')
        b=book.create('Ideen','Ein verknüpfter Gedanke #lesen')
        notes={n['path']:n for n in book.scan()['notes']}
        self.assertEqual(resolve_link(a['path'],'Ideen',notes),b['path']);self.assertEqual(a['tags'],['lesen'])
        self.assertEqual(search(list(notes.values()),'verknüpfter Gedanke')[0]['path'],b['path'])
        external=book.root/a['path'];external.write_text('# Fremde Änderung\nBleibt erhalten',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'CONFLICT'):book.write(a['path'],'Entwurf',a['hash'])
        draft(self.store,book.root,a['path'],'Entwurf',a['hash']);self.assertEqual(draft(self.store,book.root,a['path'])['text'],'Entwurf')
        updated=book.write(a['path'],'# Aktualisiert',book.read(a['path'])['hash']);versions=book.versions(a['path'])
        restored=book.restore(versions[0]['id'],updated['hash']);self.assertIn('Fremde Änderung',restored['text'])
        key=book.remove(a['path'],restored['hash']);self.assertFalse(external.exists());book.restore(key,'');self.assertTrue(external.exists())
        clear_draft(self.store,book.root,a['path']);self.assertIsNone(draft(self.store,book.root,a['path']))

    def test_path_limits_symlinks_and_missing_folder(self):
        activate(self.store);book=Notebook(self.store);outside=self.root/'outside.md';outside.write_text('private')
        (book.root/'link.md').symlink_to(outside);(book.root/'elsewhere').symlink_to(self.root,target_is_directory=True)
        self.assertEqual(book.scan()['notes'],[])
        for path in ('../outside.md','link.md','elsewhere/outside.md','/outside.md'):
            with self.assertRaises((OSError,ValueError)):book.write(path,'changed','')
        self.assertEqual(outside.read_text(),'private')
        book.root.rename(self.root/'disconnected')
        with self.assertRaises(FileNotFoundError):book.scan()
        book.root.mkdir()
        with self.assertRaises(ValueError):book.scan()
        activate(self.store,str(book.root));self.assertEqual(Notebook(self.store).scan()['notes'],[])

    def test_empty_collections_persist_and_notes_stay_inside(self):
        activate(self.store);book=Notebook(self.store)
        folder=book.create_collection('Projekte')
        self.assertEqual(Notebook(self.store).scan()['folders'],['Projekte'])
        note=book.create('Projektplan',folder=folder)
        self.assertEqual(Path(note['path']).parent,Path('Projekte'))
        book.remove(note['path'],note['hash'])
        self.assertEqual(book.scan()['folders'],['Projekte'])
        with self.assertRaises(FileExistsError):book.create_collection('Projekte')
        outside=self.root/'outside';outside.mkdir();(book.root/'linked').symlink_to(outside,target_is_directory=True)
        for name in ('','../outside','/outside','Unter/Ordner','.hidden','attachments'):
            with self.assertRaises(ValueError):book.create_collection(name)
        for folder in ('../outside','linked'):
            with self.assertRaises((OSError,ValueError)):book.create('Privat',folder=folder)
        self.assertEqual(list(outside.iterdir()),[])

    def test_store_capture_fresh_context_and_relative_links(self):
        from tools_ui import Job
        old=self.store.save_memory('Alt','Alte Erinnerung');activate(self.store);book=Notebook(self.store)
        path=book.memory_path(old);self.store.save_memory('Überarbeitet','Neue Erinnerung',memory=old)
        self.assertIn('Neue Erinnerung',book.read(path)['text'])
        key=worker(Job(lambda _:None),self.store,'save_memory',title='Fundstelle',text='Text aus der Mail',source='Mail · Beispiel')
        self.assertEqual(book.read(key)['source'],'Mail · Beispiel')
        external=book.root/'Extern.md';external.write_text('---\ntopic: Idee\n---\n# Extern\n'+('Andere Sätze. '*600)+'Nadel: wichtige Fundstelle.')
        note=book.read('Extern.md');edited=book.write('Extern.md',note['text']+'\n#recherche',note['hash'])
        self.assertTrue(edited['text'].startswith('---\ntopic: Idee'))
        self.assertTrue(external.read_text().startswith('---\ntopic: Idee'))
        context=book.context(['Extern.md'],'Nadel');self.assertIn('Nadel',context[0]['text']);self.assertLess(len(context[0]['text']),3100)
        external.write_text('# Extern\nFrisch bearbeitet');self.assertIn('Frisch bearbeitet',book.context(['Extern.md'],'Nadel')[0]['text'])
        with self.assertRaises(ValueError):book.context(['Extern.md']*9,'Frage')
        notes={n['path']:n for n in book.scan()['notes']}
        self.assertEqual(resolve_link('ordner/a.md','../Extern.md',notes),'Extern.md')
        self.assertIsNone(resolve_link('a.md','../../Extern.md',notes))
        self.store.delete_memory(old);self.assertFalse((book.root/path).exists())
