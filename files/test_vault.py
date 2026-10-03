import json
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools_data import Library
from tools_ui import Job
import vault_data as vault


class VaultTest(unittest.TestCase):
    def test_schedule_is_opt_in_and_last_disabled_plan_stops_timer(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'XDG_CONFIG_HOME':tmp}):
            library=Library('vault',Path(tmp)/'data');key=library.create('Test',interval=0)
            calls=[]
            class Runner:
                def command(self,args,**kwargs):calls.append(args)
            vault.schedule(library,key,0,Runner());self.assertFalse(any('enable' in c for c in calls))
            vault.schedule(library,key,86400,Runner());self.assertTrue(any('enable' in c for c in calls));self.assertEqual(library.get(key)['interval'],86400)
            vault.schedule(library,key,0,Runner());self.assertIn('disable',calls[-1]);self.assertEqual(library.get(key)['interval'],0)
            self.assertIn('--tick',(Path(tmp)/'systemd/user/lumen-vault.service').read_text())
            self.assertIn('ExecStart="'+sys.executable+'" ',(Path(tmp)/'systemd/user/lumen-vault.service').read_text())

    def test_rejects_nested_and_missing_targets_and_invalid_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);repo=root/'backup';repo.mkdir()
            with self.assertRaises(ValueError):vault.paths(repo,[root])
            with self.assertRaises(ValueError):vault.paths(root/'missing',[repo])
            with self.assertRaises(ValueError):vault.paths(repo,[])

    def test_real_encrypted_backup_preview_restore_and_wrong_repository(self):
        program=os.environ.get('LUMEN_TEST_RESTIC') or vault.binary()
        if not program:self.skipTest('Restic optional; LUMEN_TEST_RESTIC auf den installierten Testpfad setzen')
        passwords={}
        def keyring(_ns,key,value=None):
            if value is not None:passwords[key]=value
            return passwords[key]
        with tempfile.TemporaryDirectory() as tmp, patch('vault_data.secret',side_effect=keyring),patch('vault_data.binary',return_value=program):
            root=Path(tmp);repo=root/'backup';repo.mkdir();source=root/'source';source.mkdir();restore=root/'restored';restore.mkdir()
            (source/'example.txt').write_text('Version eins');library=Library('vault',root/'data');job=Job(lambda _:None)
            key=vault.create(library,'Test',str(repo),[str(source)],'test-secret-123456789',job)
            self.assertNotIn(b'test-secret',library.db.read_bytes())
            preview=vault.run(library,key,'preview',job);self.assertTrue(preview['dry_run'])
            first=vault.run(library,key,'backup',job);self.assertTrue(first['snapshot_id'])
            self.assertGreater(library.get(key)['last_backup'],0)
            (source/'example.txt').write_text('Version zwei')
            snapshots=vault.run(library,key,'snapshots',job);self.assertEqual(len(snapshots),1)
            snap=snapshots[0]['id'];files=vault.run(library,key,'files',job,snapshot=snap)
            chosen=next(f['path'] for f in files if f['path'].endswith('example.txt'))
            target=Path(vault.run(library,key,'restore',job,snapshot=snap,selected=chosen,destination=str(restore)))
            self.assertEqual(next(target.rglob('example.txt')).read_text(),'Version eins')
            self.assertEqual((source/'example.txt').read_text(),'Version zwei')
            self.assertIn('vollständig',vault.run(library,key,'check',job,full=True))
            original_id=library.get(key)['repository_id'];library.update(key,repository_id='wrong')
            with self.assertRaises(ValueError):vault.run(library,key,'backup',job)
            library.update(key,repository_id=original_id)
            passwords[key]='wrong-password'
            with self.assertRaises(ValueError):vault.run(library,key,'snapshots',job)
            job.cancelled.set()
            with self.assertRaises(Exception):vault.run(library,key,'snapshots',job)


if __name__=='__main__':unittest.main()
