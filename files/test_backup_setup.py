"""Synthetic data only: real encrypted backup/recovery and offline safety."""
import os
from pathlib import Path
import sys
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import backup_setup as setup
import backup_network
from lumen_jobs import Job
from tools_data import Library
import vault_data as vault


def broker(root, commands):
    binary = Path(__file__).resolve().parent.parent/'native/vault-core/target/release/lumen-vault-lab-broker'
    if not binary.is_file(): raise unittest.SkipTest('Build the native vault broker first')
    frames = bytearray()
    for command in [*commands, ['shutdown']]:
        payload = struct.pack('>I',len(command))
        for field in command:
            encoded=field.encode();payload+=struct.pack('>I',len(encoded))+encoded
        frames+=struct.pack('>I',len(payload))+payload
    result=subprocess.run([str(binary),'--laboratory-only',str(root)],input=frames,capture_output=True,timeout=45)
    assert result.returncode == 0, 'Synthetic broker failed'
    remaining=result.stdout; replies=[]
    while remaining:
        size=struct.unpack('>I',remaining[:4])[0]; frame=remaining[4:4+size];remaining=remaining[4+size:]
        count=struct.unpack('>I',frame[:4])[0];frame=frame[4:];fields=[]
        for _ in range(count):
            size=struct.unpack('>I',frame[:4])[0];fields.append(frame[4:4+size].decode());frame=frame[4+size:]
        assert fields[0] == 'ok', 'Synthetic broker command failed'
        replies.append(fields[1:])
    return replies


