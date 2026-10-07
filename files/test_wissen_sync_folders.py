import tempfile
import unittest
from pathlib import Path
from lumen_store import Store
from wissen_data import Notebook
from wissen_sync_folders import synchronize


class FolderSyncTest(unittest.TestCase):
    def test_empty_folders_two_clients_delete_rename_and_interrupted_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            books=[Notebook(Store(Path(tmp)/f's{i}'),Path(tmp)/f'n{i}',create=True) for i in range(2)]
            state=[{},{}];remote=set()
            def request(path,body=None):
                if body is None:return {'names':sorted(remote)}
                if sorted(remote) not in (body['before'],body['after']):return {'applied':False,'names':sorted(remote)}
                remote.clear();remote.update(body['after']);return {'applied':True,'names':sorted(remote)}
            def sync(i):return synchronize(books[i],request,'test',state[i])
            books[0].create_collection('Empty');sync(0);sync(1)
            self.assertTrue((books[1].root/'Empty').is_dir())
            remote.add('Web');sync(0);sync(1)
            (books[0].root/'Empty').rename(books[0].root/'Renamed')
            sync(0);sync(1)
            self.assertFalse((books[1].root/'Empty').exists())
            self.assertTrue((books[1].root/'Renamed').is_dir())
            (books[1].root/'Web'/'keep.txt').write_text('do not remove')
            remote.remove('Web');sync(0)
            self.assertEqual(sync(1),['Web'])
            self.assertEqual((books[1].root/'Web'/'keep.txt').read_text(),'do not remove')
            remote.add('AfterRestart')
            state[0]['folder_pending']={'names':['Renamed','AfterRestart'],'remove':[]}
            sync(0)
            self.assertTrue((books[0].root/'AfterRestart').is_dir())
            self.assertNotIn('folder_pending',state[0])
