"""Cross-device moves and bounded copy progress use disposable local files only."""
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import lumen_history as history
import lumen_transfers as transfers
from lumen_store import Store
import transfer_copy
from lumen_i18n import tr


class TransferSafetyTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(self.enterContext(tempfile.TemporaryDirectory(dir='/tmp')))
        self.target = Path(self.enterContext(tempfile.TemporaryDirectory(dir='/dev/shm')))
        if self.base.stat().st_dev == self.target.stat().st_dev:
            self.skipTest('Two disposable filesystems are required')
        self.store = Store(self.base/'state')
        self.source = self.base/'folder'
        self.source.mkdir()
        (self.source/'data').write_bytes(b'checked content')
        (self.source/'empty').mkdir()
        (self.source/'link').symlink_to('data')

    def ticket(self, action='move'):
        return transfers.create(self.store, action, [str(self.source)], str(self.target))

    @property
    def trash(self):
        def dispose(file, *_):
            Path(file.get_path()).rename(self.base/'retained-trash')
            return True
        return dispose

    def test_cross_device_directory_move_uses_checked_copy(self):
        from gi.repository import Gio
        disposed = []
        def trash(file, *_):
            path=Path(file.get_path()); disposed.append(path)
            path.rename(self.base/'retained-trash')
            return True
        with patch.object(Gio.File, 'trash', trash):
            value=self.ticket(); transfers.execute(self.store, value['id'])
        result=self.store.setting(transfers.PREFIX+value['id'])
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['done'], [str(self.source)])
        self.assertFalse(self.source.exists())
        self.assertEqual((self.target/'folder/data').read_bytes(), b'checked content')
        self.assertEqual(os.readlink(self.target/'folder/link'), 'data')
        self.assertEqual(len(disposed), 1)
        self.assertEqual((self.base/'retained-trash/data').read_bytes(), b'checked content')
        entry=history.entries(self.store)[0]
        self.assertEqual(entry['kind'],'activity')
        self.assertFalse(history.can_undo(entry))

    def test_cross_device_regular_file_move_is_checked_and_retained(self):
        from gi.repository import Gio
        self.source=self.base/'plain'; self.source.write_bytes(b'file bytes')
        value=self.ticket()
        with patch.object(Gio.File, 'trash', self.trash): transfers.execute(self.store, value['id'])
        self.assertFalse(self.source.exists())
        self.assertEqual((self.target/'plain').read_bytes(), b'file bytes')
        self.assertEqual((self.base/'retained-trash').read_bytes(), b'file bytes')

    def test_cross_device_symlink_is_not_followed(self):
        from gi.repository import Gio
        self.source=self.base/'outside-link'; self.source.symlink_to(self.base/'folder/data')
        value=self.ticket()
        with patch.object(Gio.File, 'trash', self.trash): transfers.execute(self.store, value['id'])
        self.assertFalse(os.path.lexists(self.source))
        self.assertTrue((self.target/'outside-link').is_symlink())
        self.assertEqual(os.readlink(self.target/'outside-link'), str(self.base/'folder/data'))
        self.assertEqual((self.base/'folder/data').read_bytes(), b'checked content')

    def test_same_filesystem_move_keeps_atomic_path_and_existing_undo(self):
        destination=self.base/'same-device'; destination.mkdir()
        inode=self.source.stat().st_ino
        value=transfers.create(self.store, 'move', [str(self.source)], str(destination))
        with patch.object(transfer_copy, 'execute') as copied:
            transfers.execute(self.store, value['id']); copied.assert_not_called()
        self.assertFalse(self.source.exists())
        self.assertEqual((destination/'folder').stat().st_ino, inode)
        entry=history.entries(self.store)[0]
        self.assertTrue(history.can_undo(entry)); history.undo_record(self.store, entry['id'])
        self.assertEqual(self.source.stat().st_ino, inode)

    def test_target_collision_does_not_change_either_side(self):
        (self.target/'folder').mkdir(); (self.target/'folder/keep').write_text('existing')
        value=self.ticket()
        transfers.execute(self.store, value['id'])
        self.assertTrue(self.store.setting(transfers.PREFIX+value['id'])['errors'])
        self.assertEqual((self.target/'folder/keep').read_text(), 'existing')
        self.assertEqual((self.source/'data').read_bytes(), b'checked content')

    def test_move_interrupted_during_staging_never_disposes_source(self):
        from gi.repository import Gio
        (self.source/'data').write_bytes(b'x' * 2*1024**2)
        value=self.ticket()
        def stop(*_): raise OSError('pause')
        with patch.object(Gio.File, 'trash') as trash:
            with self.assertRaises(OSError): transfer_copy.execute(self.store, value, stop)
            trash.assert_not_called()
        self.assertTrue(self.source.exists()); self.assertFalse((self.target/'folder').exists())
        transfers.cleanup(self.store, self.store.setting(transfers.PREFIX+value['id']))
        self.assertEqual(list(self.target.iterdir()), [])

    def test_native_prefix_survives_unsupported_trash_and_cross_device_retry(self):
        from gi.repository import Gio
        prefix=self.target/'already-local'; prefix.write_bytes(b'atomic prefix')
        destination=self.target/'destination'; destination.mkdir()
        inode=prefix.stat().st_ino
        value=transfers.create(self.store,'move',[str(prefix),str(self.source)],str(destination))
        with patch.object(Gio.File,'trash',side_effect=OSError('Unsupported trash')):
            with self.assertRaises(ValueError): transfers.execute(self.store,value['id'])
        self.assertEqual(self.store.setting(transfers.PREFIX+value['id'])['done'],[str(prefix)])
        self.assertTrue(self.source.exists())
        with patch.object(Gio.File,'trash',self.trash): transfers.execute(self.store,value['id'])
        result=self.store.setting(transfers.PREFIX+value['id'])
        self.assertEqual(result['done'],[str(prefix),str(self.source)])
        self.assertEqual(result['errors'],[])
        self.assertEqual((destination/'already-local').stat().st_ino,inode)
        self.assertEqual((destination/'folder/data').read_bytes(),b'checked content')
        self.assertEqual([p['source'] for p in result['copy_plan']['items']],[str(self.source)])

    def test_real_gio_trash_retains_source_in_disposable_home(self):
        value=self.ticket(); transfers.execute(self.store, value['id'])
        result=self.store.setting(transfers.PREFIX+value['id'])
        self.assertEqual(result['done'], [str(self.source)])
        self.assertFalse(self.source.exists())
        held=Path(os.environ['XDG_DATA_HOME'])/'Trash/files'/result['moving'][str(self.source)]
        self.assertEqual((held/'data').read_bytes(), b'checked content')
        self.assertEqual((self.target/'folder/data').read_bytes(), b'checked content')

    def test_unsupported_trash_retains_both_trees_and_retries_without_recopy(self):
        from gi.repository import Gio
        value=self.ticket()
        with patch.object(Gio.File, 'trash', side_effect=OSError('Unsupported trash')):
            with self.assertRaises(ValueError) as failed:
                transfers.execute(self.store, value['id'])
        self.assertIn(str(self.source),str(failed.exception))
        self.assertIn(str(self.target/'folder'),str(failed.exception))
        result=self.store.setting(transfers.PREFIX+value['id'])
        self.assertEqual(result['done'], [])
        self.assertTrue(self.source.exists())
        self.assertEqual((self.source/'data').read_bytes(), b'checked content')
        inode=(self.target/'folder').stat().st_ino
        with patch.object(Gio.File, 'trash', self.trash):
            transfers.execute(self.store, value['id'])
        self.assertEqual((self.target/'folder').stat().st_ino, inode)
        self.assertFalse(self.source.exists())

    def test_crash_after_publish_resumes_before_source_disposal(self):
        from gi.repository import Gio
        value=self.ticket()
        with patch.object(transfer_copy, 'retire_source', side_effect=SystemExit('crash')):
            with self.assertRaises(SystemExit): transfers.execute(self.store, value['id'])
        self.assertTrue(self.source.exists())
        inode=(self.target/'folder').stat().st_ino
        with patch.object(Gio.File, 'trash', self.trash): transfers.execute(self.store, value['id'])
        self.assertFalse(self.source.exists())
        self.assertEqual((self.target/'folder').stat().st_ino, inode)

    def test_crash_with_quarantined_source_resumes_without_losing_it(self):
        from gi.repository import Gio
        value=self.ticket()
        with patch.object(Gio.File, 'trash', side_effect=SystemExit('crash')):
            with self.assertRaises(SystemExit): transfers.execute(self.store, value['id'])
        result=self.store.setting(transfers.PREFIX+value['id'])
        held=self.base/result['moving'][str(self.source)]
        self.assertFalse(self.source.exists())
        self.assertEqual((held/'data').read_bytes(), b'checked content')
        with patch.object(Gio.File, 'trash', self.trash): transfers.execute(self.store, value['id'])
        self.assertFalse(held.exists())
        self.assertEqual(self.store.setting(transfers.PREFIX+value['id'])['done'], [str(self.source)])

    def test_cancel_after_crash_restores_quarantined_source(self):
        from gi.repository import Gio
        value=self.ticket()
        with patch.object(Gio.File, 'trash', side_effect=SystemExit('crash')):
            with self.assertRaises(SystemExit): transfers.execute(self.store, value['id'])
        result=transfers.update(self.store, value['id'], cancel=True, discard=True)
        transfers.cleanup(self.store, result)
        self.assertEqual((self.source/'data').read_bytes(), b'checked content')
        self.assertEqual((self.target/'folder/data').read_bytes(), b'checked content')
        self.assertFalse((self.base/result['moving'][str(self.source)]).exists())

    def test_cancel_during_final_verification_prevents_trash(self):
        from gi.repository import Gio
        value=self.ticket(); verify=transfer_copy.verify_move
        def cancel(*args):
            verify(*args)
            if str(args[2]).startswith('.lumen-move-'):
                transfers.update(self.store,value['id'],cancel=True)
        with patch.object(transfer_copy,'verify_move',cancel), patch.object(Gio.File,'trash') as trash:
            with self.assertRaisesRegex(ValueError,re.escape(tr('Angehalten.'))):
                transfers.execute(self.store,value['id'])
            trash.assert_not_called()
        self.assertEqual((self.source/'data').read_bytes(),b'checked content')
        self.assertEqual(self.store.setting(transfers.PREFIX+value['id'])['done'],[])

    def test_replaced_quarantine_is_never_disposed_or_restored_over_source(self):
        from gi.repository import Gio
        value=self.ticket()
        with patch.object(Gio.File,'trash',side_effect=SystemExit('crash')):
            with self.assertRaises(SystemExit): transfers.execute(self.store,value['id'])
        result=self.store.setting(transfers.PREFIX+value['id'])
        held=self.base/result['moving'][str(self.source)]
        held.rename(self.base/'original-retained')
        held.mkdir(); (held/'other').write_text('unrelated')
        with patch.object(Gio.File,'trash') as trash:
            with self.assertRaises(ValueError): transfers.execute(self.store,value['id'])
            trash.assert_not_called()
        self.assertEqual((held/'other').read_text(),'unrelated')
        self.assertFalse(self.source.exists())
        self.assertEqual((self.base/'original-retained/data').read_bytes(),b'checked content')

    def test_crash_after_trash_before_done_checkpoint_reconciles(self):
        from gi.repository import Gio
        value=self.ticket(); update=transfers.update
        def crash(*args, **fields):
            if 'done' in fields: raise SystemExit('crash')
            return update(*args, **fields)
        with patch.object(Gio.File, 'trash', self.trash), patch.object(transfers, 'update', crash):
            with self.assertRaises(SystemExit): transfers.execute(self.store, value['id'])
        self.assertFalse(self.source.exists())
        self.assertEqual(self.store.setting(transfers.PREFIX+value['id'])['done'], [])
        with patch.object(Gio.File, 'trash') as trash:
            transfers.execute(self.store, value['id'])
            trash.assert_not_called()
        self.assertEqual(self.store.setting(transfers.PREFIX+value['id'])['done'], [str(self.source)])

    def changed_source(self, change, after_quarantine=False):
        from gi.repository import Gio
        value=self.ticket(); move=transfer_copy.local.move
        def modify(root, old, new):
            move(root, old, new)
            if after_quarantine and str(new).startswith('.lumen-move-'):
                change(Path(root['path'])/new)
            elif not after_quarantine and str(old).startswith('.lumen-copy-'):
                change(self.source)
        with patch.object(transfer_copy.local, 'move', modify), patch.object(Gio.File, 'trash') as trash:
            with self.assertRaises(ValueError) as failed:
                transfers.execute(self.store, value['id'])
            trash.assert_not_called()
        self.assertIn(str(self.source),str(failed.exception))
        self.assertIn(str(self.target/'folder'),str(failed.exception))
        self.assertTrue(self.source.exists())
        self.assertEqual(self.store.setting(transfers.PREFIX+value['id'])['done'], [])

    def test_late_added_file_prevents_source_disposal(self):
        self.changed_source(lambda p: (p/'late').write_text('new data'))
        self.assertEqual((self.source/'late').read_text(), 'new data')
        self.assertFalse((self.target/'folder/late').exists())

    def test_late_replaced_file_prevents_source_disposal(self):
        def replace(p):
            (p/'data').unlink(); (p/'data').write_bytes(b'late replacement')
        self.changed_source(replace)
        self.assertEqual((self.source/'data').read_bytes(), b'late replacement')
        self.assertEqual((self.target/'folder/data').read_bytes(), b'checked content')

    def test_changes_after_quarantine_restore_source_without_deleting_them(self):
        self.changed_source(lambda p: (p/'late').write_text('late write'), after_quarantine=True)
        self.assertEqual((self.source/'late').read_text(), 'late write')

    def test_modified_target_prevents_source_disposal(self):
        from gi.repository import Gio
        value=self.ticket(); retire=transfer_copy.retire_source
        def modify(*args):
            (self.target/'folder/data').write_bytes(b'changed target')
            return retire(*args)
        with patch.object(transfer_copy, 'retire_source', modify), patch.object(Gio.File, 'trash') as trash:
            with self.assertRaises(ValueError): transfers.execute(self.store, value['id'])
            trash.assert_not_called()
        self.assertEqual((self.source/'data').read_bytes(), b'checked content')
        self.assertEqual((self.target/'folder/data').read_bytes(), b'changed target')

    def test_recreated_original_name_is_not_overwritten_on_recovery(self):
        from gi.repository import Gio
        value=self.ticket()
        with patch.object(Gio.File, 'trash', side_effect=SystemExit('crash')):
            with self.assertRaises(SystemExit): transfers.execute(self.store, value['id'])
        self.source.mkdir(); (self.source/'new').write_text('keep')
        with patch.object(Gio.File, 'trash') as trash:
            with self.assertRaisesRegex(ValueError,re.escape(tr('Quellordner wurde inzwischen neu belegt.'))):
                transfers.execute(self.store, value['id'])
            trash.assert_not_called()
        result=self.store.setting(transfers.PREFIX+value['id'])
        self.assertEqual((self.base/result['moving'][str(self.source)]/'data').read_bytes(), b'checked content')
        self.assertEqual((self.source/'new').read_text(), 'keep')

    def test_cross_device_move_history_never_offers_unsupported_undo(self):
        target=self.target/'file'; target.write_bytes(b'keep')
        source=self.base/'file'
        identity=history.file_change(self.store, 'move', str(source), str(target))
        value=next(v for v in history.entries(self.store) if v['id']==identity)
        self.assertFalse(history.can_undo(value))
        # Older journals must be rejected too, regardless of when they were created.
        value.update(kind='file-move', before=str(source), after=history.fingerprint(target))
        self.assertFalse(history.can_undo(value))
        with self.assertRaises(ValueError): history.undo_record(self.store, identity)
        self.assertEqual(target.read_bytes(), b'keep')

    def test_copy_progress_does_not_serialize_the_plan_for_every_entry(self):
        for i in range(500): (self.source/str(i)).touch()
        value=self.ticket('copy'); calls=[]
        update=transfers.update
        def count(*args, **fields):
            calls.append(fields)
            return update(*args, **fields)
        with patch.object(transfers, 'update', count), patch('time.monotonic', return_value=1):
            transfer_copy.execute(self.store, value, lambda *_: None)
        current_only=[c for c in calls if set(c)=={'current'}]
        self.assertLessEqual(len(current_only), 2)
        self.assertTrue(any('copy_plan' in c for c in calls))
        self.assertTrue(any('publishing' in c for c in calls))
        self.assertTrue(any('done' in c for c in calls))
        self.assertTrue(any('transfer_done' in c for c in calls))
        self.assertEqual(len(list((self.target/'folder').iterdir())), 503)


if __name__ == '__main__': unittest.main()