class BackupSetupTest(unittest.TestCase):
    def test_native_copy_rejects_links_fifo_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'vault';source.mkdir(mode=0o700)
            database=source/'vault.kdbx'; payload=bytes.fromhex('03d9a29a67fb4bb5')+b'encrypted-fixture'
            database.write_bytes(payload);database.chmod(0o600)
            (source/'unlock-key').write_text('must never be copied')
            job=Job(lambda _:None)
            setup.encrypted_copy(source,root/'copy',job)
            self.assertEqual([p.name for p in (root/'copy').iterdir()],['vault.kdbx'])
            self.assertEqual((root/'copy/vault.kdbx').read_bytes(),payload)
            database.chmod(0o644)
            with self.assertRaises(ValueError):setup.encrypted_copy(source,root/'bad-mode',job)
            database.unlink();database.symlink_to(root/'copy/vault.kdbx')
            with self.assertRaises(OSError):setup.encrypted_copy(source,root/'bad-link',job)
            database.unlink();os.mkfifo(database,0o600)
            with self.assertRaises(ValueError):setup.encrypted_copy(source,root/'bad-fifo',job)

    def test_stdin_is_memory_backed_and_network_credentials_are_scoped(self):
        self.assertEqual(backup_network.address('smb://'), 'smb:///')
        job=Job(lambda _:None)
        output=job.command([sys.executable,'-c',"import os,sys; print(os.readlink('/proc/self/fd/0')); assert sys.stdin.read() == 'synthetic-token'"],data=b'synthetic-token')
        self.assertIn(b'memfd:lumen-job-input',output)
        for uri in ('smb://user:password@nas/share','smb://nas/share?token=secret','smb://nas/share\n'):
            with self.assertRaises(ValueError):backup_network.address(uri)
        with patch('tools_secrets.secret',return_value='{"uri":"smb://first/share","username":"u","password":"p","domain":""}'), patch('backup_network.call') as call:
            with self.assertRaises(ValueError): setup.network({'action':'resolve','uri':'smb://second/share','network_id':'a'*32},job)
            call.assert_not_called()
        with patch('backup_network.call',return_value={'error':'auth_required'}),patch('tools_secrets.secret') as secret:
            with self.assertRaises(ValueError):setup.network({'action':'test','uri':'smb://nas/share','password':'synthetic','remember':True},job)
            secret.assert_not_called()

    def test_failed_setup_never_schedules_and_retries_same_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            library=Library('vault',Path(tmp));identity=library.create('Pending',setup_pending=True,intended_interval=86400,interval=0)
            with self.assertRaises(ValueError): vault.schedule(library,identity,86400,None)
            with patch('vault_data.run',side_effect=ValueError('offline')),patch('vault_data.schedule') as schedule:
                with self.assertRaises(ValueError):setup.finish_setup(library,identity,None)
                schedule.assert_not_called();self.assertTrue(library.get(identity)['setup_pending'])
            with patch('vault_data.run',return_value={'snapshot_id':'b'*64}),patch('vault_data.schedule') as schedule:
                self.assertTrue(setup.finish_setup(library,identity,None)['verified'])
                schedule.assert_called_once_with(library,identity,86400,None)
                self.assertFalse(library.get(identity)['setup_pending'])
                with self.assertRaises(ValueError):setup.finish_setup(library,identity,None)
                self.assertFalse(library.get(identity)['setup_pending'])

    def test_real_first_backup_restore_adopt_and_missing_network(self):
        program=os.environ.get('LUMEN_TEST_RESTIC') or vault.binary()
        if not program:self.skipTest('Restic required')
        passwords={}
        def keyring(_namespace,identity,value=None):
            if value is not None: passwords[identity]=value
            return passwords[identity]
        with tempfile.TemporaryDirectory() as tmp,patch('vault_data.secret',side_effect=keyring),patch('vault_data.binary',return_value=program):
            root=Path(tmp);target=root/'target';target.mkdir();source=root/'source';source.mkdir()
            (source/'example.txt').write_text('Original content')
            library=Library('vault',root/'tools');job=Job(lambda _:None)
            native=root/'native';native.mkdir(mode=0o700)
            entry=broker(native,[['create','SYNTHETIC MASTER LONG'],['put','','Title','Fixture','Password','SYNTHETIC TOKEN']])[1][0]
            app_source=dict(app='vault',path=str(native),slot='native-vault',kind='native-vault',title='Encrypted vault')
            inventory={'files':[], 'lumen':[], 'vault':[dict(path=str(native))]}
            request=dict(title='Synthetic',repository=str(target),groups={'files':[str(source)],'vault':[str(native)]},password='independent-test-key',recovery_confirmed=True,interval=0)
            with patch.object(setup,'inventory',return_value=inventory),patch('interop_vault.discover_sources',return_value=[app_source]):
                invalid=dict(request,remote_sources=[{'path':'wrong','uri':'smb://nas/share'}])
                with self.assertRaises(ValueError):setup.configure(library,invalid,job)
                self.assertEqual(list(target.iterdir()),[])
                identity=setup.configure(library,request,job)['id']
                self.assertEqual(library.get(identity)['interval'],0)
                with patch('vault_data.schedule') as schedule:
                    result=setup.finish_setup(library,identity,job)
                    self.assertTrue(result['verified']);schedule.assert_called_once()
            plan=library.get(identity);self.assertGreater(plan['last_restore_probe'],0)
            self.assertEqual(plan['backup_groups'],request['groups'])
            self.assertNotIn(b'independent-test-key',library.db.read_bytes())
            restore=root/'restore';restore.mkdir()
            snapshot=vault.run(library,identity,'snapshots',job)[0]['id']
            (source/'example.txt').write_text('New content')
            restored=Path(vault.run(library,identity,'restore',job,snapshot=snapshot,destination=str(restore)))
            self.assertEqual(next(restored.rglob('example.txt')).read_text(),'Original content')
            restored_native=next(restored.rglob('native-vault'))
            reopened=broker(restored_native,[['open','SYNTHETIC MASTER LONG'],['get',entry,'Password']])
            self.assertEqual(reopened[1],['SYNTHETIC TOKEN'])
            self.assertEqual((source/'example.txt').read_text(),'New content')
            library.update(identity,remote_sources=[{'path':str(source),'uri':'smb://lost/source'}])
            with patch.object(setup,'network',side_effect=ValueError('source lost')) as reconnect:
                self.assertTrue(vault.run(library,identity,'snapshots',job))
                reconnect.assert_not_called()
            repo=Path(plan['repository']); before={str(p.relative_to(repo)):p.read_bytes() for p in repo.rglob('*') if p.is_file()}
            adopted=setup.configure(library,dict(title='Recovered',repository=str(repo),password=request['password'],adopt=True),job)['id']
            self.assertEqual(library.get(adopted)['sources'],[])
            self.assertEqual(before,{str(p.relative_to(repo)):p.read_bytes() for p in repo.rglob('*') if p.is_file()})
            missing=root/'missing-mount/repo';library.update(identity,repository=str(missing),network_uri='smb://offline/share/repo')
            with patch.object(setup,'network',side_effect=ValueError('offline')):
                with self.assertRaises(ValueError):vault.run(library,identity,'backup',job)
            self.assertFalse(missing.exists())

if __name__=='__main__': unittest.main()
