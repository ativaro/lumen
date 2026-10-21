import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools_data import Cancelled, Library
from tools_ui import Job
import inbox_data
import interop_inbox_backup as backup
import interop_vault as vault


class LocalInboxBackupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.source = inbox_data.store(self.root/'source')
        self.target = inbox_data.store(self.root/'target'); self.job = Job(lambda _: None)
        account = self.source.create('Private', kind='imap', password='SECRET_ACCOUNT', host='SECRET_HOST')
        self.account = self.target.create('Reviewed destination', kind='imap')
        (self.source.assets/'attachment.txt').write_text('Keep this attachment')
        (self.source.assets/'unrelated.txt').write_text('UNRELATED_ASSET')
        with self.source.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS interop_task_details(task TEXT PRIMARY KEY,body TEXT NOT NULL)')
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,0)', ('task','Saved task','2026-12-01',''))
            db.execute('INSERT INTO interop_task_details VALUES (?,?)',('task','Full task description'))
            draft = dict(to='person@example.invalid', subject='Saved draft', body='Draft body', reply_to='',
                         attachments=[dict(asset='attachment.txt', name='Letter.txt')], formatted=True,unknown='SECRET_UNKNOWN')
            db.execute('INSERT INTO drafts VALUES (?,?,?,?)', ('draft', account, json.dumps(draft), 'draft'))
            db.execute('INSERT INTO drafts VALUES (?,?,?,?)', ('sent', account, json.dumps(draft), 'sent'))
            db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?)', (account,'INBOX','1','1','thread','Mail','sender','date','SECRET_MESSAGE_BODY',b'SECRET_RAW',0))
        self.package = self.root/'package'
        backup.export_package(self.source.root, self.package, self.job)

    def test_only_local_tasks_unsent_drafts_and_referenced_attachments_exported(self):
        value, digest = backup.read_package(self.package)
        self.assertEqual(len(value['tasks']), 1); self.assertEqual(len(value['drafts']), 1)
        all_bytes = b''.join(path.read_bytes() for path in self.package.rglob('*') if path.is_file())
        self.assertNotIn(b'SECRET_', all_bytes); self.assertNotIn(b'UNRELATED_ASSET', all_bytes)
        self.assertNotIn('account', value['drafts'][0])
        self.assertEqual(value['tasks'][0]['body'],'Full task description')
        self.assertTrue(value['drafts'][0]['data']['formatted'])
        self.assertEqual((self.package/'attachments/attachment.txt').read_text(), 'Keep this attachment')
        self.assertFalse((self.package/'library.sqlite').exists())

    def test_reviewed_account_import_is_unsent_nonoverwriting_and_replay_safe(self):
        with patch('smtplib.SMTP') as send:
            first = backup.import_package(self.package, self.target, self.account, self.job)
            again = backup.import_package(self.package, self.target, self.account, self.job)
            send.assert_not_called()
        self.assertEqual((first['tasks'], first['drafts']), (1, 1))
        self.assertEqual((again['tasks'], again['drafts']), (0, 0))
        self.assertEqual(first['refs'], again['refs'])
        with self.target.connect() as db:
            rows = db.execute('SELECT account,status,data FROM drafts').fetchall()
            self.assertEqual(len(rows), 1); self.assertEqual(rows[0]['account'], self.account); self.assertEqual(rows[0]['status'], 'draft')
            data = json.loads(rows[0]['data']); self.assertEqual(data['subject'], 'Saved draft')
            self.assertTrue(data['formatted'])
            self.assertEqual(db.execute('SELECT body FROM interop_task_details').fetchone()[0],'Full task description')
            self.assertEqual(self.target.asset(data['attachments'][0]['asset']).read_text(), 'Keep this attachment')
            self.assertNotIn('unknown', data)
        self.assertEqual(len(list(self.target.assets.iterdir())), 1)

    def test_missing_target_account_changed_package_or_attachment_abort(self):
        with self.assertRaises(ValueError): backup.import_package(self.package, self.target, 'missing', self.job)
        with self.target.connect() as db: self.assertEqual(db.execute('SELECT count(*) FROM tasks').fetchone()[0], 0)
        value, digest = backup.read_package(self.package)
        value['tasks'][0]['title'] = 'Changed during review'; (self.package/backup.PACKAGE).write_text(json.dumps(value))
        with self.assertRaises(ValueError): backup.import_package(self.package, self.target, self.account, self.job, expected=digest)
        (self.package/'attachments/attachment.txt').write_text('Tampered')
        with self.assertRaises(ValueError): backup.import_package(self.package, self.target, self.account, self.job)
        with self.target.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM tasks').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM drafts').fetchone()[0], 0)
        self.assertEqual(list(self.target.assets.iterdir()), [])

    def test_cancel_after_attachment_copy_rolls_back_rows_and_files(self):
        original = self.target.import_file
        def copy(*args, **kwargs):
            result = original(*args, **kwargs); self.job.cancelled.set(); return result
        with patch.object(self.target, 'import_file', side_effect=copy), self.assertRaises(Cancelled):
            backup.import_package(self.package, self.target, self.account, self.job)
        with self.target.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM tasks').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM drafts').fetchone()[0], 0)
        self.assertEqual(list(self.target.assets.iterdir()), [])

    def test_prepared_subset_capsule_has_no_account_database(self):
        plan = dict(sources=[str(self.source.root)], app_sources=[dict(app='inbox', path=str(self.source.root),
                    slot='inbox-local', kind='inbox-local', title='Local Inbox')])
        with vault.prepared_sources(plan, self.job) as (paths, excluded, manifest):
            root = Path(paths[-1]); self.assertTrue((root/'inbox-local'/backup.PACKAGE).is_file())
            self.assertFalse(any(root.rglob('library.sqlite')))
            self.assertEqual(excluded, [str(self.source.root)])
            bundles = vault.restored_bundles(root)
            self.assertEqual(bundles[0]['sources'][0]['kind'], 'inbox-local')
            with self.assertRaises(ValueError): vault.open_restored(bundles[0], 'inbox')

    def test_real_restic_selective_backup_restore_and_reviewed_import(self):
        import vault_data
        program=os.environ.get('LUMEN_TEST_RESTIC') or vault_data.binary()
        if not program:self.skipTest('Restic optional')
        repository=self.root/'repository';repository.mkdir();restored=self.root/'restored';restored.mkdir()
        plans=Library('vault',self.source.root.parent);passwords={}
        def keyring(_namespace,key,value=None):
            if value is not None:passwords[key]=value
            return passwords[key]
        with patch('vault_data.secret',side_effect=keyring),patch('vault_data.binary',return_value=program):
            identity=vault_data.create(plans,'Selective',str(repository),[str(self.source.root)],'synthetic-password-12345',self.job)
            vault.merge_sources(plans,identity,[dict(app='inbox',path=str(self.source.root),slot='inbox-local',kind='inbox-local',title='Local Inbox')])
            vault_data.run(plans,identity,'backup',self.job)
            snapshot=vault_data.run(plans,identity,'snapshots',self.job)[0]['id']
            directory=vault_data.run(plans,identity,'restore',self.job,snapshot=snapshot,destination=str(restored))
        self.assertFalse(any(Path(directory).rglob('library.sqlite')))
        source=vault.restored_bundles(directory)[0]['sources'][0]['restored']
        value,digest=backup.read_package(source)
        result=backup.import_package(source,self.target,self.account,self.job,expected=digest)
        self.assertEqual((result['tasks'],result['drafts']),(1,1))

    def test_damaged_unsent_draft_is_reported_instead_of_silently_omitted(self):
        with self.source.connect() as db:db.execute("INSERT INTO drafts VALUES ('damaged','account','invalid-json','draft')")
        with self.assertRaisesRegex(ValueError,'beschädigt'):backup.export_package(self.source.root,self.root/'invalid-export',self.job)


if __name__ == '__main__': unittest.main()
