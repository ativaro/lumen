import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from code_blocks import node,parse,encode,generated
from code_library import Collection
from code_blocks_run import Runs,write_file
from lumen_store import Store
from lumen_jobs import Job


class BlocksTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/'input.txt';self.source.write_text('Ein echter Beleg: 42 CHF. Termin fehlt.')
        self.env=patch.dict(os.environ,{'XDG_DATA_HOME':str(self.root/'data'),'XDG_STATE_HOME':str(self.root/'state'),'LUMEN_TOOLS_DATA':str(self.root/'tools')});self.env.start();self.addCleanup(self.env.stop)
        self.store=Store(self.root/'lumen');self.collection=Collection(self.store);self.runs=Runs(self.collection);self.job=Job(lambda _:None)

    def create(self,kinds=None,testing=True):
        nodes=[node(k, str(self.source) if k=='read_file' else 'Fasse zusammen' if k=='ai' else str(self.root) if k=='save_file' else '') for k in kinds or ['manual','read_file','ai','approval','save_file','save_note','create_task','notify']]
        entry=self.collection.create('automation','Belege',value={'flow':encode(dict(version=2,nodes=nodes))})
        self.entry=entry;return self.runs.create(entry['id'],testing)

    def drain(self,run):
        self.runs.resume(run['id'])
        for _ in range(20):
            value=self.runs.advance(run['id'],self.job)
            if value:self.runs.ai_done(run['id'],json.dumps({'text':'42 CHF; Termin offen'}),value['attempt'])
            current=self.runs.get(run['id'])
            if current['status']!='running':return current
        self.fail('Run did not finish')

    def test_test_run_approval_and_all_outputs_are_isolated(self):
        run=self.create();run=self.drain(run);self.assertEqual(run['status'],'waiting')
        self.assertEqual(run['data']['steps'][1]['output']['text'],self.source.read_text())
        self.runs.control(run['id'],'approve');run=self.drain(run)
        self.assertEqual(run['status'],'completed');self.assertEqual([s['attempts'] for s in run['data']['steps']],[1]*8)
        self.assertEqual(len(list((self.store.directory/'block-tests'/run['id']).glob('*.json'))),4)
        self.assertFalse(list(self.root.glob('Lumen-*.md')))
        self.assertFalse((self.root/'tools').exists());self.assertFalse((self.root/'state/lumen/notifications.sqlite3').exists())

    def test_live_effects_replay_and_failure_resume(self):
        from lumen_notifications import snapshot
        from wissen_data import Notebook
        notebook=self.root/'notebook';notebook.mkdir();self.store.set_setting('knowledge/notebook',str(notebook))
        run=self.create(['manual','read_file','save_file','save_note','create_task','notify'],False)
        # A missing output directory fails without repeating the already read file.
        self.runs.resume(run['id']);self.runs.advance(run['id'],self.job);self.runs.advance(run['id'],self.job)
        with patch('code_blocks_run.write_file',side_effect=PermissionError('Kein Schreibrecht')):self.runs.advance(run['id'],self.job)
        self.assertEqual(self.runs.get(run['id'])['status'],'error')
        with patch('lumen_notifications.toast'):run=self.drain(run)
        self.assertEqual(run['status'],'completed');self.assertEqual([s['attempts'] for s in run['data']['steps']],[1,1,2,1,1,1])
        self.assertEqual(len(list(self.root.glob('Lumen-*.md'))),1)
        effects=[s['output'].get('effect') for s in run['data']['steps'][2:]]
        before=snapshot(wake=False)['items'];self.assertEqual(len(before),1)
        # Replay a committed action before its checkpoint (crash window).
        with patch('lumen_notifications.toast'):
            for i in range(2,len(run['plan']['nodes'])):
                self.assertEqual(self.runs.effect(run,run['plan']['nodes'][i],run['data']['steps'][i]['input'],self.job)['effect'],effects[i-2])
        self.assertEqual(len(snapshot(wake=False)['items']),1)
        from inbox_data import store
        with store().connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM tasks').fetchone()[0],1)
        self.assertEqual(len(Notebook(self.store).scan()['notes']),1)

    def test_pause_stale_ai_and_resume(self):
        run=self.create(['manual','read_file','ai','ai','notify']);self.runs.resume(run['id'])
        self.runs.advance(run['id'],self.job);self.runs.advance(run['id'],self.job)
        first=self.runs.advance(run['id'],self.job);self.runs.control(run['id'],'pause')
        self.runs.resume(run['id']);second=self.runs.advance(run['id'],self.job)
        self.runs.ai_done(run['id'],'{"text":"late"}',first['attempt'])
        self.assertEqual(self.runs.get(run['id'])['data']['steps'][2]['status'],'running')
        self.runs.ai_done(run['id'],'{"text":"fresh"}',second['attempt']);third=self.runs.advance(run['id'],self.job)
        self.runs.ai_done(run['id'],'{"text":"late"}',second['attempt'])
        self.assertEqual(self.runs.get(run['id'])['data']['steps'][3]['status'],'running')
        self.runs.ai_done(run['id'],'{"text":"final"}',third['attempt'])
        self.runs.advance(run['id'],self.job);self.assertEqual(self.runs.get(run['id'])['status'],'completed')

    def test_fence_archive_and_plan_changes(self):
        run=self.create();self.runs.resume(run['id']);self.runs.advance(run['id'],self.job)
        self.collection.update(self.entry['id'],self.entry['revision'],archived=True)
        with self.assertRaisesRegex(ValueError,'archiviert'):self.runs.advance(run['id'],self.job)
        self.assertFalse(list(self.root.glob('Lumen-*')))

    def test_pdf_else_skips_write_path(self):
        run=self.create(['manual','read_file','if_pdf','ai','approval','save_file','notify']);run=self.drain(run)
        self.assertEqual(run['status'],'completed');self.assertEqual([s['status'] for s in run['data']['steps']][3:6],['skipped']*3)
        self.assertEqual(run['data']['steps'][2]['output']['branch'],'Sonst')

    def test_symlinks_overwrite_and_leases_fail_closed(self):
        run=self.create(['manual','read_file']);self.source.unlink();self.source.symlink_to('/etc/hosts');run=self.drain(run)
        self.assertEqual(run['status'],'error')
        with self.runs.lease(run['id']):
            with self.assertRaises(BlockingIOError):
                with self.runs.lease(run['id']):pass
        target=self.root/'existing.md';target.write_text('mine')
        with self.assertRaises(ValueError):write_file(self.root,target.name,'other')
        self.assertEqual(target.read_text(),'mine')
        link=self.root/'alias';link.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(OSError):write_file(link,'new.md','other')

    def test_contract_and_generated_targets_never_grant_access(self):
        from code_library_contract import export_template
        run=self.create();template=export_template(self.entry)
        self.assertNotIn(str(self.source),json.dumps(template));self.assertNotIn(str(self.root),template['definition']['prompt'])
        made=generated(json.dumps({'nodes':[{'kind':'manual','title':'Start','config':'/etc'},{'kind':'read_file','title':'Lesen','config':'/etc/hosts'}]}))
        self.assertEqual(made['nodes'][1]['config'],'')
        for broken in ({'version':True,'nodes':[]},{'version':2,'nodes':[node('manual'),node('manual')]},{'version':2,'nodes':[node('manual'),node('if_pdf')]}):
            with self.assertRaises(ValueError):parse(broken)


    def test_definition_edit_and_cancel_reject_pending_model_results(self):
        run=self.create(['manual','ai','notify']);self.runs.resume(run['id']);self.runs.advance(run['id'],self.job)
        request=self.runs.advance(run['id'],self.job)
        self.runs.control(run['id'],'cancel');self.runs.ai_done(run['id'],'{"text":"late"}',request['attempt'])
        self.assertEqual(self.runs.get(run['id'])['status'],'cancelled')
        self.assertFalse((self.store.directory/'block-tests').exists())
        run=self.create(['manual','ai','notify']);self.runs.resume(run['id']);self.runs.advance(run['id'],self.job)
        request=self.runs.advance(run['id'],self.job)
        plan=run['plan'];plan['nodes'][1]['config']='Anderer Auftrag'
        self.collection.update(self.entry['id'],self.entry['revision'],definition={'flow':encode(plan)})
        self.runs.ai_done(run['id'],'{"text":"old plan"}',request['attempt'])
        self.assertEqual(self.runs.get(run['id'])['status'],'error')
        with self.assertRaises(ValueError):self.runs.resume(run['id'])

if __name__=='__main__':unittest.main()
