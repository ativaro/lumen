import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import lumen_actions as actions
from lumen_store import Store


class ActionSerializationTest(unittest.TestCase):
    def test_overlapping_tasks_keep_each_predecessor_for_undo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); target = root / 'result.txt'; target.write_text('A')
            store = Store(root / 'state')
            tasks = [store.create_task(value, directory=tmp, roots=[tmp],
                steps=[dict(action='write', path=str(target), text=value)],
                approved=True, status='running') for value in ('B', 'C')]
            first_entered = threading.Event(); second_entered = threading.Event()
            first_done = threading.Event(); errors = []
            original = actions.atomic_write
            def write(parent, name, data, mode):
                if data == b'B':
                    first_entered.set(); second_entered.wait(.3)
                    original(parent, name, data, mode); first_done.set()
                else:
                    second_entered.set()
                    if not first_done.wait(3): raise TimeoutError('First write stalled')
                    original(parent, name, data, mode)
            def run(task):
                try: actions.execute(store, task, store.task(task)['steps'][0])
                except BaseException as error: errors.append(error)
            with patch.object(actions, 'atomic_write', side_effect=write):
                first = threading.Thread(target=run, args=(tasks[0],)); first.start()
                self.assertTrue(first_entered.wait(3))
                second = threading.Thread(target=run, args=(tasks[1],)); second.start()
                first.join(5); second.join(5)
                self.assertFalse(first.is_alive() or second.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(target.read_text(), 'C')
            actions.undo(store, store.changes(tasks[1])[0]['id'])
            self.assertEqual(target.read_text(), 'B')
            actions.undo(store, store.changes(tasks[0])[0]['id'])
            self.assertEqual(target.read_text(), 'A')
