import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from PySide6.QtCore import QSettings
import topbar_activity as activity


class ActivityTest(unittest.TestCase):
    def test_action_topics_and_payloads_are_not_interchangeable(self):
        with patch.object(activity,'act') as act:
            for topic,value in [('recent',dict(action='focus:start',target='',value=0)),('activity',None),('other',dict(action='open',target='',value=0)),('activity',dict(action='focus:start',target='',value=False))]:
                with self.subTest(topic=topic,value=value),self.assertRaises(ValueError): activity.act_request(topic,value)
            act.assert_not_called()
    def test_focus_counts_pauses_resumes_and_survives_a_new_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'settings.ini')
            settings=QSettings(path,QSettings.IniFormat)
            activity.focus_action('start',settings,1000)
            self.assertEqual(activity.focus(QSettings(path,QSettings.IniFormat),1030)['remaining'],1470)
            activity.focus_action('pause',settings,1040)
            self.assertEqual(activity.focus(settings,2000),dict(end=0,remaining=1460,state='paused'))
            activity.focus_action('resume',settings,2000)
            self.assertEqual(activity.focus(settings,3461)['state'],'finished')
            with self.assertRaises(ValueError): activity.focus_action('pause',settings,3461)
            activity.focus_action('stop',settings,3461)
            self.assertEqual(activity.focus(settings,3461)['state'],'off')

    def test_old_update_plan_does_not_offer_an_installed_revision(self):
        plan=dict(revision='a'*40,rows=[dict(id='lumen',pending=True,fingerprint='a'*40)])
        with patch('updater_data.installations',return_value=[Path('/installed')]),patch('updater_data.read_json',side_effect=lambda p: {'revision':'a'*40} if p.name=='install.json' else plan if p.name=='plan.json' else {}):
            self.assertFalse(activity.updates()['pending'])

    def test_recent_launch_requires_a_current_reference_and_uses_argv(self):
        with patch.object(activity,'recent',return_value=[dict(path='/tmp/$(not-a-command).txt',target='/tmp/$(not-a-command).txt',kind='file')]),patch('lumen_launch.executable',return_value='/bin/lumen-files'),patch.object(activity.subprocess,'Popen') as launch:
            activity.act('recent','/tmp/$(not-a-command).txt')
            self.assertEqual(launch.call_args.args[0],['/bin/lumen-files','/tmp/$(not-a-command).txt'])
            with self.assertRaises(ValueError): activity.act('recent','/other')
            with self.assertRaises(ValueError): activity.act('focus:unknown')

    def test_conversation_recents_keep_scope_and_reopen_without_resubmitting(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'lumen.sqlite3'
            with sqlite3.connect(path) as db:
                db.executescript('CREATE TABLE tasks(id TEXT,session TEXT,title TEXT,directory TEXT,updated REAL);CREATE TABLE events(task TEXT,kind TEXT);')
                for i,session in enumerate(('ses_local','lumen-server/current/one','lumen-server/other/two','ses_local')):
                    db.execute('INSERT INTO tasks VALUES(?,?,?,?,?)',(str(i),session,'Conversation '+str(i),tmp,100+i))
                    db.execute('INSERT INTO events VALUES(?,?)',(str(i),'input'))
            with patch('lumen_store.state_path',return_value=Path(tmp)),patch('desktop_backend.connection',return_value=({},'current')),patch('search_home.recent_documents',return_value=[]):
                rows=activity.recent();self.assertEqual(len(rows),2)
                self.assertNotIn('lumen-server/other/two',[r['session'] for r in rows])
                with patch('lumen_launch.executable',return_value='/bin/lumen-agent-app'),patch.object(activity.subprocess,'Popen') as launch:
                    activity.act('recent',rows[0]['target'])
                    self.assertEqual(launch.call_args.args[0],['/bin/lumen-agent-app','--directory',tmp,'--session','ses_local'])
                    self.assertNotIn('--prompt',launch.call_args.args[0])


if __name__=='__main__': unittest.main()
