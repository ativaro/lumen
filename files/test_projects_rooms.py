import tempfile
import unittest
from pathlib import Path
from tools_data import Library
from lumen_store import Store
from lumen_projects import save_project
from projects_rooms import ProjectRooms, source_chain
from projects_data import Projects


class ProjectRoomsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.library=Library('workbench',self.tmp.name); self.store=Store(Path(self.tmp.name)/'state')
        self.links=ProjectRooms(self.library,self.store)

    def test_same_name_is_not_identity_and_open_is_idempotent(self):
        project=self.library.create('Same name',resources=[])
        room=save_project(self.store,None,'Same name',[dict(label='Folder',location=self.tmp.name)],[],[],'Note')
        self.assertEqual(self.links.links(),{})
        created=self.links.from_room(room)
        self.assertNotEqual(created,project)
        self.assertEqual(self.links.from_room(room),created)
        self.assertEqual(len(self.library.all()),2)
        self.assertEqual(self.links.room(created),room)
        with self.assertRaises(ValueError):self.links.link(project,room['id'])

    def test_existing_project_can_explicitly_use_existing_room(self):
        project=self.library.create('Project',resources=[])
        room=save_project(self.store,None,'Room',[dict(label='Folder',location=self.tmp.name)],[],['https://example.org'],'Note')
        self.links.link(project,room['id']); self.links.link(project,room['id'])
        self.assertEqual(len(self.library.all()),1)
        self.assertEqual(self.links.material(project)['notes'],'Note')
        self.assertEqual(self.links.material(project)['resources'][1]['target'],'https://example.org')
        self.links.unlink(project)
        self.assertEqual(self.links.links(),{})
        self.assertEqual(self.library.get(project)['title'],'Project')
        from lumen_projects import projects
        self.assertEqual(projects(self.store),[room])

    def test_folderless_project_and_scoped_material(self):
        project=self.library.create('No folder',resources=[dict(kind='url',target='https://example.org',title='Source')])
        room=self.links.ensure(project)
        self.assertEqual(room['sources'],[])
        self.assertEqual(self.links.ensure(project)['id'],room['id'])
        projects=Projects(self.library); a=projects.add(project,'','A','initiative',notes='Scope A'); b=projects.add(project,'','B','initiative',notes='Scope B')
        chain=source_chain(projects,project,a,self.store)
        self.assertIn('Scope A',str(chain)); self.assertNotIn('Scope B',str(chain))
        other=self.library.create('Other')
        with self.assertRaises(ValueError):source_chain(projects,other,b,self.store)

    def test_research_can_repeat_without_creating_another_task(self):
        project=self.library.create('Plan'); projects=Projects(self.library)
        initiative=projects.add(project,'','Goal','initiative')
        task=projects.add(project,initiative,'Research','research',enabled=True,next_run=0,interval=3600)
        run=projects.begin_run(task,{},scheduled=True)
        self.assertGreater(projects.get(task)['next_run'],0)
        projects.finish_run(run,'failed',error='Offline')
        self.assertFalse(projects.get(task)['enabled'])
        self.assertEqual(projects.get(task)['kind'],'research')
        with self.assertRaises(ValueError):projects.begin_run(task,{},scheduled=True)

    def test_flow_keeps_trigger_and_is_not_duplicated_or_enabled_by_link(self):
        project=self.library.create('Plan');other=self.library.create('Other')
        flow=self.store.save_workflow('Check folder',[dict(action='open',path=self.tmp.name)],[self.tmp.name],trigger='directory',watch=self.tmp.name,enabled=False,approved=True)
        before=self.store.workflows()
        self.links.attach_flow(project,'',flow);self.links.attach_flow(project,'',flow)
        self.assertEqual(self.store.workflows(),before)
        self.assertEqual(len(self.links.flows(project)),1)
        with self.assertRaises(ValueError):self.links.attach_flow(other,'',flow)

    def test_runner_reads_attached_room_and_selected_initiative_only(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from projects_runner import snapshot
        from file_spaces import Catalog
        project=self.library.create('Plan',notes='Project context',resources=[]);projects=Projects(self.library)
        a=projects.add(project,'','Selected','initiative',notes='Selected context')
        projects.add(project,'','Other','initiative',notes='Must not be included')
        task=projects.add(project,a,'Read','analysis')
        room=self.links.ensure(project)
        from interop_data import Registry
        document=Path(self.tmp.name)/'source.txt';document.write_text('Room document content')
        ref=Registry(self.library.root.parent).register(dict(app='files',kind='file',id=str(document),path=str(document),title='Room source'))
        Catalog(self.store).put('room',dict(room,note='Room context',urls=['https://example.org'],pins=[dict(kind='object',app='files',url=ref,title='Room source')]),room)
        with patch('lumen_store.Store',return_value=self.store):result=snapshot(projects,task,SimpleNamespace(check=lambda:None))
        self.assertIn('Room context',str(result));self.assertIn('Selected context',str(result))
        self.assertNotIn('Must not be included',str(result))
        self.assertIn('https://example.org',str(result))
        self.assertIn('Room document content',str(result))


class ProjectHomeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or create_app()

    def setUp(self):
        import os
        from unittest.mock import patch
        from tools_workbench import Workbench
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.env=patch.dict(os.environ,LUMEN_DATA=self.tmp.name+'/state',LUMEN_TOOLS_DATA=self.tmp.name+'/tools');self.env.start();self.addCleanup(self.env.stop)
        with patch('projects_sync_ui.install'):self.window=Workbench()
        self.window.error=lambda message:self.fail(message)
        self.window.show();self.app.processEvents()

    def tearDown(self):
        from PySide6.QtCore import QCoreApplication,QEvent
        self.window.home.prompt.clear();self.window.close();self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_home_planning_and_five_conversations_share_identity(self):
        from file_spaces import Catalog
        from PySide6.QtWidgets import QPushButton
        w=self.window;p=w.library.create('Broadcom',notes='Keep notes',resources=[]);i=w.projects.add(p,'','Migration','initiative');t=w.projects.add(p,i,'Compare','research')
        room=w.home.links.ensure(p);pins=[dict(kind='chat',title='Chat '+str(n),chat=dict(directory=self.tmp.name,session='session-'+str(n))) for n in range(7)]
        Catalog(w.workplace.store).put('room',dict(room,pins=pins),room)
        w.home.refresh();w.home.choose('project:'+p)
        self.assertEqual(w.areas.currentIndex(),3);self.assertFalse(w.areas.tabBar().isVisible())
        pane=w.home.columns[2][0]
        buttons=lambda:[pane.layout().itemAt(j).widget() for j in range(pane.layout().count()) if isinstance(pane.layout().itemAt(j).widget(),QPushButton)]
        self.assertEqual(len([b for b in buttons() if b.text().startswith('Chat ')]),5)
        w.home.more_chats()
        from PySide6.QtCore import QEvent,QCoreApplication
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.assertEqual(len([b for b in buttons() if b.text().startswith('Chat ')]),7)
        w.home.scope=i;w.home.plan(t)
        self.assertEqual(w.scope,t);self.assertEqual(w.current,p);self.assertTrue(w.schedule_row.isVisible())
        w.show_home();self.assertEqual(w.home.scope,i);self.assertEqual(w.home.room_id,room['id'])
        self.assertEqual(w.library.get(p)['notes'],'Keep notes')

    def test_context_switch_protects_prompt_and_discuss_does_not_send(self):
        from unittest.mock import patch
        import json
        w=self.window;p=w.library.create('First',resources=[]);other=w.library.create('Second',resources=[])
        i=w.projects.add(p,'','Selected','initiative');w.home.refresh();w.home.choose('project:'+p);w.home.select_initiative(i);w.home.prompt.setText('Keep this draft')
        with self.assertRaises(ValueError):w.home.choose('project:'+other)
        self.assertEqual(w.home.project_id,p)
        with patch('lumen_detail_routes.room_action',side_effect=ValueError('Existing draft')):
            with self.assertRaises(ValueError):w.home.discuss()
        self.assertEqual(w.home.prompt.text(),'Keep this draft')
        with patch('lumen_detail_routes.room_action',return_value={}) as send:
            w.home.discuss();request=json.loads(send.call_args.args[2])
            self.assertEqual(request,dict(project=p,scope=i,prompt='Keep this draft'))
        self.assertEqual(w.home.prompt.text(),'')

    def test_native_flow_and_repeated_task_open_their_original_editor(self):
        w=self.window;p=w.library.create('Plan',resources=[]);i=w.projects.add(p,'','Goal','initiative')
        task=w.projects.add(p,i,'Compare weekly','research',enabled=False,next_run=123)
        flow=w.workplace.store.save_workflow('Existing flow',[dict(action='open',path=self.tmp.name)],[self.tmp.name],approved=True)
        w.home.links.attach_flow(p,i,flow);w.home.refresh();w.home.choose('project:'+p);w.home.select_initiative(i)
        w.home.open_flow(flow)
        self.assertEqual(w.automations.flows.currentItem().data(256)['id'],flow)
        self.assertEqual(w.recurring.count(),1)
        self.assertEqual(w.recurring.item(0).data(256),(p,task))
