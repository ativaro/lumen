import os
from pathlib import Path
import tempfile
import unittest
from lumen_store import Store
from wissen_data import Notebook,activate,search,resolve_link,draft,clear_draft,worker


class WissenTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.store=Store(self.root/'state')

    def test_timestamps_survive_edits_noop_restore_and_notebook_copy(self):
        import shutil
        from unittest.mock import patch
        activate(self.store);book=Notebook(self.store)
        with patch('wissen_data.time.time',return_value=1700000000):note=book.create('Timed','First')
        self.assertEqual(note['created'],1700000000);self.assertGreater(note['modified'],0)
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
        from wissen_data import timestamp_text,parse
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


class WissenNativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_visible_timestamps_follow_saved_note_and_memory_without_entering_editor(self):
        from unittest.mock import patch
        from PySide6.QtCore import QCoreApplication,QEvent
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QLabel
        from tools_wissen import Wissen
        from wissen_data import timestamp_text
        from lumen_i18n import tr
        def ready(window):
            for _ in range(300):
                QTest.qWait(20)
                if window.book and not window.job and not window.poller and not window.dirty:return
            self.fail('Notebook did not become idle')
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_DATA':tmp+'/state'}):
            window=Wissen(Path(tmp)/'tools');errors=[];window.error=errors.append;window.show();ready(window)
            try:
                with patch('wissen_data.time.time',return_value=1700000000):note=window.book.create('Timed','A thought')
                window.scanned(window.book.scan());window.open_note(note['path']);ready(window)
                self.assertTrue(window.timestamp.isVisible());self.assertEqual(window.timestamp.text(),timestamp_text(window.doc))
                self.assertNotIn('2023',window.editor.toPlainText())
                window.editor.appendPlainText('Edited');ready(window)
                self.assertEqual(window.doc['created'],1700000000);self.assertEqual(window.timestamp.text(),timestamp_text(window.book.read(note['path'])))
                external=window.book.root/'legacy.md';external.write_text('# Legacy\nAn old note');os.utime(external,(1700000200,1700000200))
                window.open_file(str(external));ready(window)
                self.assertIn(tr('Geändert: {0}',''),window.timestamp.text());self.assertNotIn(tr('Erstellt: {0}',''),window.timestamp.text())
                window.clear_note('No note');self.assertFalse(window.timestamp.isVisible())
                import lumen_memory
                memory=lumen_memory.Memory(window.store);entry=memory.remember('Preference','A saved preference',kind='preference')
                window.switch_area('lumen');ready(window);window.open_note(entry['path']);ready(window)
                self.assertTrue(window.timestamp.isVisible());self.assertIn(tr('Erstellt: {0}',''),window.timestamp.text())
                window.profile.update_notes(window.notes.values())
                self.assertTrue(any(tr('Erstellt: {0}','') in label.text() for label in window.profile.findChildren(QLabel)))
                self.assertFalse(errors,errors)
            finally:
                if window.job:window.job.wait(5000);self.app.processEvents()
                window.close();window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_note_loading_keeps_editor_geometry_stable(self):
        import threading
        from unittest.mock import patch
        from PySide6.QtCore import QPoint, QCoreApplication, QEvent
        from PySide6.QtTest import QTest
        import tools_wissen
        def ready(window):
            for _ in range(300):
                QTest.qWait(20)
                if window.book and not window.job and not window.poller: return
            self.fail('Notebook did not become idle')
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp+'/state'}):
            from appearance import apply_design
            old_style, old_palette, old_font = self.app.styleSheet(), self.app.palette(), self.app.font()
            apply_design(self.app, 'glass')
            window = tools_wissen.Wissen(Path(tmp)/'tools'); window.show(); ready(window)
            first = window.book.create('First', 'One')
            second = window.book.create('Second', 'Two')
            window.poll(); ready(window); window.open_note(first['path']); ready(window)
            def geometry():
                return (window.editor.mapTo(window, QPoint()), window.editor.size(), window.split.geometry())
            original = tools_wissen.data.worker
            gate = threading.Event()
            def slow_read(job, store, action, *args, **kwargs):
                if action == 'read': gate.wait(3)
                return original(job, store, action, *args, **kwargs)
            try:
                for width in (1180, 840):
                    window.resize(width, 800); QTest.qWait(50)
                    before = geometry(); gate.clear()
                    path = second['path'] if window.doc['path'] == first['path'] else first['path']
                    with patch.object(tools_wissen.data, 'worker', slow_read):
                        window.open_note(path); QTest.qWait(60)
                        loading = geometry()
                        self.assertTrue(window.progress.isVisible())
                        self.assertTrue(window.cancel_button.isVisible())
                        gate.set(); ready(window)
                    self.assertEqual(before, loading, 'Loading controls moved the notebook')
                    self.assertEqual(before, geometry(), 'Completing the load moved the notebook')
                    self.assertEqual(window.doc['path'], path)
            finally:
                gate.set(); ready(window); window.close(); window.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                self.app.setStyleSheet(old_style); self.app.setPalette(old_palette); self.app.setFont(old_font)


    def test_collection_button_and_link_picker_use_titles(self):
        from unittest.mock import patch
        from PySide6.QtCore import QCoreApplication,QEvent,Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QPushButton
        from tools_wissen import Wissen
        def ready(w):
            for _ in range(300):
                QTest.qWait(20)
                if w.book and not w.job and not w.poller and not w.dirty:return
            self.fail(w.status.text())
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_DATA':tmp+'/state'}):
            window=Wissen(Path(tmp)/'tools');window.show();ready(window)
            try:
                buttons=window.findChildren(QPushButton)
                create=next((b for b in buttons if b.accessibleName()=='Neue Sammlung'),None)
                self.assertIsNotNone(create,'Sammlungen brauchen eine sichtbare Aktion zum Anlegen')
                with patch('tools_wissen.QInputDialog.getText',return_value=('Projekte',True)):QTest.mouseClick(create,Qt.LeftButton)
                ready(window);self.assertEqual(window.collection,'folder:Projekte');self.assertEqual(window.entries.count(),0)
                window.scanned(window.book.scan());self.assertEqual(window.collection,'folder:Projekte')
                QTest.mouseClick(window.add_button,Qt.LeftButton);ready(window)
                self.assertEqual(Path(window.doc['path']).parent,Path('Projekte'))
                window.title.selectAll();QTest.keyClicks(window.title,'Quellnotiz');ready(window)
                targets=[]
                for title in ('Reiseplanung','Arbeitsplan','Arbeitsplan'):
                    note=window.book.create('Neue Notiz');targets.append(window.book.write(note['path'],'# '+title+'\n\nDetails',note['hash']))
                window.scanned(window.book.scan());chosen=targets[2]
                def choose(parent,title,label,choices,*args):
                    self.assertTrue(any('Reiseplanung' in c for c in choices))
                    self.assertEqual(len([c for c in choices if 'Arbeitsplan' in c]),2)
                    self.assertEqual(len(set(choices)),len(choices))
                    return next(c for c in choices if chosen['path'] in c),True
                with patch('tools_wissen.QInputDialog.getItem',side_effect=choose):window.insert_link()
                ready(window);note=window.book.read(window.doc['path'])
                self.assertEqual(resolve_link(note['path'],note['links'][0],window.notes),chosen['path'])
                window.toggle_view();ready(window)
                self.assertIn('Arbeitsplan',window.preview.toPlainText())
                window.toggle_view();path=window.doc['path'];window.editor.appendPlainText('Vor dem Sammlungswechsel erhalten')
                with patch('tools_wissen.QInputDialog.getText',return_value=('Noch leer',True)):
                    QTest.mouseClick(create,Qt.LeftButton);ready(window)
                window.scanned(window.book.scan());self.assertEqual(window.collection,'folder:Noch leer')
                self.assertIsNone(window.doc);self.assertEqual(window.entries.count(),0)
                self.assertIn('Vor dem Sammlungswechsel erhalten',window.book.read(path)['text'])
            finally:
                window.close();ready(window);window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_autosave_keeps_newer_typing_cursor_and_close(self):
        import threading
        from unittest.mock import patch
        from PySide6.QtCore import QCoreApplication,QEvent
        from PySide6.QtTest import QTest
        from tools_wissen import Wissen
        import wissen_data
        def wait(predicate):
            for _ in range(300):
                QTest.qWait(20)
                if predicate():return
            self.fail('Autosave did not finish')
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_DATA':tmp+'/state'}):
            window=Wissen(Path(tmp)/'tools');window.show();wait(lambda:window.book and not window.job and not window.poller)
            window.action('create',window.show_note,title='Autosave',text='Erster Gedanke');wait(lambda:window.doc and not window.job)
            path=window.doc['path'];entered=threading.Event();release=threading.Event();original=wissen_data.worker
            def slow(job,store,action,*args,**kwargs):
                if action=='write':entered.set();release.wait(3)
                return original(job,store,action,*args,**kwargs)
            with patch.object(wissen_data,'worker',side_effect=slow):
                window.editor.appendPlainText('Erste Ergänzung');wait(entered.is_set)
                self.assertTrue(window.editor.isEnabled());window.editor.insertPlainText(' und während des Speicherns weitergeschrieben')
                position=window.editor.textCursor().position();release.set();wait(lambda:not window.job and not window.dirty)
            self.assertIn('während des Speicherns',window.book.read(path)['text']);self.assertEqual(window.editor.textCursor().position(),position)
            other=window.book.create('Zweite Notiz','Ein weiterer Gedanke');window.scanned(window.book.scan());entered.clear();release.clear()
            with patch.object(wissen_data,'worker',side_effect=slow):
                window.editor.appendPlainText('Vor dem Wechsel erhalten');window.save_note();wait(entered.is_set)
                window.open_note(other['path']);release.set();wait(lambda:not window.job and window.doc['path']==other['path'])
            self.assertIn('Vor dem Wechsel erhalten',window.book.read(path)['text']);path=other['path']
            window.editor.appendPlainText('Beim Schließen ebenfalls erhalten');window.close();wait(lambda:not window.isVisible() and not window.job)
            self.assertIn('Beim Schließen ebenfalls erhalten',window.book.read(path)['text']);self.assertIsNone(draft(window.store,window.book.root,path))
            window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_direct_title_edit_frontmatter_collections_and_new_note(self):
        from unittest.mock import patch
        from PySide6.QtCore import QCoreApplication,QEvent,Qt
        from PySide6.QtTest import QTest
        from tools_wissen import Wissen
        def ready(w):
            for _ in range(300):
                QTest.qWait(20)
                if w.book and not w.job and not w.poller and not w.dirty:return
            self.fail(w.status.text())
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_DATA':tmp+'/state'}):
            window=Wissen(Path(tmp)/'tools');window.show();ready(window)
            QTest.mouseClick(window.add_button,Qt.LeftButton);ready(window)
            self.assertTrue(window.title.hasFocus());self.assertEqual(window.editor.toPlainText(),'')
            window.title.selectAll();QTest.keyClicks(window.title,'Arbeitsplan');window.editor.setPlainText('Ein Gedanke #ideen');ready(window)
            first=window.doc['path'];self.assertEqual(window.book.read(first)['text'],'# Arbeitsplan\n\nEin Gedanke #ideen')
            item=next(window.collections.item(i) for i in range(window.collections.count()) if window.collections.item(i).data(Qt.UserRole)=='tag:ideen')
            window.collections.setCurrentItem(item);self.assertEqual(window.entries.count(),1)
            window.details_button.click();self.assertTrue(window.rail.isVisible());window.details_button.click();self.assertFalse(window.rail.isVisible())
            frontmatter='---\ncategory: projekt\n---\n\n'
            for index,heading in enumerate(('# Alter Titel\n\n','')):
                path=window.book.root/f'import{index}.md';path.write_text(frontmatter+heading+'Originaler Inhalt')
                window.open_file(str(path));ready(window)
                self.assertEqual(window.document_text(),path.read_text())
                window.title.selectAll();QTest.keyClicks(window.title,'Neuer Titel');window.editor.appendPlainText('Erhalten');ready(window)
                saved=window.book.read(path.name)['text'];self.assertTrue(saved.startswith(frontmatter+'# Neuer Titel\n\n'));self.assertIn('Originaler Inhalt\nErhalten',saved)
                window.editor.appendPlainText('Weitere Bearbeitung');ready(window)
                self.assertEqual(window.book.read(path.name)['text'].count('# Neuer Titel'),1)
            window.close();ready(window);window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_explicit_mail_selection_capture(self):
        from unittest.mock import patch
        from PySide6.QtCore import QCoreApplication,QEvent
        from PySide6.QtGui import QTextCursor
        from PySide6.QtTest import QTest
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
        from PySide6.QtCore import QCoreApplication,QEvent,QUrl
        from PySide6.QtGui import QTextDocument
        from PySide6.QtTest import QTest
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
