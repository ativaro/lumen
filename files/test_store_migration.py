"""Version 3 renames the transfer and history keys once and never overwrites a row."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from lumen_store import Store
import lumen_history
import lumen_transfers

OLD_TRANSFER, OLD_HISTORY = 'workplace/' + 'transfer/', 'workplace/' + 'history/'


class StoreMigrationTest(unittest.TestCase):
    def rows(self, directory):
        with sqlite3.connect(Path(directory) / 'lumen.sqlite3') as db:
            return dict(db.execute('SELECT key,CAST(value AS BLOB) FROM settings')), db.execute('PRAGMA user_version').fetchone()[0]

    def test_old_keys_move_once_without_touching_values_or_existing_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            Store(directory)
            ticket = '{"id": "' + 'a' * 32 + '",  "status":"paused","created":1,"updated":1,"title":"\u00e4 ä"}'
            entry = '{ "id":"' + 'b' * 32 + '","created":2.50, "title":"x" }'
            old, new = '{"id": "' + 'c' * 32 + '", "status": "failed", "created": 3, "updated": 3}', '{"id": "' + 'c' * 32 + '", "status": "completed", "created": 3, "updated": 4}'
            seed = {OLD_TRANSFER + 'a' * 32: ticket, OLD_HISTORY + 'b' * 32: entry, OLD_TRANSFER + 'c' * 32: old,
                    'transfer/' + 'c' * 32: new, 'workplace/last-mode': '"focus"', 'workplace/transfer0': '1', 'memory/revision': '7'}
            with sqlite3.connect(Path(directory) / 'lumen.sqlite3') as db:
                db.executemany('INSERT INTO settings VALUES (?,?)', seed.items()); db.execute('PRAGMA user_version=2')
            store = Store(directory)
            expected = {'transfer/' + 'a' * 32: ticket.encode(), 'history/' + 'b' * 32: entry.encode(), OLD_TRANSFER + 'c' * 32: old.encode(),
                        'transfer/' + 'c' * 32: new.encode(), 'workplace/last-mode': b'"focus"', 'workplace/transfer0': b'1', 'memory/revision': b'7'}
            self.assertEqual(self.rows(directory), (expected, 3))
            self.assertEqual(lumen_transfers.PREFIX + 'a' * 32, 'transfer/' + 'a' * 32)
            self.assertEqual(store.setting(lumen_transfers.PREFIX + 'a' * 32), json.loads(ticket))
            self.assertEqual([v['id'] for v in lumen_history.entries(store)], ['b' * 32])
            before = (Path(directory) / 'lumen.sqlite3').read_bytes()
            Store(directory)
            self.assertEqual(self.rows(directory), (expected, 3))
            self.assertEqual((Path(directory) / 'lumen.sqlite3').read_bytes(), before)

    def test_keys_written_after_the_migration_stay_and_newer_databases_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            Store(directory)
            with sqlite3.connect(Path(directory) / 'lumen.sqlite3') as db:
                db.execute('INSERT INTO settings VALUES (?,?)', (OLD_HISTORY + 'd' * 32, '{}'))
            Store(directory)
            self.assertEqual(self.rows(directory), ({OLD_HISTORY + 'd' * 32: b'{}'}, 3))
            with sqlite3.connect(Path(directory) / 'lumen.sqlite3') as db: db.execute('PRAGMA user_version=4')
            with self.assertRaises(ValueError): Store(directory)


if __name__ == '__main__':
    unittest.main()
