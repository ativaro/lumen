import json
import tempfile
import unittest
from code_flow import encode,parse
from code_library import Collection
from code_flow_native import configure
from code_library_execution import prepare_run
from lumen_store import Store


def plan(**extra):
    return dict(trigger='interval',minutes=15,watch='',cron='0 9 * * *',timezone='Europe/Zurich',steps=[{'title':'Prüfen','prompt':'Nenne offene Punkte'}],condition='changed',outputs=['task_draft'],source_ids=[],service_ids=[],**extra)


class FlowTest(unittest.TestCase):
    def test_frozen_tool_plan_pause_and_transactional_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);collection=Collection(store)
            entry=collection.create('automation','Check',value={'flow':encode(plan())})
            entry=configure(collection,entry,True);flow=store.workflows()[0]
            self.assertFalse(flow['enabled']);self.assertTrue(flow['approved'])
            task=prepare_run(collection,entry['id']);store.update_task(task,status='running')
            store.update_task(task,status='completed',result='Offener Termin')
            drafts=store.rows("SELECT * FROM tasks WHERE status='draft' AND id!=?",(task,));self.assertEqual(len(drafts),1);self.assertFalse(drafts[0]['approved'])
            # Repeating the completion cannot create a second draft.
            with self.assertRaises(ValueError):store.update_task(task,status='completed',result='Offener Termin')
            task2=prepare_run(collection,entry['id']);store.update_task(task2,status='running');store.update_task(task2,status='completed',result='Offener Termin')
            self.assertEqual(len(store.rows("SELECT id FROM tasks WHERE status='draft'")),1)
            task3=prepare_run(collection,entry['id']);store.update_task(task3,status='running')
            entry=collection.get(entry['id']);p=plan();p['steps'][0]['prompt']='Geänderte Prüfung'
            collection.update(entry['id'],entry['revision'],definition={**entry['definition'],'flow':encode(p)})
            with self.assertRaisesRegex(ValueError,'geändert oder pausiert'):store.update_task(task3,status='completed',result='Kein neuer Entwurf')
            self.assertEqual(store.task(task3)['status'],'running');self.assertFalse(store.workflows()[0]['approved'])

    def test_scheduler_revision_and_archive_invalidate_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);collection=Collection(store);entry=configure(collection,collection.create('automation','Check',value={'flow':encode(plan())}),True)
            flow=store.workflows()[0];store.set_workflow_enabled(flow['id'],True)
            task=store.enqueue_due(now=store.workflows()[0]['next_run']+1)[0];store.update_task(task,status='running')
            entry=collection.get(entry['id']);collection.update(entry['id'],entry['revision'],archived=True)
            with self.assertRaises(ValueError):store.update_task(task,status='completed',result='Must not publish')
            self.assertFalse(store.rows("SELECT id FROM tasks WHERE status='draft'"))

    def test_manual_result_publishes_one_durable_notification(self):
        import os
        from pathlib import Path
        from unittest.mock import patch
        from lumen_notifications import snapshot
        from code_flow_native import deliver
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'XDG_STATE_HOME':tmp}),patch('lumen_notifications.toast'):
            store=Store(tmp+'/state');collection=Collection(store);p=plan();p['outputs']=['notify']
            entry=configure(collection,collection.create('automation','Check',value={'flow':encode(p)}),True)
            task=prepare_run(collection,entry['id']);store.update_task(task,status='running');store.update_task(task,status='completed',result='Ein Ergebnis')
            deliver(store)
            cards=snapshot(wake=False)['items'];self.assertEqual(len(cards),1);self.assertEqual(cards[0]['target'],'local-task:'+task)

    def test_portable_template_uses_current_flow_without_sources(self):
        from code_library_contract import export_template
        p=plan();p['steps'][0]['prompt']='Aktuelle Anweisung';p['source_ids']=['00000000-0000-0000-0000-000000000001']
        template=export_template({'kind':'automation','title':'Check','description':'','definition':{'prompt':'Alte Anweisung','flow':encode(p)}})
        self.assertIn('Aktuelle Anweisung',template['definition']['prompt']);self.assertNotIn('Alte Anweisung',template['definition']['prompt'])
        self.assertEqual(set(template['definition']),{'prompt'});self.assertNotIn(p['source_ids'][0],json.dumps(template))

    def test_untrusted_plan_validation(self):
        p=plan()
        for change in ({'outputs':[{}]},{'minutes':True},{'steps':[]},{'source_ids':['not-a-uuid']},{'outputs':['shell']}):
            with self.assertRaises(ValueError):parse(json.dumps({**p,**change}))
        with self.assertRaises(ValueError):parse(json.dumps({**p,'extra':'secret'}))


if __name__=='__main__':unittest.main()
