"""Real offline Chromium + native notebook, exclusively disposable profiles."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from appearance import apply_design


class NotesWebTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        apply_design(cls.app,'graphite')

    def wait(self, check):
        for _ in range(600):
            QTest.qWait(20)
            if check(): return
        self.fail('Notes web timed out')

    def js(self, script):
        result=[]
        self.w.notes_web.page().runJavaScript(script,lambda value:result.append(value))
        self.wait(lambda:bool(result))
        return result[0]

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        root=self.temp.name
        self.env=patch.dict(os.environ,{'LUMEN_DATA':root+'/data','XDG_CONFIG_HOME':root+'/config','LUMEN_LANGUAGE':'de'})
        self.env.start()
        from tools_wissen import Wissen
        self.w=Wissen(Path(root)/'tools');self.w.show()
        self.wait(lambda:self.w.book and not self.w.job and not self.w.poller)
        self.w.poll_timer.stop()
        self.first=self.w.book.create('Schreibprobe','## Willkommen\n\nDirekt **formatiert** schreiben.\n\n| Aufgabe | Status |\n| --- | --- |\n| Entwurf | In Arbeit |')
        self.second=self.w.book.create('Zweite Notiz','Anderer Inhalt')
        self.w.scanned(self.w.book.scan());self.w.show_note(self.first)
        self.wait(lambda:self.js("!!document.querySelector('[contenteditable=true]')"))
        self.w.autosave_timer.stop()

    def tearDown(self):
        w=self.w
        self.wait(lambda:not w.job and not w.poller and not w.live_preview.job)
        w.conflict=False;w.close()
        self.wait(lambda:not w.isVisible())
        w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
        self.env.stop();self.temp.cleanup()

    def type_end(self,text):
        self.js("(()=>{let el=document.querySelector('[contenteditable=true]');el.focus();let range=document.createRange();range.selectNodeContents(Array.from(el.querySelectorAll('p')).at(-1)||el);range.collapse(false);let selection=getSelection();selection.removeAllRanges();selection.addRange(range);document.execCommand('insertText',false,"+json.dumps(text)+");})()")
        self.wait(lambda:text in self.w.editor.toPlainText())

    def test_list_spacing_and_preview_does_not_repeat_note_title(self):
        self.w.resize(1440,960);QTest.qWait(100)
        row="Array.from(document.querySelectorAll('.doc-row')).find(e=>e.querySelector('strong')?.textContent==='Schreibprobe')"
        preview=self.js(f"({row}).querySelector('small').textContent")
        self.assertNotIn('Schreibprobe',preview)
        self.assertIn('Willkommen',preview)
        self.assertEqual(self.js("document.querySelector('.knowledge-notes').getBoundingClientRect().width"),210)
        self.assertGreaterEqual(self.js("parseFloat(getComputedStyle(document.querySelector('.knowledge-note-list')).gap)"),8)
        self.js(f"({row}).click()")
        self.wait(lambda:self.w.doc['path']==self.first['path'])
        self.assertIn('# Schreibprobe',self.w.book.read(self.first['path'])['text'])

    def test_panorama_link_tag_and_document_layout(self):
        from appearance_tokens import RADII
        w=self.w;w.resize(960,640)
        w.resize(1280,800);QTest.qWait(80)
        self.assertEqual(self.js("document.querySelector('.knowledge-notes').getBoundingClientRect().width"),210)
        self.assertTrue(self.js("(()=>{let tops=[...document.querySelectorAll('.note-format-bar button')].map(b=>b.getBoundingClientRect().top);return Math.max(...tops)-Math.min(...tops)<=2;})()"))
        w.resize(960,640)
        self.type_end(' ungespeicherter Panorama-Entwurf')
        draft=w.editor.toPlainText()
        self.js("document.querySelector('button[aria-label=\"Link bearbeiten\"]').click()")
        gap=self.js("(()=>{const label=document.querySelector('.note-link-form label'),range=document.createRange();range.selectNode(label.firstChild);return label.querySelector('input').getBoundingClientRect().top-range.getBoundingClientRect().bottom;})()")
        self.assertGreaterEqual(gap,8)
        self.assertTrue(self.js("(()=>{let form=document.querySelector('.note-link-form'),bottom=form.querySelector('input').getBoundingClientRect().bottom;return [...form.querySelectorAll('button')].every(b=>Math.abs(b.getBoundingClientRect().bottom-bottom)<=1);})()"))
        self.assertTrue(self.js("(()=>{const form=document.querySelector('.note-link-form'),r=form.getBoundingClientRect();return [...form.querySelectorAll('button')].every(b=>b.scrollWidth<=b.clientWidth+1&&b.getBoundingClientRect().right<=r.right+1);})()"))
        self.js("document.querySelector('.note-link-form button[type=button]').click()")
        tag='projekt/'+('datenschutzfolgenabschaetzungundverarbeitungsverzeichnis'*3)
        w.note_tags.change(tag,True);w.autosave_timer.stop()
        self.wait(lambda:self.js("!!document.querySelector('.note-tag')"))
        self.assertTrue(self.js("(()=>{let pane=document.querySelector('.knowledge-editor');return pane.scrollWidth<=pane.clientWidth+1;})()"))
        self.assertTrue(self.js("(()=>{let tag=document.querySelector('.note-tag'),button=tag.querySelector('button');return button.getBoundingClientRect().right<=tag.getBoundingClientRect().right&&button.getBoundingClientRect().width>=24;})()"))
        self.js("document.querySelector('.note-tag button').click()")
        self.wait(lambda:not self.js("!!document.querySelector('.note-tag')"))
        for theme in ('glass','atelier','midnight','graphite'):
            apply_design(self.app,theme)
            self.wait(lambda:self.js("getComputedStyle(document.documentElement).getPropertyValue('--text').trim()")==self.app.palette().text().color().name())
            self.assertEqual(self.js("parseFloat(getComputedStyle(document.querySelector('.knowledge-editor')).paddingLeft)"),24)
            self.assertEqual(self.js("parseFloat(getComputedStyle(document.querySelector('.note-rich-text')).paddingLeft)"),24)
            self.assertEqual(self.js("parseFloat(getComputedStyle(document.querySelector('.note-format-bar')).borderTopLeftRadius)"),RADII[theme])
            self.assertEqual(w.editor.toPlainText(),draft)

    def test_web_editor_tables_tags_save_and_responsive_layout(self):
        w=self.w
        self.assertNotIn('**',self.js("document.querySelector('[contenteditable]').innerText"))
        from appearance_tokens import COLORS
        for theme in ('graphite', 'atelier', 'glass', 'midnight', 'graphite'):
            apply_design(self.app, theme)
            self.wait(lambda:self.js("getComputedStyle(document.documentElement).getPropertyValue('--text').trim()")==COLORS[theme][3])
            self.assertEqual(self.js("getComputedStyle(document.documentElement).getPropertyValue('--surface').trim()"),COLORS[theme][1])
            self.assertIn('Direkt formatiert schreiben.',self.js("document.querySelector('[contenteditable]').innerText"))
        for width in (1440,1180,840):
            w.resize(width,960);QTest.qWait(80)
            self.assertEqual(w.width(),width)
            self.assertFalse(self.js('document.documentElement.scrollWidth>innerWidth+1'))
        w.resize(1440,960)
        self.js("document.querySelector('.note-rich-text td p').focus(); let r=document.createRange();r.selectNodeContents(document.querySelector('.note-rich-text td p'));r.collapse(true);getSelection().removeAllRanges();getSelection().addRange(r);document.dispatchEvent(new Event('selectionchange'))")
        self.wait(lambda:self.js("!!document.querySelector('[aria-label=\"Tabelle bearbeiten\"]')"))
        self.js("Array.from(document.querySelectorAll('button')).find(x=>x.textContent==='Spalte hinzufügen').click()")
        self.wait(lambda:self.js("document.querySelector('.note-rich-text tr').children.length")==3)
        bridge=w.notes_web_objects[0];state=json.loads(bridge.snapshot())
        bridge.command(json.dumps(dict(action='tag',id=w.doc['path'],epoch=state['epoch'],tag='projekt/test',checked=True)))
        self.wait(lambda:self.js("document.querySelector('.note-tags-editor').textContent.includes('#projekt/test')"))
        self.type_end(' Neue Eingabe')
        self.js("document.querySelector('button[aria-label=Rückgängig]').click()")
        self.wait(lambda:'Neue Eingabe' not in w.document_text())
        self.js("document.querySelector('button[aria-label=Wiederholen]').click()")
        self.wait(lambda:'Neue Eingabe' in w.document_text())
        self.js("document.querySelector('.knowledge-save button').click()")
        self.wait(lambda:not w.job and not w.dirty)
        saved=w.book.read(self.first['path'])
        self.assertIn('Neue Eingabe',saved['text']);self.assertIn('projekt/test',saved['tags'])
        header=next(line for line in saved['text'].splitlines() if line.startswith('|'))
        cells=[cell.strip() for cell in header.strip('|').split('|')]
        self.assertEqual(len(cells),3);self.assertIn('',cells);self.assertIn('Status',cells)
        w.show_note(saved);QTest.qWait(250)
        self.assertEqual(self.js("document.querySelector('.note-rich-text tr').children.length"),3)
        if os.environ.get('LUMEN_NOTES_SCREENSHOTS'):
            for width in (1440,1180,840):
                w.resize(width,960);QTest.qWait(100);w.grab().save(str(Path(os.environ['LUMEN_NOTES_SCREENSHOTS'])/f'notes-web-{width}.png'))

    def test_stale_edit_conflict_and_close_preserve_latest_browser_input(self):
        w=self.w;bridge=w.notes_web_objects[0]
        old=json.loads(bridge.snapshot())
        w.show_note(self.second);bridge.publish();QTest.qWait(250)
        bridge.command(json.dumps(dict(action='edit',id=self.first['path'],epoch=old['epoch'],sequence=99,title='Stale',body='STALE')))
        self.assertEqual(w.doc['path'],self.second['path']);self.assertNotIn('STALE',w.document_text())
        self.type_end(' Ungespeichert');w.autosave_timer.stop()
        latest=w.book.read(self.second['path']);w.book.write(latest['path'],latest['text']+'\n\nExtern',latest['hash'])
        w.save_note();self.wait(lambda:not w.job)
        self.assertTrue(w.conflict);self.assertIn('Ungespeichert',w.document_text())
        self.assertNotIn('Ungespeichert',w.book.read(latest['path'])['text'])
        from PySide6.QtWidgets import QMessageBox
        with patch('tools_wissen.QMessageBox.question',return_value=QMessageBox.Yes): w.reload_external()
        self.wait(lambda:not w.job);QTest.qWait(300)
        self.type_end(' Zuletzt')
        self.js("document.querySelector('[contenteditable=true]').focus();document.execCommand('insertText',false,' vor Schließen')")
        w.close();self.wait(lambda:not w.isVisible())
        self.assertIn('vor Schließen',w.book.read(latest['path'])['text'])

    def test_offline_navigation_and_native_tools_remain_available(self):
        w=self.w
        original=w.notes_web.url()
        from PySide6.QtCore import QUrl
        self.assertFalse(w.notes_web.page().acceptNavigationRequest(QUrl('https://example.invalid/'),0,True))
        self.assertEqual(w.notes_web.url(),original)
        w.tabs.setCurrentIndex(w.sources_tab);self.assertFalse(w.notes_web.isVisible())
        w.tabs.setCurrentIndex(0);self.assertTrue(w.notes_web.isVisible())
        self.type_end(' Thema')
        before=w.document_text()
        for theme in ('atelier','midnight','graphite'):
            apply_design(self.app,theme);QTest.qWait(200)
            self.assertEqual(w.document_text(),before)
            self.assertTrue(self.js("document.querySelector('[contenteditable=true]').textContent.includes('Thema')"))
