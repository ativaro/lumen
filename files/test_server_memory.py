from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from lumen_store import Store
from lumen_memory import Memory, stamp
import lumen_connect as client


class SharedMemoryTest(unittest.TestCase):
    def test_confirmed_mirror_is_context_only_and_revocation_removes_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); config=root/'connection.json'
            config.write_text(json.dumps({'server':'https://lumen.example.test'}))
            with closing(sqlite3.connect(root/'memory.sqlite3')) as db, db:
                db.execute('CREATE TABLE memories(id TEXT PRIMARY KEY,title TEXT,body TEXT,revision INT,source TEXT)')
                db.executemany('INSERT INTO memories VALUES (?,?,?,?,?)',[
                    ('one','日本語','Server preference',1,'https://lumen.example.test'),
                    ('other','Foreign','Must not leak',1,'https://other.example.test')])
            with patch.object(client,'ROOT',root),patch.object(client,'CONFIG',config):
                store=Store(root/'state');memory=Memory(store);memory.configure(True,False)
                personal=memory.remember('Local','Personal note')
                before=stamp(store)
                context=memory.prepare('Any language',str(root))['context']
                self.assertIn('Server preference',context);self.assertNotIn('Must not leak',context)
                self.assertEqual(len(memory.scan()['notes']),1)
                store.set_setting('memory/server_hidden',['https://lumen.example.test#one'])
                self.assertNotIn('Server preference',memory.prepare('x',str(root))['context'])
                config.unlink()
                self.assertNotEqual(before,stamp(store));self.assertEqual(client.shared_memories(),[])
                self.assertEqual(memory.book.read(personal['path'])['title'],'Local')


class SyncCommitTest(unittest.TestCase):
    def test_snapshot_changes_and_replays_do_not_replace_newer_memory(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            config={'server':'https://lumen.example.test','token':'synthetic'}
            def snapshot(version,text='Confirmed'):
                return dict(memory_version=version,memory_cursor=None,capabilities=["memory"],
                            memories=[dict(id='one',title='A',body=text,revision=1)],tasks=[],notifications=[])
            with patch.object(client,'ROOT',root),patch.object(client,'CONFIG',root/'connection.json'),patch.object(client.shutil,'which',return_value=None),patch.object(client,'desktop_requests'):
                with patch.object(client,'request',return_value=snapshot('10:2')):
                    client.synchronize(config)
                first=snapshot('11:2');first['memory_cursor']='next'
                with patch.object(client,'request',side_effect=[first,snapshot('12:2')]):
                    with self.assertRaises(ValueError):client.synchronize(config)
                with patch.object(client,'request',return_value=snapshot('9:2','Old')):
                    with self.assertRaises(ValueError):client.synchronize(config)
                with closing(sqlite3.connect(root/'memory.sqlite3')) as db:
                    self.assertEqual(db.execute('SELECT body FROM memories').fetchone()[0],'Confirmed')
                data=snapshot('12:2');data['notifications']=[dict(id=1,title='Ready',task_id='task')]
                def request(_,path,body=None):
                    if path=='/bridge/sync-complete':
                        with closing(sqlite3.connect(root/'memory.sqlite3')) as db:
                            self.assertEqual(db.execute('SELECT version FROM sync_state').fetchone()[0],body['version'])
                        return {'ok':True}
                    if path=='/bridge/ack':
                        with closing(sqlite3.connect(root/'memory.sqlite3')) as db:
                            self.assertEqual(db.execute('SELECT count(*) FROM notifications').fetchone()[0],1)
                        return {'ok':True}
                    return data
                with patch.object(client,'request',side_effect=request):
                    client.synchronize(config);client.synchronize(config)

if __name__=='__main__':unittest.main()
