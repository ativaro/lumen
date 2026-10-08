from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
import lumen_connect as client


class ArtifactTest(unittest.TestCase):
    def test_scoped_copy_hash_and_replay(self):
        content=b'Synthetic result'
        action=dict(id=str(uuid4()),file_id=str(uuid4()),revision=1,mime='text/plain',size=len(content),sha256=hashlib.sha256(content).hexdigest())
        config=dict(server='https://lumen.example.test',token='synthetic')
        with tempfile.TemporaryDirectory() as directory,patch.object(client,'tls_context'):
            with patch.object(client,'ROOT',Path(directory)),patch.object(client.urllib.request,'build_opener') as opener:
                opener.return_value.open.side_effect=lambda *a,**k:io.BytesIO(content)
                with patch.object(client,'request',side_effect=[dict(revision=2),dict(state='claimed',revision=2)]):
                    result=client.receive_artifact(config,action)
                self.assertEqual(Path(result['path']).read_bytes(),content)
                self.assertEqual(Path(result['path']).stat().st_mode&0o777,0o600)
                with patch.object(client,'request',return_value=dict(revision=2,replayed=True)):
                    with self.assertRaises(ValueError):client.receive_artifact(config,action)
                with patch.object(client,'request',return_value=dict(revision=2)):
                    with self.assertRaises(ValueError):client.receive_artifact(config,dict(action,sha256='0'*64))
                self.assertEqual(len(list((Path(directory)/'received').iterdir())),1)

    def test_duplicate_delivery_launches_one_native_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            identity=str(uuid4());root=Path(directory)
            with patch.object(client,'ROOT',root),patch.object(client,'request',return_value=[{'id':identity}]),patch.object(client.subprocess,'Popen') as launch:
                client.desktop_requests({});client.desktop_requests({})
                self.assertEqual(launch.call_count,1)
                self.assertEqual(launch.call_args.args[0][-2:],['--artifact',identity])
                with closing(sqlite3.connect(root/'memory.sqlite3')) as db:
                    self.assertEqual(db.execute('SELECT id FROM desktop_requests').fetchone()[0],identity)

if __name__=='__main__':unittest.main()
