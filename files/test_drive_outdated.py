"""Bindings saved before account-based sync are refused: never sent, migrated or rewritten."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from uuid import uuid4
import drive_sync as drive


class OutdatedTest(unittest.TestCase):
    def setUp(self):
        # The assertions name the German source text; do not depend on the language of the test machine.
        language = patch('lumen_i18n.language', return_value='de'); language.start(); self.addCleanup(language.stop)

    def roots(self):
        old, pending = str(uuid4()), dict(request_id=str(uuid4()), staged='outgoing')
        return dict(
            whole_area=dict(workspace=old, folder=None, entries={'q': dict(pending=dict(pending))}),
            no_folder=dict(entries={}),
            never_synced_since=dict(workspace=old, folder=str(uuid4()), entries={'q': dict(request_id=str(uuid4()))}),
            other_field=dict(workspace_id=old, folder=str(uuid4()), entries={}),
            queued_upload=dict(folder=str(uuid4()), account_sync_migrated=True,
                               entries={'q': dict(pending=dict(pending, legacy_upload_target=old))}),
            prepared_upload=dict(folder=str(uuid4()), entries={'q': dict(request_id=str(uuid4()), legacy_upload_target=old)}),
        )

    def test_old_binding_is_refused_before_file_or_network_and_keeps_its_queue(self):
        for name, root in self.roots().items():
            with self.subTest(name):
                root.update(id=name, enabled=True); before = deepcopy(root); saved = []
                with patch.object(drive, 'request') as network, patch.object(drive.transport, 'upload') as upload, \
                     patch.object(drive.transport, 'request') as wire, patch.object(drive.local, 'directory') as local:
                    with self.assertRaisesRegex(ValueError, 'neu eingerichtet'):
                        drive.reconcile({}, root, lambda: saved.append(True), lambda *_: None)
                network.assert_not_called(); upload.assert_not_called(); wire.assert_not_called(); local.assert_not_called()
                self.assertTrue(saved); self.assertFalse(root['enabled'])
                self.assertEqual(root, dict(before, enabled=False))

    def test_old_binding_cannot_be_resumed_or_resolved_but_the_user_can_remove_it(self):
        for name, root in self.roots().items():
            with self.subTest(name):
                root.update(id=name, enabled=False, conflicts={'k': {}}); state = dict(scope='s', roots=[root]); before = deepcopy(state)
                with patch.object(drive, 'locked'), patch.object(drive, 'read', return_value=state), patch.object(drive, 'save') as save:
                    with self.assertRaisesRegex(ValueError, 'neu eingerichtet'): drive.toggle(name, True)
                    with self.assertRaisesRegex(ValueError, 'neu eingerichtet'): drive.choose(name, 'k', 'local')
                    save.assert_not_called(); self.assertEqual(state, before)
                    drive.toggle(name, remove=True)
                    save.assert_called_once_with(dict(scope='s', roots=[]))

    def test_account_binding_with_a_leftover_field_keeps_running_and_is_not_rewritten(self):
        root = dict(workspace=str(uuid4()), account_sync_migrated=True, folder=str(uuid4()), enabled=True,
                    entries={'new': dict(pending=dict(request_id=str(uuid4()), staged='new-outgoing'))})
        before = deepcopy(root); saved = []
        self.assertFalse(drive.outdated(root)); self.assertFalse(drive.outdated(dict(folder=str(uuid4()), entries={})))
        with patch.object(drive.local, 'directory', side_effect=RuntimeError('file-boundary')), patch.object(drive, 'request') as network:
            with self.assertRaisesRegex(RuntimeError, 'file-boundary'): drive.reconcile({}, root, lambda: saved.append(True), lambda *_: None)
        network.assert_not_called(); self.assertFalse(saved); self.assertEqual(root, before)

    def test_addresses_name_no_area_and_old_area_addresses_are_invalid(self):
        old, folder, family = [str(uuid4()) for _ in range(3)]
        self.assertEqual(drive.parse_address(drive.location(folder)), ('folder', folder))
        self.assertEqual(drive.parse_address('lumen-drive:///file/' + family + '/sample'), ('file', family))
        self.assertEqual(drive.parse_address('lumen-drive://'), ('root', None))
        for bad in ['https://x', 'lumen-drive:///folder/not-a-uuid', drive.location(folder) + '?workspace=' + old,
                    'lumen-drive://' + old, 'lumen-drive://' + old + '/' + folder, 'lumen-drive://' + old + '/file/' + family + '/sample']:
            with self.assertRaises(ValueError): drive.parse_address(bad)

    def test_account_inventory_limit_includes_folders_on_last_page(self):
        page = dict(items=[], folders=[dict(id=str(i)) for i in range(100001)], cursor='known', next=None)
        with patch.object(drive, 'request', return_value=page), patch.object(drive, 'refresh') as refresh:
            with self.assertRaises(ValueError): drive.inventory({})
            refresh.assert_not_called()


if __name__ == '__main__': unittest.main()
