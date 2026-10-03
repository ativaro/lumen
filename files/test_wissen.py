import os
from pathlib import Path
import tempfile
import unittest
from lumen_store import Store
from wissen_data import Notebook,activate,search,resolve_link,draft,clear_draft


class WissenTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.store=Store(self.root/'state')

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


if __name__=='__main__':unittest.main()
