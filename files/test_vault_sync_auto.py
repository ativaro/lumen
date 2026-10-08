"""Background transport without a window, broker, or master password."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
import vault_sync as sync


class BackgroundSyncTest(unittest.TestCase):
    def test_receipts_conflicts_account_binding_and_offline_disable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);active=root/'vault.kdbx'
            original=bytes.fromhex('03d9a29a67fb4bb501000400')+os.urandom(128)
            active.write_bytes(original);active.chmod(0o600)
            cfg=dict(server='https://test.invalid',token='synthetic')
            rows=[];contents={};posts=[];retain=[True]
            def version(blob,parent=None,identity=None):
                for row in rows:row['current']=False
                row=dict(id=identity or str(uuid4()),parent=parent,sha256=sync.digest(blob),current=True,size=len(blob))
                rows.append(row);contents[row['id']]=blob
                return row
            version(original)
            def transport(config,path,method='GET',data=None):
                if method=='POST':
                    identity,expected=path[1:].split('?expected=')
                    self.assertEqual(json.loads((root/'sync-auto.json').read_text())['pending']['id'],identity)
                    posts.append(identity)
                    if retain[0]:version(data,expected,identity)
                    raise TimeoutError('synthetic lost reply')
                return json.dumps(rows).encode() if not path else contents[path.split('/')[1]]
            def run(op,**kw):return sync.execute(dict(root=str(root),op=op,**kw))
            with patch('lumen_connect.read_config',return_value=cfg) as read,patch('lumen_connect.request',return_value=dict(name='Test',capabilities=['vault_sync'])),patch('vault_sync.transport',side_effect=transport) as network:
                self.assertFalse(run('auto-poll')['enabled']);read.assert_not_called();network.assert_not_called()
                scope=run('info')['scope'];self.assertTrue(run('auto-enable',scope=scope)['enabled'])
                self.assertEqual((root/'sync-auto.json').stat().st_mode&0o777,0o600)
                active.write_bytes(original+b'local')
                with self.assertRaises(TimeoutError):run('auto-poll')
                self.assertEqual(run('auto-poll')['reason'],'published')
                run('auto-poll');self.assertEqual(len(posts),1)
                remote=version(original+b'remote',rows[-1]['id'])
                received=run('auto-poll');self.assertTrue(received['enabled']);self.assertEqual(received['reason'],'incoming')
                self.assertEqual((root/('sync-incoming-'+remote['id']+'.kdbx')).read_bytes(),original+b'remote')
                active.write_bytes(original+b'concurrent local')
                remote2=version(original+b'remote2',remote['id'])
                self.assertEqual(run('auto-poll')['reason'],'conflict')
                self.assertTrue((root/('sync-incoming-'+remote2['id']+'.kdbx')).exists())
                self.assertEqual(active.read_bytes(),original+b'concurrent local');self.assertEqual(len(posts),1)
                with self.assertRaises(ValueError):run('auto-enable',scope=scope)
                cfg['token']='different account';network.reset_mock()
                self.assertEqual(run('auto-poll')['reason'],'connection_changed');network.assert_not_called()
                cfg['token']='synthetic';active.write_bytes(contents[remote2['id']]);run('auto-enable',scope=scope)
                active.write_bytes(original+b'unknown upload');retain[0]=False
                with self.assertRaises(TimeoutError):run('auto-poll')
                self.assertEqual(run('auto-poll')['reason'],'uncertain')
                run('auto-poll');self.assertEqual(len(posts),2)
                read.side_effect=FileNotFoundError
                self.assertFalse(run('auto-disable')['enabled']);self.assertEqual(run('auto-status')['reason'],'disabled')

    def test_private_files_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'target';target.write_text('{}');target.chmod(0o600)
            for name in ('sync-auto.json','sync-auto.lock'):
                link=root/name;link.unlink(missing_ok=True);link.symlink_to(target)
                with self.assertRaises(OSError):sync.execute(dict(root=str(root),op='auto-poll'))
                link.unlink()
            state=root/'sync-auto.json';state.write_text('{}');state.chmod(0o644)
            with self.assertRaises(ValueError):sync.execute(dict(root=str(root),op='auto-poll'))
            state.chmod(0o600);state.write_text('{"enabled":true}')
            with self.assertRaises(ValueError):sync.execute(dict(root=str(root),op='auto-poll'))
            self.assertEqual(target.read_text(),'{}')
            identity=str(uuid4());(root/('sync-incoming-'+identity+'.kdbx')).symlink_to(target)
            fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
            try:
                with self.assertRaises(OSError):sync.stage(root,fd,identity,b'encrypted')
            finally:os.close(fd)


if __name__=='__main__':unittest.main()
