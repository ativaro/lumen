"""Real UI trash paths preserve originals, revisions, roles and schedules."""
import os,tempfile,unittest
import json
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QCoreApplication,QEvent,QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMenu,QMessageBox,QPushButton

class ProjectTrashTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from app import create_app
  cls.app=QApplication.instance() or create_app()
 def setUp(self):
  self.tmp=self.enterContext(tempfile.TemporaryDirectory());self.root=Path(self.tmp)
  self.enterContext(patch.dict(os.environ,LUMEN_TOOLS_DATA=self.tmp,LUMEN_DATA=self.tmp+'/state',XDG_CONFIG_HOME=self.tmp+'/config'))
  from tools_workbench import Workbench
  self.w=Workbench(self.root);self.w.error=lambda text:self.fail(text)
  self.original=self.root/'original.txt';self.original.write_text('Keep original')
  self.resource=dict(kind='file',title='Original',target=str(self.original))
  self.key=self.w.library.create('Projekt',notes='Keep notes',resources=[self.resource],references=[])
  self.parent=self.w.projects.add(self.key,'','Vorhaben','initiative',notes='Keep initiative')
  self.task=self.w.projects.add(self.key,self.parent,'Analyse','analysis',goal='Keep goal',resources=[self.resource],enabled=True,next_run=4000000000)
  self.w.home.choose(self.key);self.w.show();QTest.qWait(10)
 def tearDown(self):
  self.w.editor.discard();self.w.journal.question.clear();self.w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);self.app.processEvents()
 def state(self,item=None):
  from projects_trash import state
  return state(self.w.journal.record,self.w.projects.get(item) if item else None)
 def confirm(self,value=QMessageBox.Yes):return patch.object(self.w.project_trash,'confirm',return_value=value==QMessageBox.Yes)
 def test_native_confirmation_has_explicit_labels_plaintext_and_cancel_default(self):
  w=self.w
  for choice in ('Abbrechen','In den Papierkorb'):
   observed=[]
   def choose():
    dialog=self.app.activeModalWidget()
    if isinstance(dialog,QMessageBox):
     observed.append(([b.text() for b in dialog.buttons()],dialog.defaultButton().text(),dialog.textFormat()))
     next(b for b in dialog.buttons() if b.text()==choice).click()
   QTimer.singleShot(0,choose);w.project_trash.perform(self.state())
   self.assertEqual(set(observed[0][0]),{'Abbrechen','In den Papierkorb'});self.assertEqual(observed[0][1],'Abbrechen');self.assertEqual(observed[0][2],Qt.PlainText)
   self.assertEqual(w.library.get(self.key)['_archived'],choice=='In den Papierkorb')
 def test_overview_keyboard_cancel_trash_and_restore_preserve_ids_and_original(self):
  w=self.w;w.show_home();card=w.home.overview.cards[0];card.setFocus()
  with self.confirm(QMessageBox.Cancel):QTest.keyClick(card,Qt.Key_Delete)
  self.assertFalse(w.library.get(self.key)['_archived']);self.assertTrue(w.projects.get(self.task)['enabled'])
  with self.confirm():QTest.keyClick(card,Qt.Key_Delete)
  self.assertTrue(w.library.get(self.key)['_archived']);self.assertFalse(w.projects.get(self.task)['enabled'])
  w.home.overview.archive.click();QTest.qWait(10);card=w.home.overview.cards[0];card.setFocus()
  with self.confirm() as question:QTest.keyClick(card,Qt.Key_Delete);question.assert_not_called()
  saved=w.library.get(self.key);self.assertFalse(saved['_archived']);self.assertEqual(saved['resources'],[self.resource]);self.assertEqual(saved['notes'],'Keep notes')
  self.assertEqual(w.projects.get(self.task)['parent'],self.parent);self.assertFalse(w.projects.get(self.task)['enabled']);self.assertEqual(self.original.read_text(),'Keep original')
 def test_detail_and_child_trash_are_reachable_and_parent_restore_is_ordered(self):
  w=self.w
  with self.confirm():w.project_trash.perform(self.state(self.parent))
  w.journal.trash_filter.click();self.assertIn('Vorhaben',w.journal.visible_titles);self.assertIn('Analyse',w.journal.visible_titles)
  task=w.journal.entry_menus[self.task].actions()[1];self.assertFalse(task.isEnabled())
  w.journal.entry_menus[self.parent].actions()[1].trigger();self.assertFalse(w.projects.get(self.parent)['archived'])
  self.assertFalse(w.projects.get(self.task)['enabled']);w.journal.trash_filter.setChecked(False)
  w.navigate(self.key,self.task)
  with self.confirm():w.editor.archive.trigger()
  self.assertTrue(w.projects.get(self.task)['archived']);w.journal.trash_filter.setChecked(True)
  w.journal.entry_menus[self.task].actions()[1].trigger();self.assertFalse(w.projects.get(self.task)['archived'])
  with self.confirm():w.journal.project_archive.trigger()
  self.assertTrue(w.library.get(self.key)['_archived']);w.journal.project_archive.trigger();self.assertFalse(w.library.get(self.key)['_archived'])
 def test_stale_view_and_revision_change_during_confirmation_are_noops(self):
  w=self.w;expected=self.state();w.library.update(self.key,notes='External')
  with self.confirm(),self.assertRaises(ValueError):w.project_trash.perform(expected)
  self.assertFalse(w.library.get(self.key)['_archived']);self.assertTrue(w.projects.get(self.task)['enabled'])
  w.home.refresh();expected=self.state()
  def changed(*_):w.library.update(self.key,goal='New goal');return True
  with patch.object(w.project_trash,'confirm',side_effect=changed),self.assertRaises(ValueError):w.project_trash.perform(expected)
  self.assertEqual(w.library.get(self.key)['goal'],'New goal');self.assertFalse(w.library.get(self.key)['_archived'])
 def test_stale_overview_card_keeps_the_displayed_revision(self):
  w=self.w;w.show_home();card=w.home.overview.cards[0];card.setFocus();w.library.update(self.key,notes='Changed after rendering')
  with patch.object(w,'error') as error,self.confirm():QTest.keyClick(card,Qt.Key_Delete);error.assert_called_once()
  saved=w.library.get(self.key);self.assertFalse(saved['_archived']);self.assertEqual(saved['notes'],'Changed after rendering');self.assertTrue(w.projects.get(self.task)['enabled'])
 def test_reader_and_revoked_role_do_not_mutate(self):
  w=self.w;expected=self.state();w.library.update(self.key,server_bound=True,server_role='reader')
  with self.confirm(),self.assertRaises(ValueError):w.project_trash.perform(expected)
  self.assertFalse(w.library.get(self.key)['_archived']);self.assertTrue(w.projects.get(self.task)['enabled'])
  w.home.refresh();self.assertFalse(w.journal.project_archive.isEnabled())
 def test_running_waiting_or_queued_children_block_without_changing_history(self):
  w=self.w
  for status in ('running','waiting','queued'):
   w.projects.update(self.task,status=status);w.home.refresh()
   with self.confirm(),self.assertRaises(ValueError):w.project_trash.perform(self.state())
   self.assertFalse(w.library.get(self.key)['_archived']);self.assertEqual(w.projects.get(self.task)['status'],status);self.assertTrue(w.projects.get(self.task)['enabled'])
 def test_dirty_active_editor_action_never_saves_before_rejection(self):
  w=self.w;w.navigate(self.key,self.task);w.goal.setPlainText('Unsaved goal');w.interval.setCurrentIndex(0)
  w.projects.update(self.task,status='running')
  def stored():
   with w.library.connect() as db:return ([tuple(r) for r in db.execute('SELECT * FROM records')],[tuple(r) for r in db.execute('SELECT * FROM project_items')],[tuple(r) for r in db.execute('SELECT * FROM project_runs')])
  before=stored()
  with patch.object(w,'error') as error,self.confirm(QMessageBox.Save) as question:w.editor.archive.trigger();error.assert_called_once();question.assert_not_called()
  self.assertEqual(stored(),before);self.assertEqual(w.goal.toPlainText(),'Unsaved goal');self.assertEqual(w.projects.get(self.task)['goal'],'Keep goal')
 def test_unlink_changes_only_the_selected_reference_and_keeps_flow(self):
  w=self.w;flow=w.project_store.save_workflow('Original flow',[dict(action='open',path=str(self.original))],[str(self.root)],approved=True)
  with w.library.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS project_flows(flow TEXT PRIMARY KEY,project TEXT NOT NULL,scope TEXT NOT NULL DEFAULT "")');db.execute('INSERT INTO project_flows VALUES(?,?,?)',(flow,self.key,''))
  w.home.refresh()
  action=w.journal.material_controls[self.resource['target']].findChild(QMenu).actions()[1]
  with self.confirm(QMessageBox.Cancel):action.trigger()
  self.assertEqual(w.library.get(self.key)['resources'],[self.resource])
  with self.confirm():action.trigger()
  self.assertEqual(w.library.get(self.key)['resources'],[]);self.assertEqual(self.original.read_text(),'Keep original')
  QTest.qWait(10)
  control=next(c for c in w.journal.findChildren(QPushButton) if c.isVisible() and c.accessibleName()=='Original flow')
  with self.confirm():control.findChild(QMenu).actions()[1].trigger()
  self.assertEqual(w.project_store.workflows()[0]['id'],flow)
  with w.library.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM project_flows').fetchone()[0],0)
 def test_queued_run_blocks_and_finished_history_survives_restore(self):
  w=self.w;data=json.dumps(dict(result='Past result',snapshot=dict(goal='Original goal')))
  with w.library.connect() as db:db.execute('INSERT INTO project_runs VALUES(?,?,?,?,?,?)',('run',self.task,1,None,'queued',data))
  with self.confirm(),self.assertRaises(ValueError):w.project_trash.perform(self.state(self.parent))
  with w.library.connect() as db:db.execute('UPDATE project_runs SET status="done",finished=2 WHERE id="run"')
  original=w.projects.runs(self.task)
  with self.confirm():w.project_trash.perform(self.state())
  w.project_trash.perform(self.state());self.assertEqual(w.projects.runs(self.task),original);self.assertFalse(w.projects.get(self.task)['enabled'])
 def test_reference_and_server_attachment_unlink_preserve_other_associations(self):
  w=self.w;ref=dict(kind='chat',title='Conversation',chat=dict(directory=str(self.root),session='ses_demo'))
  attachment=dict(kind='file',id='fe489edd-903c-44e0-ac05-25299c06b224',title='Server file')
  w.library.update(self.key,references=[ref],server_attachments=[attachment],server_bound=True,server_role='editor');w.home.refresh()
  with self.confirm():w.project_trash.unlink(self.state(),'references',ref)
  self.assertEqual(w.library.get(self.key)['server_attachments'],[attachment])
  with self.confirm():w.project_trash.unlink(self.state(),'server_attachments',attachment)
  saved=w.library.get(self.key);self.assertEqual(saved['references'],[]);self.assertEqual(saved['server_attachments'],[]);self.assertEqual(saved['resources'],[self.resource]);self.assertEqual(self.original.read_text(),'Keep original')
 def test_no_delete_shortcut_in_question_editor(self):
  w=self.w;w.journal.question.setFocus();w.journal.question.setPlainText('Unsent question');w.journal.question.moveCursor(QTextCursor.Start)
  with patch.object(w.project_trash,'confirm') as question:QTest.keyClick(w.journal.question,Qt.Key_Delete);question.assert_not_called()
  self.assertFalse(w.library.get(self.key)['_archived'])
