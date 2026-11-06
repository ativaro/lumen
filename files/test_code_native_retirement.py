"""Retire local Code producers while preserving ordinary approved desktop tasks."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lumen_store import Store
from lumen_tasks import run_steps,tick


class CodeNativeRetirementTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=Store(self.root/'state')

    def workflow(self,name='Ordinary'):
        target=self.root/(name+'.txt')
        key=self.store.save_workflow(name,[dict(action='write',path=str(target),text='Approved own output')],
            [str(self.root)],trigger='interval',interval=60,enabled=True,approved=True,now=100)
        return key,target

    def test_due_code_flows_are_not_produced_but_ordinary_native_workflow_runs(self):
        ordinary,target=self.workflow();old,forbidden=self.workflow('OldCode')
        with self.store.connect() as db:db.execute('UPDATE workflows SET code_plan=? WHERE id=?',('{"legacy":"fixture"}',old))
        queued=self.store.enqueue_due(now=161)
        self.assertEqual(len(queued),1);self.assertEqual(self.store.task(queued[0])['title'],'Ordinary')
        run_steps(self.store,queued[0]);self.assertEqual(target.read_text(),'Approved own output')
        self.assertFalse(forbidden.exists());self.assertEqual(self.store.task(queued[0])['status'],'completed')
        oldrow=next(row for row in self.store.workflows() if row['id']==old)
        self.assertEqual(oldrow['next_run'],160);self.assertEqual(oldrow['code_plan'],'{"legacy":"fixture"}')




    def test_linked_legacy_flow_is_not_run_or_enabled(self):
        old,target=self.workflow('OldLinked')
        with self.store.connect() as db:
            db.execute('CREATE TABLE code_library(id TEXT,kind TEXT,definition TEXT)')
            db.execute('INSERT INTO code_library VALUES (?,?,?)',('old-code','automation','{"workflow_id":"'+old+'"}'))
        self.assertEqual(self.store.enqueue_due(now=161),[])
        with self.assertRaisesRegex(ValueError,'Lumen Server'):self.store.set_workflow_enabled(old,True)
        self.store.set_workflow_enabled(old,False);self.assertFalse(target.exists())

    def test_old_queued_code_is_closed_once_while_ordinary_task_completes(self):
        target=self.root/'forbidden.txt'
        old=self.store.create_task('Old code',directory=str(self.root),roots=[str(self.root)],steps=[dict(action='write',path=str(target),text='Never')],approved=True,status='queued')
        self.store.event(old,'code-library','old-code')
        ordinary=self.store.create_task('Own task',directory=str(self.root),roots=[str(self.root)],steps=[dict(action='write',path=str(self.root/'ordinary.txt'),text='Preserved')],approved=True,status='queued')
        with patch('transfer_followup.tick'),patch('lumen_tasks.defer_background',return_value=''):
            tick(self.store);before=self.store.task(old);tick(self.store)
        self.assertEqual(before['status'],'failed');self.assertIn('Lumen Server',before['error'])
        self.assertEqual(self.store.task(old)['updated'],before['updated']);self.assertFalse(target.exists())
        self.assertEqual(self.store.task(ordinary)['status'],'completed');self.assertEqual((self.root/'ordinary.txt').read_text(),'Preserved')

    def test_direct_old_code_configuration_and_execution_have_no_effects(self):
        with self.assertRaisesRegex(ValueError,'Lumen Server'):self.store.save_workflow('Code',[],[str(self.root)],code_plan='{}')
        with self.assertRaisesRegex(ValueError,'Lumen Server'):self.store.save_workflow('Code',[],[str(self.root)],collection_entry=('old',1))
        target=self.root/'forbidden.txt'
        task=self.store.create_task('Old code',directory=str(self.root),roots=[str(self.root)],steps=[dict(action='write',path=str(target),text='Never')],approved=True,status='queued')
        self.store.event(task,'code-flow','old-code')
        with self.assertRaisesRegex(ValueError,'Lumen Server'):self.store.update_task(task,status='running')
        with self.assertRaisesRegex(ValueError,'Lumen Server'):run_steps(self.store,task)
        self.assertFalse(target.exists());self.assertFalse(self.store.task(task)['result'])
