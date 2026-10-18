import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from code_blocks import node,encode
from code_blocks_run import Runs
from code_library import Collection
from code_triggers import Triggers,validate,file_event
from lumen_store import Store

class Job:
    def check(self):pass

class TriggerTest(unittest.TestCase):
    def make(self,tmp,source,actions=None):
        c=Collection(Store(Path(tmp)/'state'))
        plan={'version':3,'nodes':[node('manual',json.dumps(source)),*(actions or [node('filter_text','a')])]}
        e=c.create('automation','Test',value={'flow':encode(plan)})
        return c,e,Triggers(c)

    def finish(self,c,identity):
        r=Runs(c)
        with r.lease(identity):
            r.resume(identity)
            while r.get(identity)['status']=='running':r.advance(identity,Job())
        return r.get(identity)

    def test_directory_baseline_stability_dedup_and_real_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);(path/'old.txt').write_text('old');out=path/'out';out.mkdir()
            c,e,t=self.make(tmp,{'kind':'file','trigger':{'kind':'directory','path':tmp}},[node('filter_text','alpha'),node('save_file',str(out))])
            t.activate(e['id'],0);self.assertEqual(t.poll(1),[])
            new=path/'new.txt';new.write_text('alpha\nbeta')
            self.assertEqual(t.poll(2),[]);ids=t.poll(3);self.assertEqual(len(ids),1)
            self.assertEqual(t.poll(4),[])
            done=self.finish(c,ids[0]);self.assertEqual(done['status'],'completed')
            self.assertEqual(Path(done['data']['steps'][-1]['output']['effect']['path']).read_text(),'alpha')
            self.assertEqual(done['data']['steps'][0]['output']['filename'],'new.txt')
            self.assertEqual(t.poll(5),[])

    def test_replaced_or_changed_source_cannot_be_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            source={'kind':'file','trigger':{'kind':'directory','path':tmp}}
            path=Path(tmp)/'a.txt';path.write_text('alpha');event=file_event(source,path)
            c,e,t=self.make(tmp,source);run=Runs(c).create(e['id'],event=event)
            path.write_text('changed')
            done=self.finish(c,run['id']);self.assertEqual(done['status'],'error')
            with self.assertRaises(ValueError):file_event(source,Path(tmp)/'nested'/'a.txt')
            (Path(tmp)/'link.txt').symlink_to(path)
            with self.assertRaises(ValueError):file_event(source,Path(tmp)/'link.txt')

    def test_calendar_once_and_pause_fence(self):
        from code_clock import default
        with tempfile.TemporaryDirectory() as tmp:
            clock={**default(),'kind':'interval','minutes':15}
            c,e,t=self.make(tmp,{'kind':'text','text':'alpha','trigger':{'kind':'clock','clock':clock}})
            t.activate(e['id'],100);self.assertEqual(t.poll(999),[])
            ids=t.poll(1000);self.assertEqual(len(ids),1);self.assertEqual(t.poll(1000),[])
            t.pause(e['id'])
            with self.assertRaisesRegex(ValueError,'pausiert'):self.finish(c,ids[0])

    def test_project_change_reads_current_projects_and_ignores_other_projects(self):
        from tools_data import Library
        from projects_data import Projects
        with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{'LUMEN_TOOLS_DATA':tmp+'/tools'}):
            lib=Library('workbench');a=lib.create('A',notes='alpha');b=lib.create('B',notes='beta')
            c,e,t=self.make(tmp,{'kind':'project','project_id':'workbench:'+a,'trigger':{'kind':'project'}})
            t.activate(e['id']);lib.update(b,notes='other');self.assertEqual(t.poll(),[])
            p=Projects(lib);p.add(a,'','Vorhaben','initiative',notes='Neuer Plan')
            ids=t.poll();self.assertEqual(len(ids),1)
            done=self.finish(c,ids[0]);self.assertIn('Neuer Plan',done['data']['steps'][0]['output']['text'])
            self.assertEqual(t.poll(),[])

    def test_saved_changes_and_archiving_disable_old_authorization(self):
        from code_clock import default
        with tempfile.TemporaryDirectory() as tmp:
            c,e,t=self.make(tmp,{'kind':'text','text':'alpha','trigger':{'kind':'clock','clock':{**default(),'kind':'daily'}}})
            t.activate(e['id']);plan=json.loads(e['definition']['flow']);plan['nodes'][-1]['config']='beta'
            c.update(e['id'],e['revision'],definition={'flow':encode(plan)})
            self.assertEqual(t.poll(1e10),[]);self.assertFalse(t.get(e['id'])['enabled'])

    def test_reject_unknown_and_mismatched_trigger(self):
        for value,kind in [({'kind':'mail'},'text'),({'kind':'project'},'file'),({'kind':'directory','path':'relative'},'file')]:
            with self.assertRaises(ValueError):validate(value,kind)

    def test_background_timer_executes_real_file_actions_without_window(self):
        from code_clock import default
        from lumen_tasks import tick
        with tempfile.TemporaryDirectory() as tmp:
            c,e,t=self.make(tmp,{'kind':'text','text':'alpha\nbeta','trigger':{'kind':'clock','clock':{**default(),'kind':'interval','minutes':15}}},[node('filter_text','alpha'),node('save_file',tmp)])
            t.activate(e['id'],0)
            with patch('lumen_tasks.defer_background',return_value=''),patch('code_triggers.time.time',return_value=1000):tick(c.store)
            done=Runs(c).latest(e['id']);self.assertEqual(done['status'],'completed')
            self.assertEqual(next(Path(tmp).glob('Lumen-*.md')).read_text(),'alpha')
            with patch('lumen_tasks.defer_background',return_value=''),patch('code_triggers.time.time',return_value=1000):tick(c.store)
            self.assertEqual(len(list(Path(tmp).glob('Lumen-*.md'))),1)

    def test_background_ai_is_tools_free_and_checkpointed(self):
        from code_clock import default
        from code_blocks_worker import run_pending
        from PySide6.QtCore import QObject,Signal,QTimer
        class Backend(QObject):
            completed=Signal(bool,str)
            def __init__(self,*a,**kw):super().__init__();self.sent=None
            def send(self,prompt,**kw):
                self.sent=(prompt,kw);self.assert_proposal=kw['proposal'];QTimer.singleShot(0,lambda:self.completed.emit(True,json.dumps({'text':'alpha Ergebnis'})))
            def stop(self):pass
            def shutdown(self):pass
        with tempfile.TemporaryDirectory() as tmp:
            c,e,t=self.make(tmp,{'kind':'text','text':'alpha','trigger':{'kind':'clock','clock':{**default(),'kind':'interval','minutes':15}}},[node('ai','Fasse zusammen'),node('save_file',tmp)])
            t.activate(e['id'],0)
            with patch('assistant_backend.OpenCodeBackend',Backend),patch('code_triggers.time.time',return_value=1000):run_pending(c)
            done=Runs(c).latest(e['id']);self.assertEqual(done['status'],'completed');self.assertEqual(next(Path(tmp).glob('Lumen-*.md')).read_text(),'alpha Ergebnis')

    def test_background_waits_for_confirmation_and_pause_is_not_auto_resumed(self):
        from code_clock import default
        from code_blocks_worker import run_pending
        with tempfile.TemporaryDirectory() as tmp:
            c,e,t=self.make(tmp,{'kind':'text','text':'alpha','trigger':{'kind':'clock','clock':{**default(),'kind':'interval','minutes':15}}},[node('approval'),node('save_file',tmp)])
            t.activate(e['id'],0)
            with patch('code_triggers.time.time',return_value=1000):run_pending(c)
            run=Runs(c).latest(e['id']);self.assertEqual(run['status'],'waiting');self.assertFalse(list(Path(tmp).glob('Lumen-*.md')))
            with patch('code_triggers.time.time',return_value=2000):run_pending(c)
            self.assertEqual(Runs(c).latest(e['id'])['id'],run['id'])

if __name__=='__main__':unittest.main()
