import tempfile
import unittest
import os
from pathlib import Path
from lumen_store import Store
from wissen_data import Notebook,activate
from lumen_memory import Memory,stamp
from lumen_i18n import tr


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name);self.store=Store(self.base/'state');activate(self.store);self.notes=Notebook(self.store);self.memory=Memory(self.store)

    def test_identity_survives_reload_and_edit_but_isolates_profiles(self):
        self.memory.remember('Original','PostgreSQL')
        first=self.memory.scan()['notes'][0]
        again=Memory(self.store).scan()['notes'][0]
        self.assertEqual(first['id'],again['id'])
        self.memory.write(first['path'],'# Neuer Titel\nSQLite',first['hash'])
        edited=Memory(self.store).scan()['notes'][0]
        self.assertEqual(first['id'],edited['id'])
        self.assertNotEqual(first['revision'],edited['revision'])
        other=Memory(Store(self.base/'other'))
        self.assertNotEqual(first['id'],other.identity(first['path']))

    def test_private_notes_and_folder_overrides_project_scope(self):
        self.memory.configure(True,True)
        private=self.notes.create('Privat','Projekt geheimes Detail')
        shared=self.notes.create('Freigegeben','Projekt gemeinsamer Plan')
        global_note=self.memory.remember('Stil','Ich bevorzuge kurze Antworten.',kind='preference')
        self.memory.remember('Projektentscheidung','Projekt bleibt lokal.',scope=str(self.base/'one'))
        result=self.memory.prepare('Projekt',str(self.base/'two'))
        self.assertIn('kurze Antworten',result['context']);self.assertNotIn('geheimes',result['context']);self.assertNotIn('gemeinsamer',result['context']);self.assertNotIn('bleibt lokal',result['context'])
        self.memory.share('.',True,True);self.memory.share(private['path'],False)
        result=self.memory.prepare('Projekt',str(self.base/'one/sub'))
        self.assertNotIn('gemeinsamer Plan',result['context']);self.assertNotIn('geheimes',result['context']);self.assertIn('bleibt lokal',result['context'])
        before=stamp(self.store);self.memory.share(shared['path'],False);self.assertNotEqual(stamp(self.store),before)
        self.assertNotIn('gemeinsamer',self.memory.prepare('Projekt',str(self.base))['context'])
        self.assertEqual(self.notes.read(private['path'])['text'],private['text'])
        self.memory.configure(False,False);self.assertEqual(self.memory.prepare('Projekt',str(self.base))['context'],'')

    def test_learning_evidence_conflicts_deduplication_and_forget(self):
        self.memory.configure(True,True,automatic=True);user='Ich möchte kurze Antworten.'
        item=dict(title='Antwortlänge',text='Der Nutzer möchte kurze Antworten.',kind='preference',scope='global',evidence=user)
        revision=self.store.setting('memory/revision',0)
        self.assertEqual(self.memory.apply([item,item],user,str(self.base),'Gespräch 1',[],revision),1)
        note=self.memory.scan()['notes'][0];self.assertTrue(note['memory']['automatic']);self.assertEqual(note['memory']['evidence'],user)
        prepared=self.memory.prepare('Antworten',str(self.base))
        changed=dict(item,path=note['path'],text='Antworten sollen sehr kurz sein.')
        edited=self.memory.write(note['path'],'# Antwortlänge\nMeine Korrektur.',note['hash'])
        self.assertEqual(self.memory.apply([changed],user,str(self.base),'Gespräch 2',prepared['candidates'],self.store.setting('memory/revision',0)),0)
        self.assertIn('Meine Korrektur',self.memory.book.read(note['path'])['text'])
        self.memory.forget(note['path'],edited['hash']);self.assertEqual(self.memory.scan()['notes'],[]);self.assertEqual(self.memory.book.versions(note['path']),[])
        self.assertEqual(self.memory.apply([item],user,str(self.base),'Gespräch 3',[],self.store.setting('memory/revision',0)),0)
        self.assertEqual(self.memory.apply([dict(item,title='Geänderte Formulierung')],user,str(self.base),'Gespräch 3',[],self.store.setting('memory/revision',0)),0)
        self.assertEqual(Memory(self.store).prepare('Antworten',str(self.base))['context'],'')

    def test_invalid_or_stale_suggestions_and_path_boundaries(self):
        self.memory.configure(True,True);revision=self.store.setting('memory/revision',0)
        item=dict(title='Schriftart',text='Bevorzugt eine große Schrift.',kind='preference',scope='global',evidence='Ich mag große Schrift.')
        self.assertEqual(self.memory.apply([item],'Anderer Text',str(self.base),'Quelle',[],revision),0)
        self.assertEqual(self.memory.apply([dict(item,path='../outside.md')],item['evidence'],str(self.base),'Quelle',[],revision),0)
        self.memory.configure(True,False)
        self.assertEqual(self.memory.apply([item],item['evidence'],str(self.base),'Quelle',[],revision),0)
        self.memory.configure(True,True)
        self.assertEqual(self.memory.apply([item],item['evidence'],str(self.base),'Quelle',[],revision),0)
        for path in ('../','/tmp'):
            with self.assertRaises((ValueError,OSError)):self.memory.share(path,True,True)
        self.assertEqual(self.store.setting('memory/shares',[]),[])


if __name__=='__main__':unittest.main()
