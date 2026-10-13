"""Room references, navigation and opt-in resume use isolated files/stores."""
import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox,QPlainTextEdit,QApplication,QPushButton,QWidget,QLabel
from app import Window,create_app
from file_spaces import Catalog
from lumen_store import Store
from lumen_workplace import Workplace
from interop_data import Registry
import lumen_projects as projects

class RoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or create_app()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,LUMEN_DATA=str(self.root/'state'),LUMEN_TOOLS_DATA=str(self.root/'tools'));self.env.start()
        self.store=Store(self.root/'state');self.file=self.root/'note.txt';self.file.write_text('unchanged')
        self.project=projects.save_project(self.store,None,'Workshop',[dict(label='PC',location=str(self.root))],[],[],'Next step')
        self.w=Window(str(self.root),QSettings(str(self.root/'prefs'),QSettings.IniFormat),Catalog(self.store))
        self.page=Workplace(store=self.store,files_provider=lambda:self.w);self.page.resize(1150,820);self.page.show();QTest.qWait(30)
        self.rooms=self.page.rooms
    def tearDown(self):
        self.page.shutdown();self.page.close();self.w.close();self.page.deleteLater();self.w.deleteLater();QTest.qWait(10);self.env.stop();self.tmp.cleanup()
    def pin(self):
        url=Registry().register(dict(app='files',kind='file',id=str(self.file),path=str(self.file),title='note.txt'))
        return dict(kind='object',app='files',url=url,title='note.txt')
    def test_landing_detail_and_activity_keep_existing_actions(self):
        self.assertEqual(self.rooms.stack.currentIndex(),0)
        self.rooms.open(self.project['id']);self.assertEqual(self.rooms.stack.currentIndex(),1)
        self.assertEqual(self.rooms.tabs.count(),6)
        self.rooms.prompt.setText('Draft');self.page.resize(730,800);QTest.qWait(30)
        self.assertEqual(self.rooms.prompt.text(),'Draft')
        self.page.tabs.setCurrentIndex(1);self.assertTrue(self.page.tabs.tabBar().isVisible())
        self.page.tabs.setCurrentIndex(0);self.rooms.home();self.assertEqual(self.rooms.stack.currentIndex(),0)
        self.page.refresh_modes() # Main Lumen calls this for the room page too.
    def test_continue_opens_room_and_folder_only_navigates_files(self):
        home=self.rooms.stack.widget(0)
        def control(title):return next(b for b in home.findChildren(QPushButton) if b.text()==title and b.isVisible())
        self.rooms.prompt.setText('Keep draft')
        with patch.object(self.page,'resume') as resume,patch.object(self.w.spaces,'open_room') as restore,patch.object(self.w,'navigate') as navigate:
            control('Weiterarbeiten →').click()
            self.assertEqual(self.rooms.stack.currentIndex(),1)
            self.assertEqual(self.rooms.prompt.text(),'Keep draft')
            resume.assert_not_called();restore.assert_not_called();navigate.assert_not_called()
            self.rooms.home();QTest.qWait(10)
            control('Ordner öffnen').click();navigate.assert_called_once_with(str(self.root))
            resume.assert_not_called();restore.assert_not_called()
            self.assertEqual(self.rooms.prompt.text(),'Keep draft')
        from file_spaces import LIBRARY
        room=projects.save_project(self.store,None,'Several folders',[dict(label='One',location=str(self.root)),dict(label='Two',location=str(self.root/'second'))],[],[],'')
        with patch.object(self.w,'navigate') as navigate:
            self.rooms.open_folder(room);navigate.assert_called_once_with(LIBRARY+'project-'+room['id'])
        self.rooms.open(room['id'])
        self.assertEqual(self.page.project['id'],self.project['id'])
        self.assertEqual(self.rooms.prompt.text(),'Keep draft')
    def test_knowledge_and_links_have_visible_empty_sections_and_direct_add(self):
        self.rooms.open(self.project['id'])
        for name,title,method in [('roomKnowledge','Notes-Notiz hinzufügen','add_note'),('roomWeblinks','Weblink hinzufügen','add_url')]:
            section=self.rooms.findChild(QWidget,name)
            self.assertTrue(section.isVisible())
            with patch.object(self.rooms,method) as add:
                next(b for b in section.findChildren(QPushButton) if b.text()==title).click()
                add.assert_called_once()
        note=self.root/'idea.md';note.write_text('Knowledge text')
        url=Registry().register(dict(app='wissen',kind='note',id='idea.md',title='Idea',path=str(note),locator=dict(root=str(self.root),area='user')))
        with patch.object(self.rooms,'load_previews'):
            self.rooms.add_pin(dict(kind='object',app='wissen',title='Idea',url=url))
        self.rooms.add_pin(dict(kind='url',title='Research website',url='https://example.org/research'))
        QTest.qWait(20)
        knowledge=self.rooms.findChild(QWidget,'roomKnowledge');links=self.rooms.findChild(QWidget,'roomWeblinks')
        self.assertIn('Idea',[l.text() for l in knowledge.findChildren(QLabel)])
        self.assertIn('Research website',[l.text() for l in links.findChildren(QLabel)])
        self.assertFalse(any('Noch keine' in l.text() for l in knowledge.findChildren(QLabel)+links.findChildren(QLabel)))
        self.page.resize(730,800);QTest.qWait(30)
        self.assertTrue(self.rooms.findChild(QWidget,'roomKnowledge').isVisible())
        self.assertTrue(self.rooms.findChild(QWidget,'roomWeblinks').isVisible())
        self.rooms.save(urls=['https://example.org/legacy','https://example.org/research'])
        chat=Mock();chat.composer=QPlainTextEdit()
        with patch.object(self.rooms,'chat_ready',return_value=chat):
            self.rooms.prompt.setText('Compare these sources');self.rooms.discuss()
        self.assertEqual(set(chat.paths),{str(self.root),str(note)})
        draft=chat.composer.toPlainText()
        self.assertIn('https://example.org/legacy',draft)
        self.assertEqual(draft.count('https://example.org/research'),1)
        self.assertIn('Compare these sources',draft);chat.send.assert_not_called()
    def test_pins_are_references_survive_capture_and_do_not_open_automatically(self):
        pin=self.pin();self.rooms.add_pin(pin);self.rooms.add_pin(pin)
        self.assertEqual(len(self.page.project['pins']),1)
        self.page.capture();self.assertEqual(self.page.project['pins'],[pin])
        with patch.object(self.rooms,'open_pin') as opened:
            self.rooms.resume_pins(self.page.project);opened.assert_not_called()
            self.rooms.save(pins=[dict(pin,resume=True)])
            self.rooms.resume_pins(self.page.project);opened.assert_called_once()
        with patch.object(self.w,'open_path') as opened:self.rooms.open_pin(pin);opened.assert_called_once_with(str(self.file))
        self.rooms.save(pins=[]);self.assertEqual(self.file.read_text(),'unchanged')
    def test_stale_edits_are_refused_and_task_state_is_real(self):
        stale=self.page.project
        projects.save_project(self.store,stale,'Other window',stale['sources'],[],[],'changed')
        with self.assertRaises(ValueError):self.rooms.save(note='overwrite')
        self.page.refresh_projects(stale['id']);self.assertEqual(self.page.project['note'],'changed')
        task=self.store.create_task('Check draft',status='draft');self.rooms.add_pin(dict(kind='task',id=task,title='Check draft'))
        self.store.update_task(task,status='completed');self.rooms.refresh_tasks()
        self.assertEqual(self.rooms.tasks.item(0,1).text(),'Erledigt')
        self.assertEqual(self.rooms.task_labels[task].text(),'Erledigt')
    def test_pin_order_and_unsafe_links(self):
        for url in ('javascript:alert(1)','https://user:pw@example.org'):
            with self.assertRaises(ValueError):self.rooms.add_pin(dict(kind='url',url=url,title='Bad'))
        with self.assertRaises(ValueError):projects.validate_pin(dict(kind='chat',title='Bad',chat=dict(directory='relative',session='x')))
        a=self.pin();b=dict(kind='url',url='https://example.org',title='Docs')
        self.rooms.add_pin(a);self.rooms.add_pin(b);self.rooms.move_pin(b,-1)
        self.assertEqual(self.page.project['pins'],[b,a])
        self.assertEqual(self.file.read_text(),'unchanged')
    def test_chat_handoff_does_not_discard_a_draft_or_send(self):
        chat=Mock();chat.backend.busy=False;chat.context_tools.process=None;chat.composer=QPlainTextEdit('Keep this')
        with patch.object(self.w.spaces,'chat',return_value=chat),patch.object(self.w,'ask_lumen') as ask,patch.object(QMessageBox,'question',return_value=QMessageBox.No):
            self.rooms.prompt.setText('Question');self.rooms.discuss();ask.assert_not_called();self.assertEqual(chat.composer.toPlainText(),'Keep this')
        chat.composer.clear()
        with patch.object(self.w.spaces,'chat',return_value=chat),patch.object(self.w,'ask_lumen'):
            self.rooms.prompt.setText('Question');self.rooms.discuss()
            self.assertIn('Workshop',chat.composer.toPlainText());self.assertIn('Question',chat.composer.toPlainText());chat.send.assert_not_called()
    def test_resume_refuses_discard_and_preserves_pins_on_active_room(self):
        chat=Mock();chat.backend.busy=False;chat.context_tools.process=None;chat.composer=QPlainTextEdit('Keep')
        with patch.object(self.w.spaces,'chat',return_value=chat),patch.object(self.w.spaces,'open_room') as opened,patch.object(QMessageBox,'question',return_value=QMessageBox.No):
            self.page.resume();opened.assert_not_called()
        self.w.spaces.active_room=self.page.project
        self.rooms.add_pin(self.pin());self.assertEqual(self.w.spaces.active_room,self.page.project)
        self.assertTrue(self.w.spaces.save_active_room());self.assertEqual(len(projects.projects(self.store)[0]['pins']),1)

    def test_knowledge_preview_is_read_live_without_copying_note(self):
        note=self.root/'idea.md';note.write_text('# Idea\nOriginal note content')
        ref=dict(app='wissen',kind='note',id='idea.md',title='Idea',path=str(note),locator=dict(root=str(self.root),area='user'))
        url=Registry().register(ref);self.rooms.open(self.project['id']);self.rooms.add_pin(dict(kind='object',app='wissen',title='Idea',url=url))
        for _ in range(200):
            QTest.qWait(10)
            if not self.page.jobs:break
        self.assertFalse(self.page.jobs)
        self.assertIn('Original note content',self.rooms.preview_labels[url].text())
        self.assertNotIn('Original note content',str(projects.projects(self.store)))
        self.assertEqual(note.read_text(),'# Idea\nOriginal note content')

    def test_two_rooms_replace_sources_without_copying_or_sending(self):
        second = self.root/'second'; second.mkdir()
        other = projects.save_project(self.store, None, 'Second room', [dict(label='B', location=str(second))], [], ['https://example.org/second'], 'B only')
        chat = Mock(); chat.backend.busy = False; chat.context_tools.process = None
        chat.composer = QPlainTextEdit()
        with patch.object(self.w.spaces, 'chat', return_value=chat), patch.object(self.w, 'ask_lumen'), patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            for room, expected, excluded in ((self.project, self.root, second), (other, second, self.root), (self.project, self.root, second)):
                self.rooms.open(room['id'])
                self.rooms.prompt.setText('Use this room')
                self.rooms.discuss()
                self.assertEqual(chat.paths, [str(expected)])
                self.assertIn(room['name'], chat.composer.toPlainText())
                if room == self.project: self.assertNotIn('B only', chat.composer.toPlainText())
                chat.backend.send.assert_not_called()
        self.assertEqual(self.file.read_text(), 'unchanged')

    def test_file_views_do_not_offer_project_management(self):
        from PySide6.QtCore import QTimer
        spaces=self.w.spaces
        spaces.catalog.save_room(None,'Saved file view',spaces.capture())
        spaces.active_room=self.project
        labels=[]
        def inspect():
            menu=QApplication.activePopupWidget()
            if menu is not None:
                labels.extend(a.text() for a in menu.actions() if not a.isSeparator());menu.close()
        QTimer.singleShot(20,inspect);spaces.room_menu()
        spaces.active_room=None
        self.assertIn('Saved file view',labels)
        self.assertNotIn(self.project['name'],labels)
        self.assertIn('Lumen Projekte öffnen',labels)
        self.assertNotIn('Dateiansicht umbenennen …',labels)
        self.assertFalse(any('Arbeitsraum' in label for label in labels))

if __name__=='__main__':unittest.main()
