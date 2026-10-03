import os
from pathlib import Path
import tempfile
import unittest
from lumen_store import Store
from wissen_data import Notebook,activate,search,resolve_link,draft,clear_draft,worker


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
        activate(self.store,str(book.root));self.assertEqual(Notebook(self.store).scan()['notes'],[])

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


class WissenNativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_explicit_mail_selection_capture(self):
        from unittest.mock import patch
        from PyQt5.QtCore import QCoreApplication,QEvent
        from PyQt5.QtGui import QTextCursor
        from PyQt5.QtTest import QTest
        from tools_inbox import Inbox
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_DATA':tmp+'/state'}):
            store=Store();activate(store);window=Inbox(Path(tmp)/'tools')
            try:
                window.message=dict(subject='Fundstelle',sender='test@example.invalid',sent='2026-10-03',body='Gewählte Stelle\nUngewählter Rest')
                window.reader.setPlainText(window.message['body']);cursor=window.reader.textCursor();cursor.setPosition(0);cursor.setPosition(len('Gewählte Stelle'),QTextCursor.KeepAnchor);window.reader.setTextCursor(cursor)
                window.capture_knowledge()
                for _ in range(150):
                    QTest.qWait(20)
                    if not window.job:break
                self.assertIsNone(window.job);note=store.memories()[0]
                self.assertIn('Gewählte Stelle',note['text']);self.assertNotIn('Ungewählter Rest',note['text']);self.assertIn('test@example.invalid',note['source'])
            finally:
                window.close();window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_native_edit_external_conflict_draft_sources_and_safe_preview(self):
        from unittest.mock import patch
        from PyQt5.QtCore import QCoreApplication,QEvent,QUrl
        from PyQt5.QtGui import QTextDocument
        from PyQt5.QtTest import QTest
        from tools_wissen import Wissen
        from PIL import Image
        def ready(window,predicate=lambda:True):
            for _ in range(200):
                QTest.qWait(20)
                if window.book and not window.job and not window.poller and predicate():return
            self.fail('Wissen not ready: '+window.status.text())
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_DATA':tmp+'/state'}):
            window=Wissen(Path(tmp)/'tools');window.show();ready(window)
            window.action('create',window.show_note,title='Plan',text='Eine erste Idee #projekt');ready(window,lambda:window.doc is not None)
            path=window.doc['path'];window.editor.appendPlainText('Mein neuer Gedanke');window.save_note();ready(window)
            self.assertIn('Mein neuer Gedanke',window.book.read(path)['text'])
            window.editor.appendPlainText('Ein lokaler Entwurf');window.save()
            (window.book.root/path).write_text('# Externe Fassung\nNicht überschreiben.')
            window.scanned(window.book.scan());self.assertTrue(window.conflict);self.assertIn('lokaler Entwurf',window.editor.toPlainText())
            window.save_copy();ready(window);self.assertIn('Externe Fassung',window.book.read(path)['text'])
            self.assertIn('lokaler Entwurf',window.doc['text'])
            image=Path(tmp)/'picture.png';Image.new('RGB',(40,30),'red').save(image);asset=window.book.add_image(image)
            window.editor.appendPlainText('![Bild]('+asset+')');window.toggle_view();ready(window,lambda:window.views.currentIndex()==1)
            self.assertIsNotNone(window.preview.loadResource(QTextDocument.ImageResource,QUrl.fromLocalFile(str(window.book.root/asset))))
            self.assertIsNone(window.preview.loadResource(QTextDocument.ImageResource,QUrl('https://example.test/tracker.png')))
            self.assertIsNone(window.preview.loadResource(QTextDocument.ImageResource,QUrl.fromLocalFile(str(image))))
            window.toggle_view()
            window.scanned(window.book.scan());window.question.setText('lokaler Entwurf');window.find_sources()
            with patch.object(window,'ai') as ai:
                window.ask();ready(window,lambda:ai.called);self.assertIn('lokaler Entwurf',ai.call_args.args[0]);self.assertIn('untrusted data',ai.call_args.args[0])
            window.answered('{"answer":"Eine Idee [1]."}');window.tabs.setCurrentIndex(2);self.assertGreater(len(window.map.scene().items()),0)
            window.editor.appendPlainText('Entwurf für Neustart');window.save();window.conflict=True;window.close();window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
            again=Wissen(Path(tmp)/'tools');again.show();ready(again,lambda:again.doc is not None)
            self.assertIn('Entwurf für Neustart',again.editor.toPlainText());again.conflict=True;again.close();again.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


if __name__=='__main__':unittest.main()
