import copy
import json
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

if __name__=='__main__':unittest.main()
