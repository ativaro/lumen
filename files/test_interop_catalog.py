import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lumen_store import Store
from tools_data import Library, Cancelled
from tools_ui import Job
from interop_data import Registry
import inbox_data
import interop_catalog as catalog


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = Registry(self.root/'tools')
        self.store = Store(self.root/'state')

    def test_index_existing_apps_content_backlinks_and_reader_origin(self):
        resource = self.root/'research.md'; resource.write_text('Original')
        reader = Library('reader', self.root/'tools')
        book = reader.create('Reading', notes=[dict(text='ultraviolet marker')], source=resource.as_uri())
        book_url = self.registry.register(dict(app='reader', kind='record', id=book, title='Reading'))
        workbench = Library('workbench', self.root/'tools')
        project = workbench.create('Project', notes='acetylene proposal', resources=[dict(kind='file', title='Research', target=str(resource))], interop_sources=[book_url])
        before = sorted(path.name for path in (self.root/'tools').iterdir())
        counts = catalog.index_local(self.registry, self.store)
        self.assertEqual(counts['skipped'], 0)
        self.assertGreaterEqual(counts['links'], 3)
        self.assertEqual(sorted(path.name for path in (self.root/'tools').iterdir()), before)
        self.assertEqual(self.registry.search('acetylene')[0]['id'], project)
        self.assertEqual(self.registry.search('ultraviolet')[0]['id'], book)
        related = self.registry.related(book_url)
        self.assertTrue(any(row['id'] == project for row in related))
        self.assertTrue(any(row.get('path') == str(resource) for row in related))

    def test_notebooks_link_text_and_ignore_symlinks(self):
        notebook = self.store.directory/'lumen-memory'; notebook.mkdir()
        (notebook/'first.md').write_text('# First\n\nNeptunium analysis [[Second]]')
        (notebook/'second.md').write_text('# Second\n\nObservable energy')
        outside = self.root/'secret.md'; outside.write_text('# Outside\n\nNever index symlink content')
        (notebook/'escape.md').symlink_to(outside)
        (notebook/'escape-dir').symlink_to(self.root, target_is_directory=True)
        counts = catalog.index_local(self.registry, self.store)
        self.assertEqual(counts['objects'], 2)
        first = self.registry.search('Neptunium')[0]
        self.assertEqual(first['locator']['root'], str(notebook))
        self.assertEqual(first['locator']['area'],'lumen')
        self.assertTrue(any(row['title'] == 'Second' for row in self.registry.related(first['url'])))
        self.assertEqual(self.registry.search('Never index'), [])
        self.assertFalse((self.store.directory/'wissen-history').exists())

    def test_retired_user_notes_are_not_indexed_or_searched_but_links_and_originals_remain(self):
        notebook=self.root/'old-user-notes';notebook.mkdir();path=notebook/'old.md'
        raw='# Old title\n\nOld content must not reenter the current notebook';path.write_text(raw)
        self.store.set_setting('knowledge/notebook',str(notebook))
        old=dict(app='wissen',kind='note',id='old.md',title='Old title',path=str(path),locator=dict(root=str(notebook)))
        url=self.registry.register(old);self.registry.index_text(url,raw);self.registry.set_tags(url,['old'])
        counts=catalog.index_local(self.registry,self.store)
        self.assertEqual(counts['objects'],0)
        for query in ('Old title','Old content','#old',''):self.assertEqual(self.registry.search(query),[])
        self.assertEqual(self.registry.resolve(url),old);self.assertEqual(path.read_text(),raw)

    def test_memory_reference_opens_only_the_guarded_memory_entry(self):
        from interop_open import open_url
        path=self.store.directory/'lumen-memory/entry.md'
        ref=dict(app='wissen',kind='note',id='entry.md',title='Own memory',path=str(path),locator=dict(root=str(path.parent),area='lumen'))
        url=self.registry.register(ref)
        with patch('interop_open.launch') as launch:
            open_url(url,self.root/'tools')
            launch.assert_called_once_with('wissen',[str(path),'--area','lumen'],self.root/'tools')

    def test_inbox_indexes_visible_fields_without_raw_or_account_secrets(self):
        inbox = inbox_data.store(self.root/'tools')
        account = inbox.create('Mail account', password='NeverIndexAccountSecret', url='https://invalid.test/PrivateAccountToken')
        locator = dict(account=account, folder='INBOX', validity='1', uid='2')
        with inbox.connect() as db:
            db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?)', (account, 'INBOX', '1', '2', 'thread', 'Mail title', 'a@example.invalid', 'today', 'Polonium mail body', b'NeverIndexRawMessage', 0))
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?)', ('task', 'Local task', '2026-12-01', '', 0))
            db.execute('INSERT INTO drafts VALUES (?,?,?,?)', ('draft', account, json.dumps(dict(subject='Draft subject', body='Vanadium draft', unknown='NeverIndexUnknown')), 'draft'))
            db.execute('INSERT INTO calendar_cache VALUES (?,?,?)', (account, 'event|2026-12-01', json.dumps(dict(title='Calendar title', description='Bismuth meeting', ics='NeverIndexRawCalendar'))))
        counts = catalog.index_local(self.registry, self.store)
        self.assertEqual(counts['objects'], 4)
        message = self.registry.search('Polonium')[0]
        expected = hashlib.sha256(json.dumps(locator, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(message['id'], expected)
        self.assertEqual(message['locator'], locator)
        self.assertEqual(self.registry.search('Vanadium')[0]['kind'], 'draft')
        self.assertEqual(self.registry.search('Bismuth')[0]['kind'], 'event')
        for secret in ('NeverIndex', 'PrivateAccountToken', 'RawCalendar'):
            self.assertEqual(self.registry.search(secret), [])

    def test_count_limit_and_cancel_are_bounded(self):
        library = Library('workbench', self.root/'tools')
        for i in range(7): library.create('Project '+str(i), notes='Body')
        with patch('interop_catalog.MAX_OBJECTS', 3):
            result = catalog.index_local(self.registry, self.store)
        self.assertTrue(result['limited']); self.assertLessEqual(result['objects'], 3)
        job = Job(lambda _: None); job.cancelled.set()
        with self.assertRaises(Cancelled): catalog.index_local(self.registry, self.store, job)

    def test_deleted_source_text_is_cleared_and_current_title_remains_in_history(self):
        library = Library('workbench', self.root/'tools')
        key = library.create('History item', notes='DisappearingText')
        catalog.index_local(self.registry, self.store)
        self.assertTrue(self.registry.search('DisappearingText'))
        with library.connect() as db: db.execute('DELETE FROM records WHERE id=?', (key,))
        catalog.index_local(self.registry, self.store)
        self.assertEqual(self.registry.search('DisappearingText'), [])
        self.assertTrue(self.registry.search('History item'))


if __name__ == '__main__': unittest.main()
