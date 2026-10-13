import hashlib,json,os,tempfile,unittest
from pathlib import Path
from vault_catalogue import entries

class CatalogueTest(unittest.TestCase):
    def test_labels_survive_lock_but_not_disable_and_never_admit_extra_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.assertFalse(entries(root=root)['enabled'])
            cipher=root/'vault.kdbx'; cipher.write_bytes(b'encrypted-fixture'); cipher.chmod(0o600)
            row=dict(id='12345678-1234-1234-1234-123456789abc',title='Example',kind='token',origin='https://example.test')
            data=dict(version=1,sha256=hashlib.sha256(cipher.read_bytes()).hexdigest(),updated='2026-10-13T10:00:00Z',entries=[row])
            path=root/'assistant-catalogue.json'
            def save(): path.write_text(json.dumps(data));path.chmod(0o600)
            save()
            value=entries(root=root)
            self.assertEqual(value['entries'][0]['title'],'Example')
            self.assertTrue(value['requires_confirmation']);self.assertFalse(value['secrets_available']);self.assertFalse(value['stale'])
            cipher.write_bytes(b'changed encrypted fixture')
            self.assertTrue(entries(root=root)['stale'])
            self.assertEqual(entries(root=root)['entries'],[])
            self.assertIsNone(entries(root=root)['next_offset'])
            for key in ('password','username','notes','fields'):
                row[key]='must-not-be-read';save()
                with self.assertRaises(ValueError): entries(root=root)
                del row[key]
            row['origin']='https://example.test/path?secret=hidden';save()
            with self.assertRaises(ValueError):entries(root=root)
            path.unlink();self.assertFalse(entries(root=root)['enabled'])

    def test_symlink_and_public_permissions_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);outside=root/'outside';outside.write_text('{}')
            path=root/'assistant-catalogue.json';path.symlink_to(outside)
            with self.assertRaises(OSError):entries(root=root)
            path.unlink();path.write_text('{}');path.chmod(0o644)
            with self.assertRaises(ValueError):entries(root=root)

if __name__=='__main__':unittest.main()
