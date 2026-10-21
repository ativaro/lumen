import tempfile
from pathlib import Path
import unittest
from lumen_store import Store
from wissen_data import Notebook,parse
from notes_move import rewrite,plan


class MoveTest(unittest.TestCase):
    def test_links_anchors_aliases_images_and_code(self):
        texts={'A/One.md':'# One\n[[../Two#Part|label]]\n![](image.png)\n[[#Here]]','Two.md':'# Two\n[[A/One#^block|alias]]\n[go](A/One.md#Part)\n`[[A/One]]`\n```\n[[A/One]]\n```'}
        notes={p:parse(p,t.encode()) for p,t in texts.items()}
        out=rewrite(texts['Two.md'],'Two.md','A','B',notes)
        self.assertIn('[[B/One.md#^block|alias]]',out);self.assertIn('[go](B/One.md#Part)',out)
        self.assertIn('`[[A/One]]`',out);self.assertIn('```\n[[A/One]]',out)
        out=rewrite(texts['A/One.md'],'A/One.md','A/One.md','Two/New.md',notes)
        self.assertIn('![](../A/image.png)',out);self.assertIn('[[#Here]]',out)
    def test_plan_is_readonly_preserves_raw_metadata_rejects_collision(self):
        with tempfile.TemporaryDirectory() as root:
            book=Notebook(Store(Path(root)/'state'),Path(root)/'notes',create=True)
            book.create_collection('A');raw='\ufeff<!-- lumen: {"source":"x","custom":"keep"} -->\n# One\n'
            (book.root/'A/One.md').write_bytes(raw.encode());book.write('Two.md','# Two\n[[A/One]]','')
            value=plan(book,'A/One.md','New.md')
            self.assertEqual((book.root/'A/One.md').read_bytes(),raw.encode());self.assertFalse((book.root/'New.md').exists())
            self.assertTrue(any(c['after'].startswith('\ufeff<!-- lumen:') for c in value['changes']))
            with self.assertRaises(ValueError):plan(book,'A/One.md','Two.md')
            with self.assertRaises(ValueError):plan(book,'A/One.md','../bad.md')

    def make_book(self,root):
        book=Notebook(Store(Path(root)/'state'),Path(root)/'notes',create=True)
        book.create_collection('A');book.create_collection('B')
        book.write('A/One.md','# One\n\n[image](pic.png)\n![](pic.png)','',note_id='11111111-1111-4111-8111-111111111111')
        book.write('Two.md','# Two\n\n[[A/One#^anchor|alias]]','')
        return book

    def test_apply_restart_undo_and_private_move_into_shared_folder(self):
        from notes_move import execute,undo
        from lumen_memory import Memory
        with tempfile.TemporaryDirectory() as root:
            book=self.make_book(root);before={n['path']:book.raw(n['path']) for n in book.scan()['notes']}
            shares=[dict(root=str(book.root),identity=book.identity,path='B',directory=True,allow=True)]
            book.store.set_setting('memory/shares',shares)
            value=plan(book,'A/One.md','B/Renamed.md');execute(book,value)
            self.assertFalse((book.root/'A/One.md').exists());self.assertIn('[[B/Renamed.md#^anchor|alias]]',book.read('Two.md')['text'])
            self.assertIn('![](../A/pic.png)',book.read('B/Renamed.md')['text'])
            self.assertEqual(book.read('B/Renamed.md')['note_id'],'11111111-1111-4111-8111-111111111111')
            memory=Memory.__new__(Memory);memory.store=book.store
            self.assertFalse(memory.shared(book,'B/Renamed.md'))
            book=Notebook(book.store,book.root);undo(book)
            self.assertEqual({n['path']:book.raw(n['path']) for n in book.scan()['notes']},before)
            self.assertEqual(book.store.setting('memory/shares'),shares)

    def test_interruption_resume_and_conflict_never_overwrites_edit(self):
        from unittest.mock import patch
        import notes_move
        with tempfile.TemporaryDirectory() as root:
            book=self.make_book(root);value=plan(book,'A','C');write=notes_move.raw_write;calls=[]
            def fail(*args):
                calls.append(1)
                if len(calls)==2:raise OSError('interrupted')
                return write(*args)
            with patch.object(notes_move,'raw_write',side_effect=fail),self.assertRaises(OSError):notes_move.execute(book,value)
            self.assertTrue(notes_move.pending(book));notes_move.execute(Notebook(book.store,book.root))
            self.assertFalse((book.root/'A').exists());self.assertIn('[[C/One.md#^anchor|alias]]',book.read('Two.md')['text'])
            current=book.read('Two.md');book.write('Two.md',current['text']+'\nNew edit',current['hash'])
            with self.assertRaises(ValueError):notes_move.undo(book)
            self.assertIn('New edit',book.read('Two.md')['text']);self.assertIsNone(notes_move.pending(book))

    def test_stale_preview_and_symlink_target_do_not_move_anything(self):
        from notes_move import execute
        with tempfile.TemporaryDirectory() as root:
            book=self.make_book(root);value=plan(book,'A/One.md','B/Renamed.md')
            book.write('New.md','# New\n[[A/One]]','')
            with self.assertRaises(ValueError):execute(book,value)
            self.assertTrue((book.root/'A/One.md').exists())
            (book.root/'escape').symlink_to(Path(root),target_is_directory=True)
            with self.assertRaises(OSError):plan(book,'A/One.md','escape/Outside.md')

    def test_pending_move_blocks_sync_before_network_request(self):
        from unittest.mock import patch
        import wissen_sync
        from notes_move import key
        with tempfile.TemporaryDirectory() as root:
            book=self.make_book(root);book.store.set_setting(key(book),{'source':'A'})
            with patch('lumen_connect.read_config',return_value={}),patch('lumen_connect.request') as request:
                with self.assertRaises(ValueError):wissen_sync.sync(book)
                request.assert_not_called()

    def test_rollback_partial_and_resume_after_rename_before_commit(self):
        from unittest.mock import patch
        import notes_move
        with tempfile.TemporaryDirectory() as root:
            book=self.make_book(root);before={n['path']:book.raw(n['path']) for n in book.scan()['notes']}
            value=plan(book,'A','C');shares=notes_move.set_shares;calls=[]
            def fail(book,rules):
                calls.append(1)
                if len(calls)==2:raise OSError('crash after rename')
                shares(book,rules)
            with patch.object(notes_move,'set_shares',side_effect=fail),self.assertRaises(OSError):notes_move.execute(book,value)
            self.assertTrue((book.root/'C').is_dir());notes_move.execute(Notebook(book.store,book.root))
            self.assertIsNone(notes_move.pending(book));notes_move.undo(book)
            self.assertEqual(before,{n['path']:book.raw(n['path']) for n in book.scan()['notes']})
            value=plan(book,'A','C')
            with patch.object(notes_move,'raw_write',side_effect=OSError('before any writes')),self.assertRaises(OSError):notes_move.execute(book,value)
            notes_move.undo(book);self.assertIsNone(notes_move.pending(book))
            self.assertEqual(before,{n['path']:book.raw(n['path']) for n in book.scan()['notes']})

    def test_markdown_titles_parentheses_metadata_and_unsupported_forms(self):
        notes={'A(one).md':parse('A(one).md',b'# One')}
        text='[go](A(one).md "caption")\n[space](<A(one).md> \'caption\')'
        out=rewrite(text,'Other.md','A(one).md','B.md',notes)
        self.assertEqual(out,'[go](B.md "caption")\n[space](<B.md> \'caption\')')
        text='---\nrelated: "[[A(one)]]"\n---\n[[A(one)]]'
        self.assertIn('related: "[[A(one)]]"',rewrite(text,'Other.md','A(one).md','B.md',notes))
        for text in ('[id]: A(one).md','<a href="A(one).md">One</a>'):
            with self.assertRaises(ValueError):rewrite(text,'Other.md','A(one).md','B.md',notes)


class NativeMoveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def wait(self,check):
        from PySide6.QtTest import QTest
        for _ in range(600):
            QTest.qWait(20)
            if check():return
        self.fail('Native move timed out')

class MoveSyncTest(unittest.TestCase):
    def test_local_move_keeps_id_and_links_but_cannot_revive_retired_sync(self):
        from unittest.mock import patch
        import wissen_sync as sync
        from notes_move import execute
        with tempfile.TemporaryDirectory() as root:
            book=Notebook(Store(Path(root)/'state'),Path(root)/'notes',create=True)
            identity='11111111-1111-4111-8111-111111111111'
            book.write('One.md','# One\nBody','',note_id=identity)
            book.write('Two.md','# Two\n[[One#Body]]','')
            execute(book,plan(book,'One.md','Renamed.md'))
            self.assertEqual(book.read('Renamed.md')['note_id'],identity)
            self.assertFalse((book.root/'One.md').exists())
            self.assertIn('[[Renamed.md#Body]]',book.read('Two.md')['text'])
            before={n['path']:n['hash'] for n in book.scan()['notes']}
            with patch('lumen_connect.request') as network:
                with self.assertRaises(ValueError):sync.sync(book)
                network.assert_not_called()
            self.assertEqual(before,{n['path']:n['hash'] for n in book.scan()['notes']})
