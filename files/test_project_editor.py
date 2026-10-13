"""Native sidebar workflows; only synthetic local projects, no providers or timers."""
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from test_projects_rooms import ProjectHomeTest


class SidebarTest(ProjectHomeTest):
    # The base supplies an isolated native window and all home regressions.
    def project(self):
        w=self.window;p=w.library.create('Home',notes='Project note',resources=[])
        i=w.projects.add(p,'','Office','initiative',notes='Initiative note')
        w.home.refresh();w.home.choose('project:'+p);w.home.select_initiative(i)
        return p,i

    def tearDown(self):
        self.window.editor.discard()
        super().tearDown()

    def test_create_cancel_and_save_stay_in_home(self):
        w=self.window;p,i=self.project()
        for kind,action in [('initiative',w.home.add_initiative),('task',w.home.add_task)]:
            before=w.projects.items(p);action();self.assertEqual(w.areas.currentWidget(),w.home)
            self.assertTrue(w.editor.isVisible());self.assertEqual(w.editor.draft_kind,kind)
            w.title.setText('Draft')
            with patch.object(QMessageBox,'question',return_value=QMessageBox.Discard):w.editor.close_editor()
            self.assertEqual(w.projects.items(p),before)
        w.home.add_task();w.title.setText('Compare lighting');w.goal.setPlainText('Three options')
        w.editor.commit();task=w.projects.get(w.scope)
        self.assertEqual(task['parent'],i);self.assertEqual(task['goal'],'Three options');self.assertEqual(task['kind'],'research')
        self.assertFalse(w.editor.isVisible());self.assertEqual(w.areas.currentWidget(),w.home)
        w.home.plan(task['id']);self.assertEqual(w.title.text(),'Compare lighting');self.assertTrue(w.editor.isVisible())

    def test_material_is_staged_and_scoped(self):
        w=self.window;p,i=self.project();w.home.edit_material();material=w.editor.material
        material.kind.setCurrentIndex(material.kind.findData('url'));material.address.setText('https://example.org/source')
        material.stage();self.assertEqual(w.projects.get(i)['resources'],[])
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):w.home.add_task()
        self.assertEqual(w.tabs.currentIndex(),1);self.assertEqual(w.scope,i)
        w.editor.commit();self.assertEqual(w.projects.get(i)['resources'][0]['target'],'https://example.org/source')
        self.assertEqual(w.library.get(p)['resources'],[])
        w.home.edit_material();material.kind.setCurrentIndex(material.kind.findData('note'));material.note.setPlainText('New note');w.editor.commit()
        self.assertIn('New note',w.projects.get(i)['notes']);self.assertEqual(w.library.get(p)['notes'],'Project note')

    def test_unknown_parent_creates_nothing_on_open_or_cancel(self):
        w=self.window;p=w.library.create('Empty',resources=[]);w.home.refresh();w.home.choose('project:'+p)
        w.home.add_task();self.assertFalse(w.editor.apply.isEnabled());self.assertTrue(w.editor.missing.isVisible())
        w.editor.close_editor();self.assertEqual(w.projects.items(p),[])

    def test_dirty_editor_is_not_saved_by_sync_or_poll(self):
        w=self.window;p,i=self.project();w.home.plan(i);w.notes.setPlainText('Keep draft')
        from projects_sync_ui import run
        with patch('projects_sync.read_state') as sync:run(w);sync.assert_not_called()
        w.poll_runs();self.assertEqual(w.notes.toPlainText(),'Keep draft');self.assertEqual(w.projects.get(i)['notes'],'Initiative note')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):w.show_home()
        self.assertTrue(w.editor.isVisible());self.assertEqual(w.notes.toPlainText(),'Keep draft')

    def test_repeat_preserves_identity_and_custom_interval(self):
        w=self.window;p,i=self.project();t=w.projects.add(p,i,'Weekly','research',interval=7200)
        w.home.plan(t);self.assertEqual(w.interval.currentData(),7200);w.schedule.setChecked(True)
        with patch('projects_runner.install_timer') as install:w.editor.commit();install.assert_called_once()
        self.assertEqual(w.projects.get(t)['interval'],7200);self.assertTrue(w.projects.get(t)['enabled'])
        self.assertEqual(len(w.projects.items(p,i)),1)
        w.home.plan(t);w.schedule.setChecked(False);w.editor.commit();self.assertFalse(w.projects.get(t)['enabled'])

    def test_stale_scope_save_rejected_without_losing_draft(self):
        w=self.window;p,i=self.project();w.home.plan(i);w.notes.setPlainText('Local draft');w.projects.update(i,notes='External change')
        with self.assertRaises(ValueError):w.save()
        self.assertEqual(w.notes.toPlainText(),'Local draft');self.assertEqual(w.projects.get(i)['notes'],'External change')

    def test_old_room_note_keeps_owner(self):
        from file_spaces import Catalog
        w=self.window;p,i=self.project();room=w.home.links.ensure(p)
        Catalog(w.workplace.store).put('room',dict(room,note='Original room note'),room)
        w.home.refresh();record=w.home.record_chain()[0];w.home.edit_note(record)
        w.notes.setPlainText('Updated room note');w.editor.commit()
        self.assertEqual(w.home.links.room(p)['note'],'Updated room note');self.assertEqual(w.library.get(p)['notes'],'Project note')

    def test_wissen_selection_keeps_reference_and_ignores_stale_load(self):
        w=self.window;p,i=self.project();w.home.edit_material();m=w.editor.material;m.kind.setCurrentIndex(m.kind.findData('wissen'))
        ref=dict(app='wissen',kind='record',id='test-note',title='Existing note')
        with patch.object(w.workplace,'job') as job:m.choose();callback=job.call_args.args[2]
        callback([ref],'');m.knowledge.setCurrentRow(0);m.choose();w.editor.commit()
        self.assertTrue(w.projects.get(i)['resources'][0]['target'].startswith('lumen:'))
        w.home.edit_material();m.reset();callback([dict(ref,title='Stale')],'');self.assertEqual(m.knowledge.count(),0)

    def test_empty_creation_can_leave_and_close_without_writing(self):
        w=self.window;p,i=self.project();w.home.add_task();w.show_home()
        self.assertEqual(w.projects.items(p,i),[]);self.assertFalse(w.editor.draft_kind)
        w.create();self.assertTrue(w.close());self.assertEqual(len(w.library.all()),1)

    def test_readonly_and_existing_results_remain_inspectable(self):
        w=self.window;p,i=self.project();task=w.projects.add(p,i,'Review','analysis')
        run=w.projects.begin_run(task,{});w.projects.finish_run(run,'done','Existing result')
        w.library.update(p,server_bound=True,server_role='reader')
        w.home.plan(task);self.assertFalse(w.editor.apply.isEnabled());self.assertTrue(w.notes.isReadOnly())
        w.editor.show_page(3);self.assertEqual(w.result.toPlainText(),'Existing result')
        w.poll_runs();self.assertEqual(w.tabs.currentIndex(),3)

    def test_cancel_context_change_keeps_task_editor(self):
        w=self.window;p,i=self.project();task=w.projects.add(p,i,'Review','analysis');w.home.plan(task)
        w.goal.setPlainText('Unfinished draft')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):w.home.edit_material()
        self.assertEqual(w.scope,task);self.assertEqual(w.tabs.currentIndex(),2);self.assertEqual(w.goal.toPlainText(),'Unfinished draft')

    def test_escape_keeps_dirty_draft_when_cancelled(self):
        from PySide6.QtTest import QTest
        w=self.window;p,i=self.project();w.home.add_task();w.title.setText('Keep me');w.title.setFocus();self.app.processEvents()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):QTest.keyClick(w.title,Qt.Key_Escape)
        self.assertTrue(w.editor.isVisible());self.assertEqual(w.title.text(),'Keep me');self.assertEqual(w.projects.items(p,i),[])

    def test_environment_is_embedded_and_preserves_other_project_content(self):
        from file_spaces import Catalog
        w=self.window;p,i=self.project();room=w.home.links.ensure(p)
        room=Catalog(w.workplace.store).put('room',dict(room,note='Keep legacy note',pins=[dict(kind='url',title='Pinned',url='https://example.org')]),room)
        w.home.edit_environment();env=w.editor.environment
        self.assertEqual(w.areas.currentWidget(),w.home)
        self.assertEqual(w.tabs.currentWidget(),env)
        self.assertFalse(env.isWindow())
        env.add_source('Source',str(w.library.root));env.urls.setPlainText('https://example.com')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):w.show_home()
        self.assertIs(w.editor.environment,env)
        self.assertEqual(w.home.links.room(p),room)
        w.editor.commit();saved=w.home.links.room(p)
        self.assertEqual(saved['sources'][0]['label'],'Source')
        self.assertEqual(saved['note'],'Keep legacy note');self.assertEqual(saved['pins'],room['pins'])
        self.assertEqual(w.library.get(p)['notes'],'Project note')
        self.assertIsNone(w.editor.environment)

    def test_environment_discard_and_stale_save(self):
        from file_spaces import Catalog
        w=self.window;p,i=self.project();w.home.edit_environment();env=w.editor.environment
        before=w.home.links.room(p);env.urls.setPlainText('https://example.com')
        external=Catalog(w.workplace.store).put('room',dict(before,note='Concurrent note'),before)
        with self.assertRaises(ValueError):w.save()
        self.assertEqual(w.home.links.room(p),external)
        self.assertEqual(env.urls.toPlainText(),'https://example.com')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Discard):w.editor.close_editor()
        self.assertEqual(w.home.links.room(p),external)
        self.assertIsNone(w.editor.environment)

    def test_environment_respects_readonly_project(self):
        w=self.window;p,i=self.project();w.library.update(p,server_bound=True,server_role='reader')
        w.home.edit_environment()
        self.assertFalse(w.editor.environment.isEnabled())
        self.assertFalse(w.editor.apply.isEnabled())
        with self.assertRaises(ValueError):w.save()
