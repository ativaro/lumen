import copy
import json
from pathlib import Path
import tempfile
import unittest
from code_blocks import node,parse,encode
from code_block_paths import flatten,tree
from code_blocks_run import Runs
from code_library import Collection
from lumen_store import Store

class Job:
    def check(self):pass

class BranchRuns(unittest.TestCase):
    def plan(self):
        start=node('manual',json.dumps({'kind':'message','text':'Hallo','subject':'Rechnung','has_attachment':True}))
        wait=node('approval');notify=node('notify')
        branch=node('choose');branch.update(cases=[{'when':{'all':[{'field':'subject','op':'contains','value':'Rechnung'},{'field':'has_attachment','op':'equals','value':True}]},'steps':[wait]}],otherwise=[notify])
        return flatten([start,branch,node('notify')])

    def test_branch_checkpoint_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            collection=Collection(Store(tmp));plan=self.plan();entry=collection.create('automation','Test',value={'flow':encode(plan)})
            runs=Runs(collection);run=runs.create(entry['id']);runs.resume(run['id'])
            for _ in range(3):runs.advance(run['id'],Job())
            self.assertEqual(runs.get(run['id'])['status'],'waiting')
            runs.control(run['id'],'approve');runs.resume(run['id']);runs.advance(run['id'],Job())
            done=runs.get(run['id']);self.assertEqual(done['status'],'completed')
            self.assertEqual([s['status'] for s in done['data']['steps']],['completed','completed','completed','skipped','completed'])
            self.assertEqual(done['data']['steps'][0]['attempts'],1)

    def test_fallback_and_nested_paths(self):
        p=self.plan();t=tree(p);t[0]['config']=json.dumps({'kind':'text','text':'Hallo'})
        # The source no longer exposes message fields, so the old condition cannot silently survive.
        with self.assertRaises(ValueError):parse(flatten(t))
        t[1]['cases'][0]['when']={'field':'text','op':'contains','value':'Rechnung'}
        with tempfile.TemporaryDirectory() as tmp:
            c=Collection(Store(tmp));r=Runs(c);e=c.create('automation','Fallback',value={'flow':encode(flatten(t))});run=r.create(e['id']);r.resume(run['id'])
            for _ in range(5):r.advance(run['id'],Job())
            self.assertEqual(r.get(run['id'])['status'],'completed')
            self.assertEqual(r.get(run['id'])['data']['steps'][2]['status'],'skipped')

    def test_invalid_membership_and_future_fields(self):
        p=self.plan();p['nodes'][1]['config']=json.dumps({'cases':[{'when':{'field':'matched','op':'equals','value':True},'nodes':[]}],'otherwise':[]})
        with self.assertRaises(ValueError):parse(p)
        p=self.plan();config=json.loads(p['nodes'][1]['config']);config['otherwise']=config['cases'][0]['nodes'];p['nodes'][1]['config']=json.dumps(config)
        with self.assertRaises(ValueError):parse(p)



class LoopRuns(unittest.TestCase):
    def test_each_line_uses_distinct_replay_safe_effects_and_reopens(self):
        from code_block_paths import flatten
        start=node('manual',json.dumps({'kind':'text','text':'erste Zeile\nzweite Zeile'}))
        repeat=node('for_each');repeat.update(steps=[node('approval'),node('notify')],end=node('end_each','',title='Ende'))
        repeat['end']['config']=repeat['id']
        with tempfile.TemporaryDirectory() as tmp:
            c=Collection(Store(tmp));runs=Runs(c);entry=c.create('automation','Zeilen',value={'flow':encode(flatten([start,repeat,node('notify')]))})
            run=runs.create(entry['id']);runs.resume(run['id'])
            for _ in range(3):runs.advance(run['id'],Job())
            self.assertEqual(runs.get(run['id'])['status'],'waiting')
            runs.control(run['id'],'approve');runs.resume(run['id'])
            for _ in range(3):runs.advance(run['id'],Job())
            self.assertEqual(runs.get(run['id'])['status'],'waiting')
            self.assertEqual(len(list((Path(tmp)/'block-tests'/run['id']).glob('*.json'))),1)
            runs=Runs(c);runs.control(run['id'],'approve');runs.resume(run['id'])
            for _ in range(4):runs.advance(run['id'],Job())
            final=runs.get(run['id']);self.assertEqual(final['status'],'completed')
            self.assertEqual(final['data']['steps'][-1]['output']['text'],'erste Zeile\nzweite Zeile')
            files=list((Path(tmp)/'block-tests'/run['id']).glob('*.json'));self.assertEqual(len(files),3)
            self.assertEqual(len(final['data']['loops'][repeat['id']]['history']),2)

class AdditionalActions(unittest.TestCase):
    def test_project_append_is_atomic_and_test_run_does_not_write(self):
        from file_spaces import Catalog
        with tempfile.TemporaryDirectory() as tmp:
            c=Collection(Store(tmp));Catalog(c.store).put('room',{'id':'project-a','project':True,'name':'A','note':'Vorhanden','sources':[],'applications':[],'urls':[]})
            start=node('manual',json.dumps({'kind':'text','text':'Neues Ergebnis'}));plan={'version':3,'nodes':[start,node('project_note','project-a')]};entry=c.create('automation','Projekt',value={'flow':encode(plan)});runs=Runs(c)
            run=runs.create(entry['id'],True);runs.resume(run['id']);runs.advance(run['id'],Job());runs.advance(run['id'],Job())
            self.assertEqual(Catalog(c.store).rooms()[0]['note'],'Vorhanden')
            run=runs.create(entry['id'],False);runs.resume(run['id']);runs.advance(run['id'],Job());runs.advance(run['id'],Job())
            self.assertEqual(runs.get(run['id'])['status'],'completed');self.assertIn('Neues Ergebnis',Catalog(c.store).rooms()[0]['note'])

    def test_wait_keeps_original_deadline_after_retry(self):
        from unittest.mock import patch
        class CancelledJob:
            def check(self):raise ValueError('Unterbrochen')
        with tempfile.TemporaryDirectory() as tmp:
            c=Collection(Store(tmp));p={'version':3,'nodes':[node('manual',json.dumps({'kind':'text','text':'abc'})),node('delay','5'),node('filter_text','a')]};entry=c.create('automation','Warten',value={'flow':encode(p)});r=Runs(c);run=r.create(entry['id']);r.resume(run['id']);r.advance(run['id'],Job());r.advance(run['id'],CancelledJob())
            failed=r.get(run['id']);self.assertEqual(failed['status'],'error');deadline=failed['data']['steps'][1]['until']
            r.resume(run['id'])
            with patch('code_blocks_run.time.time',return_value=deadline+1):r.advance(run['id'],Job())
            r.advance(run['id'],Job());self.assertEqual(r.get(run['id'])['status'],'completed');self.assertEqual(r.get(run['id'])['data']['steps'][1]['until'],deadline)

if __name__=='__main__':unittest.main()
