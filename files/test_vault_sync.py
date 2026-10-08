import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
import vault_sync as sync


class VaultSyncTransportTest(unittest.TestCase):
    def test_explicit_scope_ciphertext_staging_conflict_and_changed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'vault';root.mkdir(mode=0o700)
            blob=bytes.fromhex('03d9a29a67fb4bb501000400')+os.urandom(128)
            active=root/'vault.kdbx';active.write_bytes(blob);active.chmod(0o600)
            cfg=dict(server='https://test.invalid',token='synthetic');identity=str(uuid4())
            row=dict(id=identity,sha256=hashlib.sha256(blob).hexdigest(),current=True,size=len(blob))
            def transport(config,path,method='GET',data=None):
                self.assertEqual(config,cfg)
                if method=='POST':
                    self.assertEqual(data,blob);return json.dumps(dict(applied=False,head=row,version=row)).encode()
                return json.dumps([row]).encode() if not path else blob
            with patch('lumen_connect.read_config',return_value=cfg),patch('lumen_connect.request',return_value=dict(name='Test',capabilities=['vault_sync'])),patch('vault_sync.transport',side_effect=transport):
                request=dict(root=str(root));info=sync.execute(dict(request,op='info'))
                request['scope']=info['scope']
                self.assertFalse(sync.execute(dict(request,op='upload',id=str(uuid4()),expected=identity,local_hash=info['local_hash']))['applied'])
                received=sync.execute(dict(request,op='download',id=identity,sha256=row['sha256']))
                self.assertEqual(Path(received['path']).read_bytes(),blob)
                self.assertEqual(Path(received['path']).stat().st_mode&0o777,0o600)
                self.assertEqual(sync.execute(dict(request,op='download',id=identity,sha256=row['sha256'])),received)
                with self.assertRaises(ValueError):sync.execute(dict(request,op='download',id=identity,sha256='bad'))
                active.write_bytes(blob+b'new')
                with self.assertRaises(ValueError):sync.execute(dict(request,op='upload',id=str(uuid4()),local_hash=info['local_hash']))
                cfg['token']='another-device'
                with self.assertRaises(ValueError):sync.execute(dict(request,op='download',id=identity,sha256=row['sha256']))
                self.assertEqual(active.read_bytes(),blob+b'new')

    def test_symlinks_permissions_and_plaintext_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);file=root/'vault.kdbx';file.write_text('Not encrypted');file.chmod(0o600)
            with self.assertRaises(ValueError):sync.snapshot(root)
            file.unlink();file.symlink_to('/etc/hostname')
            with self.assertRaises(OSError):sync.snapshot(root)


if __name__=='__main__':unittest.main()
