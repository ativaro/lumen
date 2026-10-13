"""Hierarchy, native editing, handoffs and the real asynchronous runner lifecycle."""
import json
import tempfile
import time
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from PySide6.QtCore import QObject,Signal,QTimer,Qt,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication
from tools_data import Library
from projects_data import Projects
from lumen_jobs import Job


class FakeEngine(QObject):
    completed=Signal(bool,str); requestsChanged=Signal(object,object)
    calls=[]
    def __init__(self,directory,parent=None,**kwargs):super().__init__(parent); self.busy=False; self.messages=[]
    def send(self,prompt,**kwargs):
        self.calls.append(kwargs); self.busy=True
        self.messages=[dict(parts=[dict(type='tool',tool='websearch',state=dict(status='completed'))])]
        QTimer.singleShot(0,lambda:self.completed.emit(True,'Result with https://example.org/source'))
    def stop(self):self.completed.emit(False,'Abgebrochen')
    def shutdown(self):self.busy=False


class ProjectsTest(TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.library=Library('workbench',self.temp.name); self.projects=Projects(self.library)
        self.project=self.library.create('Home',notes='project context',questions=[],resources=[])
        self.initiative=self.projects.add(self.project,'','Room','initiative')

    def tearDown(self):
        for window in list(self.app.topLevelWidgets()):
            window.close();window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.app.processEvents()

    def test_migration_dependencies_and_run_transactions(self):
        self.library.update(self.project,questions=[dict(text='Measure',done=True),dict(text='Paint',done=False)],question_draft='unfinished')
        self.projects.migrate(self.project); self.projects.migrate(self.project)
        tasks=[t for t in self.projects.items(self.project) if t['kind']=='manual']
        self.assertEqual(len(tasks),2); self.assertEqual(tasks[0]['status'],'done')
        self.assertEqual(self.library.get(self.project)['question_draft'],'unfinished')
        self.projects.update(tasks[1]['id'],depends=[tasks[0]['id']])
        with self.assertRaises(ValueError):self.projects.update(tasks[0]['id'],depends=[tasks[1]['id']])
        run=self.projects.begin_run(tasks[1]['id'],dict(sources=[]))
        with self.assertRaises(ValueError):self.projects.begin_run(tasks[1]['id'],{})
        self.projects.update(tasks[1]['id'],notes='edit while running')
        self.projects.finish_run(run,'done','result')
        self.assertEqual(self.projects.get(tasks[1]['id'])['notes'],'edit while running')
        self.assertEqual(self.projects.runs(tasks[1]['id'])[0]['result'],'result')

    def test_native_scope_edits_reopen_and_archive(self):
        from tools_workbench import Workbench
        task=self.projects.add(self.project,self.initiative,'Review','analysis')
        w=Workbench(self.temp.name); w.error=lambda message:self.fail(message)
        w.focus_record(self.project); w.open_scope(task); w.notes.setPlainText('task note'); w.goal.setPlainText('compare'); w.save()
        w.navigate(self.project,self.initiative); w.notes.setPlainText('initiative note'); w.save()
        w.navigate(self.project,''); self.assertEqual(w.notes.toPlainText(),'project context')
        w.navigate(self.project,task); self.assertEqual(w.notes.toPlainText(),'task note'); self.assertEqual(w.goal.toPlainText(),'compare')
        w.navigate(self.project,self.initiative); w.archive()
        self.assertFalse(self.library.get(self.project)['_archived']); self.assertTrue(self.projects.get(self.initiative)['archived'])
        w.archived.setChecked(True)
        self.assertEqual(w.entries.topLevelItemCount(),1); self.assertEqual(w.entries.topLevelItem(0).childCount(),1)
        w.navigate(self.project,self.initiative); w.archive(); self.assertFalse(self.projects.get(self.initiative)['archived'])
        w.archived.setChecked(False); w.open_scope(task); w.archive_task(); w.archived.setChecked(True); w.open_scope(task); w.archive_task()
        self.assertFalse(self.projects.get(task)['archived'])
        w.close()

    def test_external_project_edits_refresh_without_discarding_editor_draft(self):
        from tools_workbench import Workbench
        w=Workbench(self.temp.name); w.focus_record(self.project)
        self.library.update(self.project,notes='Saved by project tool')
        w.poll_runs(); self.assertEqual(w.notes.toPlainText(),'Saved by project tool')
        w.notes.setPlainText('Unsent local edit')
        self.library.update(self.project,notes='Another external edit')
        w.poll_runs(); self.assertEqual(w.notes.toPlainText(),'Unsent local edit')
        with self.assertRaises(ValueError):w.save()
        self.assertEqual(self.library.get(self.project)['notes'],'Another external edit')
        self.assertEqual(w.notes.toPlainText(),'Unsent local edit')
        w.editor.discard()
        self.library.create('Added by tool')
        w.poll_runs(); self.assertEqual(w.entries.topLevelItemCount(),2)
        w.close()

    def test_due_check_is_atomic_and_history_selection_stays(self):
        from tools_workbench import Workbench
        task=self.projects.add(self.project,self.initiative,'Repeat','automation',enabled=True,next_run=0)
        self.projects.update(task,enabled=False)
        with self.assertRaises(ValueError):self.projects.begin_run(task,{},scheduled=True)
        self.projects.update(task,enabled=True,next_run=time.time()+3600)
        with self.assertRaises(ValueError):self.projects.begin_run(task,{},scheduled=True)
        for result in ('old','new'):
            run=self.projects.begin_run(task,{});self.projects.finish_run(run,'done',result)
        w=Workbench(self.temp.name); w.focus_record(self.project);w.open_scope(task);w.history.setCurrentIndex(1)
        w.poll_runs();self.assertEqual(w.result.toPlainText(),'old');w.close()

    def test_task_selection_handoff_does_not_include_other_sources(self):
        from tools_workbench import Workbench
        from interop_sources import capture
        from PySide6.QtGui import QTextCursor
        one=Path(self.temp.name)/'one.txt';two=Path(self.temp.name)/'two.txt';one.write_text('one');two.write_text('two')
        task=self.projects.add(self.project,self.initiative,'Compare','analysis',notes='selected text',goal='Private goal',resources=[dict(kind='file',title='One',target=str(one)),dict(kind='file',title='Two',target=str(two))])
        w=Workbench(self.temp.name);w.focus_record(self.project);w.open_scope(task);w.tabs.setCurrentIndex(1);w.resources.setCurrentRow(0)
        self.assertEqual(capture(w)['paths'],[str(one)])
        w.tabs.setCurrentIndex(0);cursor=w.notes.textCursor();cursor.select(QTextCursor.Document);w.notes.setTextCursor(cursor)
        payload=capture(w);self.assertEqual(payload['text'],'selected text');self.assertEqual(payload['paths'],[]);w.close()

    def test_scoped_handoff_undo_and_reference(self):
        from interop_targets import apply,choices
        from interop_undo import undo
        from interop_data import Registry
        from interop_open import focus
        from tools_workbench import Workbench
        task=self.projects.add(self.project,self.initiative,'Compare','analysis')
        registry=Registry(self.temp.name); source=dict(app='workbench',kind='record',id=self.project,title='Source')
        payload=dict(title='Document',text='hello',paths=[],items=[],source=source,source_url=registry.register(source))
        choice=dict(id=self.project+'/'+task,mode='copy',title='Document',token='projects-test')
        self.assertIn(choice['id'],[r['id'] for r in choices('workbench.add',self.temp.name)])
        ref=apply('workbench.add',payload,choice,Job(lambda _:None),self.temp.name)
        self.assertIn('hello',self.projects.get(task)['notes'])
        self.assertEqual(ref,apply('workbench.add',payload,choice,Job(lambda _:None),self.temp.name))
        w=Workbench(self.temp.name); focus(w,ref); self.assertEqual(w.scope,task); w.close()
        undo('workbench.add',choice['token'],Job(lambda _:None),self.temp.name)
        self.assertEqual(self.projects.get(task)['notes'],'')

    def test_question_undo_reimport_restore_and_new_project(self):
        from interop_targets import apply
        from interop_undo import undo
        from interop_data import Registry
        source=dict(app='workbench',id=self.project,title='Source'); registry=Registry(self.temp.name)
        payload=dict(title='Question',text='Question?',paths=[],items=[],source=source,source_url=registry.register(source))
        choice=dict(id=self.project,mode='copy',title='Question',token='question-1'); job=Job(lambda _:None)
        apply('workbench.question',payload,choice,job,self.temp.name);self.projects.migrate(self.project)
        task=next(t for t in self.projects.items(self.project) if t['kind']=='manual')
        undo('workbench.question',choice['token'],job,self.temp.name);self.projects.migrate(self.project)
        self.assertTrue(self.projects.get(task['id'])['archived'])
        self.projects.update(task['id'],archived=False);self.projects.migrate(self.project);self.assertFalse(self.projects.get(task['id'])['archived'])
        choice['token']='question-2';apply('workbench.question',payload,choice,job,self.temp.name);self.projects.migrate(self.project)
        self.assertEqual(len([t for t in self.projects.items(self.project) if t['kind']=='manual']),2)
        choice.update(id='',token='new-project');ref=apply('workbench.question',payload,choice,job,self.temp.name);self.projects.migrate(ref['id'])
        before=self.projects.items(ref['id']);undo('workbench.question',choice['token'],job,self.temp.name);self.projects.migrate(ref['id'])
        self.assertEqual(self.projects.items(ref['id']),before)

    def test_import_locks_all_three_panes_and_timer_stops_on_close(self):
        from tools_workbench import Workbench
        w=Workbench(self.temp.name);w.focus_record(self.project);w.begin('Import')
        self.assertFalse(w.task_pane.isEnabled());self.assertFalse(w.body.isEnabled());self.assertFalse(w.sidebar.isEnabled())
        w.end();self.assertTrue(w.task_pane.isEnabled());w.close();self.assertFalse(w.poll_timer.isActive())

    def test_snapshot_paths_revisions_and_recovery(self):
        from projects_runner import snapshot,recover,lease
        from interop_paths import relocate
        import os
        old=Path(self.temp.name)/'old.txt'; new=Path(self.temp.name)/'new.txt'; old.write_text('document')
        task=self.projects.add(self.project,self.initiative,'Read','analysis',resources=[dict(kind='file',title='Text',target=str(old))])
        old.rename(new); relocate(old,new,self.temp.name)
        value=snapshot(self.projects,task,Job(lambda _:None)); self.assertEqual(value['sources'][-1]['text'],'document')
        self.assertIn('SHA256',value['sources'][-1]['revision'])
        run=self.projects.begin_run(task,value); fd=lease(self.projects,task)
        recover(self.projects); self.assertEqual(self.projects.runs(task)[0]['status'],'running')
        os.close(fd); recover(self.projects); self.assertEqual(self.projects.runs(task)[0]['status'],'paused')

    def test_runner_reuse_three_phases_and_failure(self):
        from projects_runner import Runner
        first=self.projects.add(self.project,self.initiative,'Research','research',deep=True)
        second=self.projects.add(self.project,self.initiative,'Analyze','analysis')
        with patch('assistant_backend.OpenCodeBackend',FakeEngine):
            runner=Runner(self.projects,self.app); FakeEngine.calls=[]
            for task in (first,second):
                runner.start(task); deadline=time.monotonic()+5
                while runner.busy and time.monotonic()<deadline:self.app.processEvents(); time.sleep(.005)
                self.assertFalse(runner.busy); self.assertEqual(self.projects.runs(task)[0]['status'],'done')
            self.assertEqual([c['web_research'] for c in FakeEngine.calls],[True,True,False,False])
            self.assertTrue(all(c['project_task'] for c in FakeEngine.calls))
            runner.start(second); runner.cancel(); deadline=time.monotonic()+5
            while runner.busy and time.monotonic()<deadline:self.app.processEvents(); time.sleep(.005)
            self.assertEqual(self.projects.runs(second)[0]['status'],'cancelled')
            runner.deleteLater()

    def test_backend_scopes_permissions_and_excludes_memory(self):
        from assistant_backend import OpenCodeBackend
        from lumen_store import Store
        store=Store(Path(self.temp.name)/'state')
        calls=[]
        engine=OpenCodeBackend(self.temp.name); engine.selected_model='test/model'; engine.read_only=True; engine.ensure_server=lambda callback:callback(); engine.refresh_sessions=lambda:None; engine.poll=lambda:None
        def request(method,path,body=None,callback=None,**kwargs):
            calls.append((method,path,body))
            if path=='/session' and method=='POST':callback(dict(id='test-session'))
        engine.request=request
        with patch('lumen_store.Store',return_value=store),patch('memory_bridge.MemoryBridge',side_effect=AssertionError('Memory must not be read')):
            engine.send('Synthetic task',project_task=True,web_research=True)
            session=next(body for method,path,body in calls if path=='/session')
            prompt=next(body for method,path,body in calls if path.endswith('prompt_async'))
            self.assertEqual(prompt['tools'],{'*':False,'websearch':True,'webfetch':True})
            self.assertEqual([rule['action'] for rule in session['permission']],['deny','allow','allow'])
            engine.set_busy(False); calls.clear(); engine.send('Synthetic analysis',project_task=True)
            session=next(body for method,path,body in calls if path=='/session')
            prompt=next(body for method,path,body in calls if path.endswith('prompt_async'))
            self.assertEqual(prompt['tools'],{'*':False}); self.assertEqual(len(session['permission']),1)
        engine.shutdown();engine.deleteLater()

    def test_chat_discovers_projects_without_loading_them_into_every_prompt(self):
        from assistant_backend import OpenCodeBackend
        from lumen_store import Store
        from projects_mcp import INSTRUCTION
        store=Store(Path(self.temp.name)/'chat-state'); store.set_setting('memory/options',dict(enabled=False,learn=False))
        calls=[]
        engine=OpenCodeBackend(self.temp.name); engine.selected_model='test/model'; engine.ensure_server=lambda callback:callback()
        engine.refresh_sessions=lambda:None; engine.poll=lambda:None
        def request(method,path,body=None,callback=None,**kwargs):
            if path.endswith('prompt_async'):calls.append(body)
            if path=='/session' and method=='POST':callback(dict(id='chat-test'))
        engine.request=request
        try:
            with patch('lumen_store.Store',return_value=store),patch('projects_mcp.invoke',side_effect=AssertionError('No eager project read')):
                engine.send('Wie steht mein Projekt?')
                self.assertIn(INSTRUCTION,calls[-1]['system'])
                self.assertNotIn('project context',str(calls[-1]))
                engine.set_busy(False); engine.send('Only attached context',project_task=True)
                self.assertNotIn(INSTRUCTION,calls[-1]['system'])
                engine.set_busy(False); engine.send('Native proposal',proposal=True)
                self.assertNotIn(INSTRUCTION,calls[-1]['system'])
        finally:engine.shutdown();engine.deleteLater()

    def test_timer_records_exact_library_and_failure(self):
        from projects_runner import install_timer
        import os
        from types import SimpleNamespace
        with patch.dict(os.environ,{'XDG_CONFIG_HOME':str(Path(self.temp.name)/'config')}),patch('projects_runner.subprocess.run',return_value=SimpleNamespace(returncode=0,stderr='')) as run:
            install_timer(self.library.root.parent)
            service=next((Path(self.temp.name)/'config/systemd/user').glob('*.service')).read_text()
            self.assertIn('--root "'+str(self.library.root.parent)+'"',service);self.assertEqual(run.call_count,2)
            run.return_value=SimpleNamespace(returncode=1,stderr='unavailable')
            with self.assertRaisesRegex(ValueError,'unavailable'):install_timer(self.library.root.parent)
