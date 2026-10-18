"""Real app chrome and keyboard menus agree; all data stays in disposable profiles."""
import os
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt, QPoint, QCoreApplication, QEvent
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolBar, QMenu
from appearance import apply_design
from desktop_design import AppHeader


class DesktopDesignTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([]);cls.app.setStyle('Fusion')

    def wait(self, predicate):
        for _ in range(500):
            QTest.qWait(20)
            if predicate():return
        self.fail('Native app did not settle')

    def js(self, script):
        result=[];self.notes.notes_web.page().runJavaScript(script,lambda value:result.append(value))
        self.wait(lambda:bool(result));return result[0]

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        from tools_wissen import Wissen
        from tools_workbench import Workbench
        from code_library_window import CollectionWindow
        from tools_meeting_radio import MeetingRadio
        from lumen_store import Store
        self.notes=Wissen(self.root/'notes');self.projects=Workbench(self.root/'projects');self.code=CollectionWindow(Store(self.root/'code'))
        self.audio=MeetingRadio(root=self.root/'audio')
        self.windows=[('notes',self.notes),('projects',self.projects),('code',self.code),('audio',self.audio)]
        self.wait(lambda:self.notes.book and not self.notes.job and not self.notes.poller)
        self.notes.poll_timer.stop()
        self.wait(lambda:self.js("!!document.querySelector('.desktop-app-header')"))
        note=self.notes.book.create('Ideen für das Arbeitszimmer','## Nächste Schritte\n\nLicht, Schreibtisch und Stauraum planen.')
        self.notes.scanned(self.notes.book.scan());self.notes.show_note(note)
        self.wait(lambda:self.notes.doc is not None)
        self.projects.library.create('Arbeitszimmer einrichten',notes='Quellen sammeln und nächste Schritte planen.')
        self.projects.home.refresh()
        self.code.collection.create('tool','Dokumente zusammenfassen',value={'prompt':'Fasse das ausgewählte Dokument zusammen.'});self.code.refresh()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def tearDown(self):
        for _,window in self.windows:window.close()
        self.wait(lambda:not self.notes.isVisible() and not self.notes.job and not self.notes.poller)
        for _,window in self.windows:window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);self.app.processEvents();self.temp.cleanup()

    def test_real_apps_share_header_and_existing_menus_without_app_strip(self):
        self.projects.flow_entry.click();self.assertEqual(self.projects.areas.currentIndex(),2)
        self.projects.back_home.click();self.assertEqual(self.projects.areas.currentIndex(),3)
        output=Path(os.environ['LUMEN_DESKTOP_CAPTURE']) if os.environ.get('LUMEN_DESKTOP_CAPTURE') else None
        if output:output.mkdir(parents=True,exist_ok=True)
        for theme in ('graphite','glass','atelier','midnight'):
            apply_design(self.app,theme);sizes=[];families=[]
            for name,window in self.windows:
                window.resize(1280,900);window.show();QTest.qWait(300)
                self.assertFalse(any(bar.objectName()=='panoramaApps' for bar in window.findChildren(QToolBar)))
                if name=='notes':
                    expected=self.app.palette().color(QPalette.Window).name()
                    self.wait(lambda:self.js("getComputedStyle(document.documentElement).getPropertyValue('--window').trim()")==expected)
                    metrics=json.loads(self.js("JSON.stringify((()=>{const h=document.querySelector('.desktop-app-header');const t=h.querySelector('h1');const p=h.querySelector('p');return {height:Math.round(h.getBoundingClientRect().height),left:h.getBoundingClientRect().left,top:h.getBoundingClientRect().top,weight:getComputedStyle(t).fontWeight,title:getComputedStyle(t).fontSize,subtitle:getComputedStyle(p).fontSize,family:getComputedStyle(t).fontFamily.split(',')[0].replaceAll('\"','').trim()};})())"))
                    self.assertEqual(metrics['title'],'26px');self.assertEqual(metrics['subtitle'],'12px');self.assertEqual(metrics['weight'],'500');self.assertEqual((metrics['left'],metrics['top']),(24,20))
                    sizes.append(metrics['height']);families.append(metrics['family'])
                    self.wait(lambda:self.js("!!document.querySelector('.title-input')"))
                    self.assertTrue(self.js("(()=>{const row=document.querySelector('.doc-row');const title=row?.querySelector('strong');const summary=row?.querySelector('small');const input=document.querySelector('.title-input');const tags=document.querySelector('.note-tags-editor');return !!(title&&summary&&input&&tags)&&title.getBoundingClientRect().bottom<=summary.getBoundingClientRect().top&&input.getBoundingClientRect().bottom<=tags.getBoundingClientRect().top;})()"))
                    # WebEngine DOM readiness precedes its offscreen compositor frame.
                    self.notes.notes_web.update();QTest.qWait(350)
                else:
                    headers=[h for h in window.findChildren(AppHeader) if h.isVisible()]
                    self.assertEqual(len(headers),1,name)
                    header=headers[0];sizes.append(header.height());families.append(header.title.font().family())
                    self.assertEqual(header.title.font().pixelSize(),26,name)
                    self.assertEqual(header.title.font().weight(),500,name)
                    self.assertEqual(header.mapTo(window,QPoint(0,0)),QPoint(24,20),name)
                    self.assertEqual(header.subtitle.font().pixelSize(),12,name)
                    self.assertEqual(header.title.palette().color(QPalette.WindowText),self.app.palette().color(QPalette.Text),name)
                if output:window.grab().save(str(output/(theme+'-'+name+'.png')))
                window.hide()
            self.assertEqual(len(set(sizes)),1,sizes);self.assertEqual(len(set(families)),1,families)
            fired=[];menu=QMenu(self.notes);first=menu.addAction('Sammlung merken');first.setCheckable(True);first.triggered.connect(lambda checked:fired.append(checked))
            disabled=menu.addAction('Nicht verfügbar');disabled.setEnabled(False);menu.addSeparator();submenu=menu.addMenu('Weitere Aktionen');submenu.addAction('Original öffnen')
            menu.popup(QPoint(80,80));menu.setActiveAction(first);QTest.qWait(20)
            self.assertEqual(menu.font().pixelSize(),14);self.assertFalse(disabled.isEnabled());self.assertEqual(menu.palette().color(QPalette.Text),self.app.palette().color(QPalette.Text))
            if output:menu.grab().save(str(output/(theme+'-menu.png')))
            QTest.keyClick(menu,Qt.Key_Return);self.assertEqual(fired,[True]);self.assertTrue(first.isChecked());menu.close();menu.deleteLater()
        self.audio.select('radio');self.assertIs(self.audio.tabs.currentWidget(),self.audio.pages['radio'])
        with patch.object(self.audio.pages['radio'],'open_settings') as settings:
            self.audio.settings_button.click();settings.assert_called_once_with()
        self.audio.select('meetings');self.assertIs(self.audio.tabs.currentWidget(),self.audio.pages['meetings'])
        with patch.object(self.audio.pages['meetings'],'open_settings') as settings:
            self.audio.settings_button.click();settings.assert_called_once_with()
        self.notes.resize(960,800);self.notes.show();QTest.qWait(500)
        self.assertTrue(self.js("document.documentElement.scrollWidth<=window.innerWidth"))
        self.assertTrue(self.js("document.querySelector('.title-input').getBoundingClientRect().right<=window.innerWidth"))
        if output:self.notes.grab().save(str(output/'notes-narrow.png'))


if __name__=='__main__':unittest.main()
