"""A user notebook move can overlap background memory work in the same Store."""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch


class NotesMemoryLockOrderTest(unittest.TestCase):
    def test_move_and_memory_write_finish_without_timeout_termination(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            'HOME': tmp, 'XDG_CONFIG_HOME': tmp+'/config', 'XDG_DATA_HOME': tmp+'/data',
            'LUMEN_DATA': tmp+'/state', 'LUMEN_TOOLS_DATA': tmp+'/tools',
        }):
            from lumen_store import Store
            from lumen_memory import Memory
            from wissen_data import Notebook
            import notes_move
            store = Store(Path(tmp)/'state'); book = Notebook(store, Path(tmp)/'notes', create=True)
            book.write('One.md', '# One\n\nKeep this note', '')
            memory = Memory(store); plan = notes_move.plan(book, 'One.md', 'Moved.md')
            original = Notebook.lock; memory_holds = threading.Event(); move_waiting = threading.Event()
            errors = []; completed = []
            @contextmanager
            def observed(self, name='wissen.lock'):
                who = threading.current_thread().name
                if who == 'audit-move' and name == 'memory-state.lock': move_waiting.set()
                with original(self, name):
                    if who == 'audit-memory' and name == 'memory-state.lock':
                        memory_holds.set()
                        if not move_waiting.wait(2): raise TimeoutError('Move did not reach shared lock')
                    yield
            def run(name, function):
                try: function(); completed.append(name)
                except Exception as error: errors.append(error)
            with patch.object(Notebook, 'lock', observed):
                writer = threading.Thread(name='audit-memory', target=run,
                    args=('memory', lambda: memory.remember('Preference', 'Synthetic preference')), daemon=True)
                mover = threading.Thread(name='audit-move', target=run,
                    args=('move', lambda: notes_move.execute(book, plan)), daemon=True)
                writer.start(); self.assertTrue(memory_holds.wait(2)); mover.start()
                writer.join(2); mover.join(2)
                self.assertEqual(errors, [])
                self.assertCountEqual(completed, ['memory', 'move'])
            self.assertIn('Keep this note', book.read('Moved.md')['text'])
