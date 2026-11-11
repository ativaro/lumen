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

    def test_direct_old_code_execution_has_no_effects(self):
        target=self.root/'forbidden.txt'
        task=self.store.create_task('Old code',directory=str(self.root),roots=[str(self.root)],steps=[dict(action='write',path=str(target),text='Never')],approved=True,status='queued')
        self.store.event(task,'code-flow','old-code')
        with self.assertRaisesRegex(ValueError,'Lumen Server'):self.store.update_task(task,status='running')
        with self.assertRaisesRegex(ValueError,'Lumen Server'):run_steps(self.store,task)
        self.assertFalse(target.exists());self.assertFalse(self.store.task(task)['result'])

    def test_enabled_automatic_rows_of_older_versions_never_start(self):
        with self.store.connect() as db:
            db.execute('INSERT INTO workflows (id,name,steps,roots,trigger,interval,watch,enabled,next_run,fingerprint,updated,approved,prompt,code_plan) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('old','Alt','[{"action":"diagnose"}]','[]','interval',60,'',1,0,'',0,1,'',''))
        with patch('transfer_followup.tick'),patch('lumen_tasks.defer_background',return_value=''):tick(self.store)
        self.assertEqual(self.store.tasks(),[]);self.assertEqual(self.store.file_actions(),[])
        for name in ('enqueue_due','save_workflow','set_workflow_enabled','workflows'):self.assertFalse(hasattr(self.store,name),name)
