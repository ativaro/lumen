"""Memory publication failures use only private temporary notebooks and state."""
from contextlib import ExitStack, contextmanager
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch


class MemoryPublicationTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.dict(os.environ, {
            'HOME': str(self.root), 'XDG_CONFIG_HOME': str(self.root/'config'),
            'XDG_DATA_HOME': str(self.root/'data'), 'LUMEN_DATA': str(self.root/'state'),
            'LUMEN_TOOLS_DATA': str(self.root/'tools'), 'LUMEN_MEMORY_HOME': str(self.root/'no-model'),
        }))
        from lumen_store import Store
        from lumen_memory import Memory
        self.Memory = Memory; self.store = Store(self.root/'state'); self.memory = Memory(self.store)
        self.memory.configure(True, False)
        self.alpha = self.root/'alpha'; self.beta = self.root/'beta'
        self.alpha.mkdir(); self.beta.mkdir()

    def fail_final_metadata(self, before=''):
        save = self.memory.save_record
        def interrupted(note, meta, records):
            if note.get('hash') and note['hash'] != before:
                raise OSError('Interrupted after publishing body')
            return save(note, meta, records)
        return patch.object(self.memory, 'save_record', side_effect=interrupted)

    def test_interrupted_new_memory_keeps_intended_scope_and_is_not_approved(self):
        with self.fail_final_metadata(), self.assertRaises(OSError):
            self.memory.remember('Alpha only', 'Private alpha text', scope=str(self.alpha))
        reopened = self.Memory(self.store); note, = reopened.scan()['notes']
        self.assertEqual(note['memory']['scope'], str(self.alpha))
        self.assertFalse(note['memory']['allowed'])
        self.assertEqual(reopened.eligible(str(self.beta)), [])
        self.assertEqual(reopened.eligible(str(self.alpha)), [])

    def test_interrupted_rescope_cannot_publish_new_text_in_the_old_scope(self):
        original = self.memory.remember('Old beta', 'Old beta text', scope=str(self.beta))
        with self.fail_final_metadata(original['hash']), self.assertRaises(OSError):
            self.memory.remember('Alpha only', 'New private alpha text', scope=str(self.alpha),
                                 path=original['path'], expected=original['hash'])
        reopened = self.Memory(self.store); note, = reopened.scan()['notes']
        self.assertEqual(note['memory']['scope'], str(self.alpha))
        self.assertFalse(note['memory']['allowed'])
        self.assertEqual(reopened.eligible(str(self.beta)), [])

    def test_interrupted_same_body_rescope_invalidates_an_inflight_global_search(self):
        original = self.memory.remember('Secret', 'Private alpha detail')
        save = self.memory.save_record
        calls = 0
        def interrupted(note, meta, records):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('Interrupted before final approval')
            return save(note, meta, records)
        def rescope_after_snapshot(_memory, _query):
            with patch.object(self.memory, 'save_record', side_effect=interrupted):
                with self.assertRaises(OSError):
                    self.memory.remember('Secret', 'Private alpha detail', scope=str(self.alpha),
                                         path=original['path'], expected=original['hash'])
            return [], None
        with patch('lumen_connect.memory_stamp', return_value='synthetic'), patch('knowledge_context.fetch', side_effect=rescope_after_snapshot) as fetch:
            result = self.memory.prepare('Private alpha detail', str(self.beta))
        fetch.assert_called_once()
        self.assertEqual(self.memory.book.read(original['path'])['hash'], original['hash'])
        self.assertEqual(result['context'], '')
        self.assertEqual(result['notes'], [])
        self.assertFalse(self.Memory(self.store).scan()['notes'][0]['memory']['allowed'])

    def test_search_waits_for_the_approval_snapshot_during_publication(self):
        original = self.memory.remember('Secret', 'Private alpha detail')
        invalidated = threading.Event(); release = threading.Event(); searching = threading.Event()
        changed = self.memory.changed; lock = self.memory.book.lock; save = self.memory.save_record
        results = []; errors = []; calls = 0
        def paused_change(invalidate=False):
            changed(invalidate)
            invalidated.set()
            if not release.wait(2): raise TimeoutError('Publication was not released')
        def interrupted(note, meta, records):
            nonlocal calls
            calls += 1
            if calls == 2: raise OSError('Interrupted before final approval')
            return save(note, meta, records)
        @contextmanager
        def observed_lock(name='wissen.lock'):
            if threading.current_thread().name == 'search' and name == 'memory-state.lock':
                searching.set()
            with lock(name): yield
        def writer():
            try:
                self.memory.remember('Secret', 'Private alpha detail', scope=str(self.alpha),
                                     path=original['path'], expected=original['hash'])
            except OSError: pass
            except Exception as error: errors.append(error)
        def reader():
            try: results.append(self.memory.prepare('Private alpha detail', str(self.beta)))
            except Exception as error: errors.append(error)
        with patch.object(self.memory, 'changed', side_effect=paused_change), patch.object(self.memory, 'save_record', side_effect=interrupted), patch.object(self.memory.book, 'lock', side_effect=observed_lock):
            writing = threading.Thread(target=writer, daemon=True)
            reading = threading.Thread(target=reader, name='search', daemon=True)
            writing.start()
            try:
                self.assertTrue(invalidated.wait(2))
                reading.start()
                self.assertTrue(searching.wait(2))
            finally:
                release.set(); writing.join(2)
                if reading.ident is not None: reading.join(2)
            self.assertFalse(writing.is_alive()); self.assertFalse(reading.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['context'], '')
        self.assertEqual(results[0]['notes'], [])

    def test_failed_body_write_preserves_existing_metadata_and_grant(self):
        original = self.memory.remember('Original', 'Old text', scope=str(self.beta))
        before = self.store.setting('memory/records', {})
        with patch.object(self.memory.book, 'write', side_effect=OSError('Before body write')):
            with self.assertRaises(OSError):
                self.memory.remember('New', 'New text', scope=str(self.alpha),
                                     path=original['path'], expected=original['hash'])
        self.assertEqual(self.store.setting('memory/records', {}), before)
        self.assertEqual(self.memory.book.read(original['path'])['text'], original['text'])

    def test_success_preserves_private_grant_and_leaves_no_pending_identity(self):
        original = self.memory.remember('Original', 'Old text', scope=str(self.alpha))
        original = self.memory.allow(original['path'], original['hash'], False)
        saved = self.memory.remember('Updated', 'New text', scope=str(self.alpha),
                                     path=original['path'], expected=original['hash'])
        self.assertFalse(saved['memory']['allowed'])
        created = self.memory.remember('New', 'Completed text', scope=str(self.alpha))
        self.assertTrue(created['memory'].get('allowed', True))
        self.assertEqual(set(self.store.setting('memory/records', {})), {saved['path'], created['path']})

    def test_legacy_note_and_stale_edit_keep_their_existing_boundaries(self):
        legacy = self.memory.book.write('Legacy.md', '# Legacy\n\nOriginal', '')
        self.assertEqual(legacy['note_id'], '')
        with self.fail_final_metadata(legacy['hash']), self.assertRaises(OSError):
            self.memory.remember('Scoped legacy', 'Private alpha text', scope=str(self.alpha),
                                 path=legacy['path'], expected=legacy['hash'])
        self.assertEqual(self.Memory(self.store).eligible(str(self.beta)), [])
        before = self.store.setting('memory/records', {})
        with self.assertRaises(ValueError):
            self.memory.remember('Stale', 'Must not write', path=legacy['path'], expected=legacy['hash'])
        self.assertEqual(self.store.setting('memory/records', {}), before)
