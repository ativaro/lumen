"""Portable identity and forgetting across copies, renames and interrupted migration."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lumen_memory import Memory
from lumen_store import Store


class MemoryMigrationTest(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.store=Store(self.root/'state');self.memory=Memory(self.store)
        self.memory.configure(True,True)

    def test_legacy_preview_repeat_and_scope_after_rename(self):
        note=self.memory.book.create('Legacy','A durable choice')
        self.store.set_setting('memory/records',{note['path']:dict(kind='decision',scope='/project-a',
            automatic=False,hash=note['hash'],evidence='User said so')})
        original=self.memory.scan()['notes'][0]
        raw=self.memory.book.raw(note['path'])
        self.assertEqual(self.memory.migrate()['pending'],1)
        self.assertEqual(raw,self.memory.book.raw(note['path']))
        self.assertEqual(self.memory.migrate(False)['changed'],1)
        self.assertEqual(self.memory.migrate(False)['changed'],0)
        migrated=self.memory.scan()['notes'][0]
        self.assertEqual(original['id'],migrated['id'])
        self.assertEqual(migrated['note_id'],original['id'])
        self.assertEqual(len(self.memory.book.versions()),1)
        (self.memory.book.root/note['path']).rename(self.memory.book.root/'renamed.md')
        moved=self.memory.scan()['notes'][0]
        self.assertEqual(moved['id'],original['id'])
        self.assertEqual(self.memory.eligible('/project-b'),[])
        self.assertEqual(len(self.memory.eligible('/project-a')),1)
        edited=self.memory.write('renamed.md','# Renamed\nUpdated choice',moved['hash'])
        self.assertEqual(edited['id'],original['id'])
        self.assertEqual(edited['memory']['scope'],'/project-a')

    def test_copied_id_is_not_ambiguous_context_and_forgetting_survives_restored_file(self):
        note=self.memory.remember('Preference','Concise answers',kind='preference')
        saved=self.memory.book.raw(note['path'])
        copy=self.memory.book.root/'copy.md';copy.write_bytes(saved)
        self.assertEqual(self.memory.eligible(str(self.root)),[])
        copy.unlink()
        self.assertEqual(len(self.memory.eligible(str(self.root))),1)
        self.memory.forget(note['path'],note['hash'])
        copy.write_bytes(saved.replace(b'Concise answers',b'Changed old backup'))
        self.assertEqual(self.memory.scan()['notes'],[])
        with self.assertRaises(ValueError):
            self.memory.write('copy.md','# New title\nOther body',self.memory.book.read('copy.md')['hash'])
        marker=self.store.setting('memory/tombstones')[note['id']]
        self.assertEqual(set(marker),{'revision','forgotten'})
        new=self.memory.remember('Preference','Concise answers',kind='preference')
        self.assertNotEqual(note['id'],new['id'])
        self.assertEqual([n['id'] for n in self.memory.eligible(str(self.root))],[new['id']])

    def test_interrupted_migration_keeps_scope_and_manual_protection(self):
        note=self.memory.book.create('Legacy','Private project')
        self.store.set_setting('memory/records',{note['path']:dict(scope='/project-a',automatic=False,hash=note['hash'])})
        save=self.memory.save_record
        calls=[]
        def interrupt(*args):
            calls.append(1)
            if len(calls)==2:raise OSError('Synthetic interrupted metadata commit')
            return save(*args)
        with patch.object(self.memory,'save_record',side_effect=interrupt):
            with self.assertRaises(OSError):self.memory.migrate(False)
        (self.memory.book.root/note['path']).rename(self.memory.book.root/'renamed.md')
        reloaded=Memory(self.store)
        self.assertEqual(reloaded.migrate(False)['changed'],0)
        self.assertEqual(reloaded.eligible('/project-b'),[])
        current=reloaded.eligible('/project-a')[0]
        self.assertFalse(current['memory']['automatic'])
        self.assertEqual(current['memory']['scope'],'/project-a')


if __name__=='__main__':unittest.main()
