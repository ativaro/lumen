import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from code_clock import default, starts, wall, validate
from code_flow import encode, parse
from code_library import Collection
from code_flow_native import configure
from lumen_store import Store
from test_code_flow import plan


class EditDataTest(unittest.TestCase):
    def test_clock_calendar_and_dst(self):
        from datetime import date
        now = datetime(2027, 3, 27, 12, tzinfo=timezone.utc).timestamp()
        clock = default();clock.update(kind='daily', time='02:30')
        values=starts(clock,now)
        self.assertEqual(datetime.fromtimestamp(values[0],timezone.utc).day,29)
        self.assertIsNone(wall(date(2027,3,28),'02:30'))
        overlap=wall(date(2027,10,31),'02:30')
        self.assertEqual(datetime.fromtimestamp(overlap,timezone.utc).hour,0)
        clock.update(kind='monthly',month_day=31,time='09:00')
        self.assertEqual([datetime.fromtimestamp(v,timezone.utc).month for v in starts(clock,now)],[3,5,7])
        for key,value in [('minutes',True),('days',[True]),('time','25:00'),('month_day',0)]:
            with self.assertRaises(ValueError):validate({**clock,key:value})
        clock.update(kind='once',date='2030-05-14')
        self.assertEqual(len(starts(clock,now)),1)

    def test_schedule_uses_actual_due_queue_and_pauses_changed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);collection=Collection(store);clock=default();clock.update(kind='daily',time='08:00')
            p=plan();p['trigger']='schedule';p['clock']=clock
            entry=collection.create('automation','Prüfen',value={'flow':encode(p),'directory':tmp})
            entry=configure(collection,entry,True);flow=store.workflows()[0]
            store.set_workflow_enabled(flow['id'],True)
            flow=store.workflows()[0];due=flow['next_run'];tasks=store.enqueue_due(now=due+1)
            self.assertEqual(len(tasks),1)
            self.assertGreater(store.workflows()[0]['next_run'],due+3600)
            other=Path(tmp)/'other';other.mkdir()
            collection.update(entry['id'],entry['revision'],definition={**entry['definition'],'directory':str(other)})
            self.assertFalse(store.workflows()[0]['approved']);self.assertFalse(store.workflows()[0]['enabled'])

    def test_frozen_tool_adoption_is_atomic_and_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);c=Collection(store)
            tool=c.create('tool','Prüfen',value={'prompt':'Original'})
            p=plan();p['steps']=[dict(title=tool['title'],prompt='Original',tool_id=tool['id'],tool_revision=1)]
            first=configure(c,c.create('automation','Erste',value={'flow':encode(p)}),True)
            second=configure(c,c.create('automation','Zweite',value={'flow':encode(p)}),True)
            c.store.set_workflow_enabled(first['definition']['workflow_id'],True)
            updated=c.update(tool['id'],1,definition={'prompt':'Neu'})
            self.assertEqual(parse(c.get(first['id'])['definition']['flow'])['steps'][0]['prompt'],'Original')
            with self.assertRaises(ValueError):
                c.update(tool['id'],updated['revision'],definition={'prompt':'Noch neuer'},adopt=[(first['id'],first['revision']-1)])
            self.assertEqual(c.get(tool['id'])['definition']['prompt'],'Neu')
            c.update(tool['id'],updated['revision'],definition={'prompt':'Noch neuer'},adopt=[(first['id'],first['revision'])])
            adopted=parse(c.get(first['id'])['definition']['flow'])['steps'][0]
            self.assertEqual(adopted['prompt'],'Noch neuer');self.assertEqual(adopted['tool_revision'],3)
            self.assertEqual(parse(c.get(second['id'])['definition']['flow'])['steps'][0]['prompt'],'Original')
            flow=next(f for f in store.workflows() if f['id']==first['definition']['workflow_id'])
            self.assertFalse(flow['enabled']);self.assertFalse(flow['approved'])

    def test_once_notes_delivery_retry_and_target_guard(self):
        from code_flow_native import deliver
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);c=Collection(store);notes=Path(tmp)/'notes';notes.mkdir();store.set_setting('knowledge/notebook',str(notes))
            clock=default();clock.update(kind='once',date='2030-05-14',time='09:00')
            p=plan();p.update(trigger='schedule',clock=clock,outputs=['note'],note_root=str(notes))
            entry=configure(c,c.create('automation','Beleg',value={'flow':encode(p),'directory':tmp}),True)
            workflow=store.workflows()[0];store.set_workflow_enabled(workflow['id'],True)
            task=store.enqueue_due(now=store.workflows()[0]['next_run']+1)[0]
            self.assertEqual(store.enqueue_due(now=store.workflows()[0]['next_run']-10),[])
            store.update_task(task,status='running')
            # Output cannot silently follow a changed Notes destination.
            other=Path(tmp)/'other-notes';other.mkdir();store.set_setting('knowledge/notebook',str(other))
            store.update_task(task,status='completed',result='CHF 42, Frist fehlt')
            self.assertFalse(list(notes.glob('*.md')));self.assertFalse(list(other.glob('*.md')))
            self.assertFalse(store.workflows()[0]['enabled'])
            store.set_setting('knowledge/notebook',str(notes));deliver(store);deliver(store)
            self.assertEqual(len(list(notes.glob('*.md'))),1)
            self.assertEqual(len(store.rows("SELECT * FROM events WHERE task=? AND kind='code-flow-note-saved'",(task,))),1)

    def test_stale_configuration_cannot_reapprove_a_changed_routine(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);c=Collection(store);entry=configure(c,c.create('automation','Alt',value={'flow':encode(plan())}),True)
            updated=c.update(entry['id'],entry['revision'],title='Neu')
            before=store.workflows()[0]
            with self.assertRaisesRegex(ValueError,'inzwischen'):configure(c,entry,True)
            self.assertEqual(store.workflows()[0],before)
            self.assertEqual(c.get(updated['id'])['title'],'Neu')

    def test_untrusted_refs_and_specs(self):
        from code_library_contract import definition
        p=plan()
        p['steps'][0].update(tool_id=123,tool_revision=1)
        with self.assertRaises(ValueError):encode(p)
        for spec in [dict(input='Shell',output='Prüfbericht mit Fundstellen',rules=['x']),dict(input='Text',output='Kurze Zusammenfassung',rules=[''])]:
            with self.assertRaises(ValueError):definition('tool','x',value={'tool_spec':json.dumps(spec)})

    def test_delayed_interval_keeps_activation_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);c=Collection(store);p=plan();p['clock']={**default(),'kind':'interval','minutes':15}
            entry=configure(c,c.create('automation','Intervall',value={'flow':encode(p)}),True)
            flow=store.workflows()[0];store.set_workflow_enabled(flow['id'],True)
            original=store.workflows()[0]['next_run'];store.enqueue_due(now=original+25)
            self.assertEqual(store.workflows()[0]['next_run'],original+900)


if __name__=='__main__':unittest.main()
