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
            settings={'server':'https://lumen.example.test','token':'synthetic'}
            config.write_text(json.dumps(settings))
            with closing(sqlite3.connect(root/'memory.sqlite3')) as db, db:
                db.execute('CREATE TABLE memories(id TEXT PRIMARY KEY,title TEXT,body TEXT,revision INT,source TEXT)')
                db.execute('CREATE TABLE memory_owner(scope TEXT NOT NULL)')
                db.execute('INSERT INTO memory_owner VALUES (?)',(client.connection_scope(settings),))
                db.executemany('INSERT INTO memories VALUES (?,?,?,?,?)',[
                    ('one','日本語','Server preference',1,'https://lumen.example.test'),
                    ('other','Foreign','Must not leak',1,'https://other.example.test')])
            with patch.object(client,'ROOT',root),patch.object(client,'CONFIG',config):
                store=Store(root/'state');memory=Memory(store);memory.configure(True,False)
                personal=memory.remember('Local','Personal note')
                before=stamp(store)
                context=memory.prepare('Server preference',str(root))['context']
                self.assertIn('Server preference',context);self.assertNotIn('Must not leak',context)
                self.assertNotIn('Server preference',memory.prepare('unrelated-ZYX',str(root))['context'])
                self.assertEqual(len(memory.scan()['notes']),1)
                store.set_setting('memory/server_hidden',['https://lumen.example.test#one'])
                self.assertNotIn('Server preference',memory.prepare('Server preference',str(root))['context'])
                store.set_setting('memory/server_hidden',[])
                store.set_setting('memory/tombstones',{'one':dict(revision='local-forget')})
                self.assertNotIn('Server preference',memory.prepare('Server preference',str(root))['context'])
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
                client.save_private(client.CONFIG,json.dumps(config))
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

    def test_account_switch_and_late_old_response_never_expose_or_erase_new_mirror(self):
        from urllib.error import HTTPError
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            old=dict(server='https://same.example.test',device_id='old-device',token='synthetic-old')
            new=dict(old,device_id='new-device',token='synthetic-new')
            def snapshot(text,version):
                return dict(memory_version=version,capabilities=['memory'],
                            memories=[dict(id='same-id',title='A',body=text,revision=1)],tasks=[],notifications=[])
            with patch.object(client,'ROOT',root),patch.object(client,'CONFIG',root/'connection.json'),patch.object(client,'desktop_requests'),patch.object(client.shutil,'which',return_value=None):
                client.save_private(client.CONFIG,json.dumps(old))
                with patch.object(client,'request',return_value=snapshot('Old account','90:2')):
                    client.synchronize(old)
                self.assertEqual(client.shared_memories()[0]['body'],'Old account')
                client.save_private(client.CONFIG,json.dumps(new))
                self.assertEqual(client.shared_memories(),[])
                with patch.object(client,'request',return_value=snapshot('New account','1:1')):
                    client.synchronize(new)
                self.assertEqual(client.shared_memories()[0]['body'],'New account')
                with self.assertRaises(ValueError):client.synchronize(old)
                # A request already in flight when the user pairs another account.
                for rejected in (False,True):
                    client.save_private(client.CONFIG,json.dumps(old))
                    def late_response(*args):
                        client.save_private(client.CONFIG,json.dumps(new))
                        if rejected:raise HTTPError(old['server'],401,'synthetic revoked',None,None)
                        return snapshot('Late old account','91:2')
                    with patch.object(client,'request',side_effect=late_response):
                        with self.assertRaises((ValueError,HTTPError)) as error:client.synchronize(old)
                        if isinstance(error.exception,HTTPError):error.exception.close()
                    self.assertEqual(client.shared_memories()[0]['body'],'New account')
                    self.assertEqual(client.read_config(),new)
                # Legacy unbound caches require a fresh authenticated sync.
                with closing(sqlite3.connect(root/'memory.sqlite3')) as db,db:
                    db.execute('DROP TABLE memory_owner')
                self.assertEqual(client.shared_memories(),[])
                with patch.object(client,'request',return_value=snapshot('New account','2:1')):
                    client.synchronize(new)
                self.assertEqual(client.shared_memories()[0]['body'],'New account')
                raw=(root/'memory.sqlite3').read_bytes()
                self.assertNotIn(old['token'].encode(),raw);self.assertNotIn(new['token'].encode(),raw)

if __name__=='__main__':unittest.main()
