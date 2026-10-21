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

    def test_collection_linked_workflow_and_new_code_configuration_are_closed(self):
        from code_library import Collection
        old,forbidden=self.workflow('LinkedCode');collection=Collection(self.store)
        entry=collection.create('automation','Own old code',value=dict(workflow_id=old))
        self.assertEqual(self.store.enqueue_due(now=161),[])
        with self.assertRaisesRegex(ValueError,'Lumen Server'):self.store.set_workflow_enabled(old,True)
        self.store.set_workflow_enabled(old,False)
        self.assertFalse(next(row for row in self.store.workflows() if row['id']==old)['enabled'])
        with self.assertRaisesRegex(ValueError,'Lumen Server'):
            self.store.save_workflow('Code',[],[str(self.root)],prompt='Keep',code_plan='{"legacy":"fixture"}')
        with self.assertRaisesRegex(ValueError,'Lumen Server'):
            self.store.save_workflow('Code',[],[str(self.root)],prompt='Keep',collection_entry=(entry['id'],entry['revision']))
        with self.assertRaisesRegex(ValueError,'Lumen Server'):
            self.store.save_workflow('Replaced',[],[str(self.root)],prompt='Keep',workflow=old)
        self.assertEqual(self.store.workflows()[0]['name'],'LinkedCode')
        self.assertFalse(forbidden.exists());self.assertEqual(len(self.store.workflows()),1)

    def test_tick_closes_old_queued_code_once_without_delivery_or_block_worker(self):
        target=self.root/'forbidden.txt'
        old=self.store.create_task('Own old code',directory=str(self.root),roots=[str(self.root)],
            steps=[dict(action='write',path=str(target),text='Must not happen')],approved=True,status='queued')
        self.store.event(old,'code-library','synthetic-entry')
        ordinary=self.store.create_task('Own task',directory=str(self.root),roots=[str(self.root)],
            steps=[dict(action='write',path=str(self.root/'ordinary.txt'),text='Preserved')],approved=True,status='queued')
        with patch('transfer_followup.tick'),patch('lumen_tasks.defer_background',return_value=''), \
                patch('code_blocks_worker.run_pending') as blocks,patch('code_flow_native.deliver') as deliver:
            tick(self.store);before=self.store.task(old);tick(self.store)
        blocks.assert_not_called();deliver.assert_not_called()
        self.assertEqual(before['status'],'failed');self.assertIn('Lumen Server',before['error'])
        self.assertEqual(self.store.task(old)['updated'],before['updated'])
        self.assertFalse(target.exists());self.assertEqual((self.root/'ordinary.txt').read_text(),'Preserved')
        self.assertEqual(self.store.task(ordinary)['status'],'completed')

    def test_explicit_old_code_task_and_entry_actions_fail_without_effects(self):
        import code_flow_native as flow
        import code_blocks_worker as blocks
        import code_library_execution as execution
        target=self.root/'forbidden.txt'
        task=self.store.create_task('Own old Code',directory=str(self.root),roots=[str(self.root)],
            steps=[dict(action='write',path=str(target),text='Must not happen')],approved=True,status='queued')
        self.store.event(task,'code-flow','synthetic-old-plan')
        for action in (lambda:flow.configure(None,None),lambda:flow.deliver(self.store),lambda:flow.deliver_notes(self.store),
                       lambda:execution.prepare_run(None,'own-old-entry'),lambda:blocks.run_pending(None),
                       lambda:blocks.execute(None,'own-old-run')):
            with self.subTest(action=action),self.assertRaisesRegex(ValueError,'Lumen Server'):action()
        for state in ('running','completed'):
            with self.subTest(state=state),self.assertRaisesRegex(ValueError,'Lumen Server'):
                self.store.update_task(task,status=state,result='Unpublished')
        with self.assertRaisesRegex(ValueError,'Lumen Server'):run_steps(self.store,task)
        self.assertFalse(target.exists());self.assertFalse(self.store.task(task)['result'])
        self.assertEqual(self.store.task(task)['status'],'failed')
