"""A user notebook move can overlap background memory work in the same Store."""
import fcntl
import os
from pathlib import Path
import tempfile
import threading
import time
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
            errors = []; completed = []
            def run(name, function):
                try: function(); completed.append(name)
                except Exception as error: errors.append(error)
            # The memory (in the service) and the move (here) wait for the same lock, memory-state.lock
            # before wissen.lock; held here first, both queue behind it and finish once it is free.
            fd = os.open(store.directory/'memory-state.lock', os.O_RDWR | os.O_CREAT, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            writer = threading.Thread(target=run, args=('memory', lambda: memory.remember('Preference', 'Synthetic preference')), daemon=True)
            mover = threading.Thread(target=run, args=('move', lambda: notes_move.execute(book, plan)), daemon=True)
            writer.start(); time.sleep(.3); mover.start(); time.sleep(.3)
            self.assertEqual(completed, [])
            os.close(fd)
            writer.join(20); mover.join(20)
            self.assertEqual(errors, [])
            self.assertCountEqual(completed, ['memory', 'move'])
            self.assertIn('Keep this note', book.read('Moved.md')['text'])
            self.assertEqual([n['title'] for n in memory.scan()['notes']], ['Preference'])


if __name__ == '__main__':
    unittest.main()
