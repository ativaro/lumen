import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import lumen_notifications as notifications
import lumen_transfers as transfers
from lumen_store import Store
from transfer_copy import execute
import transfer_followup as follow


class FollowupTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = patch.dict(os.environ, {
            'XDG_STATE_HOME': str(self.root / 'notifications'), 'LUMEN_LANGUAGE': 'de',
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.toast = patch.object(notifications, 'toast').start()
        self.addCleanup(patch.stopall)
        self.store = Store(self.root / 'state')
        self.source = self.root / 'image.iso'
        self.source.write_bytes(b'abcdefgh' * 256 * 1024)
        self.target = self.root / 'target'
        self.target.mkdir()
        ticket = transfers.create(self.store, 'copy', [str(self.source)], str(self.target))

        def disconnected(amount, total):
            raise OSError('synthetic disconnect')

        with self.assertRaises(OSError):
            execute(self.store, ticket, disconnected)
        self.identity = ticket['id']
        transfers.update(self.store, self.identity, status='failed', errors=['synthetic disconnect'])

    def value(self):
        return self.store.setting(transfers.PREFIX + self.identity)

    def test_opt_in_only_and_one_notification_for_unchanged_readiness(self):
        with patch.object(follow, 'probe', return_value='ready') as probe:
            follow.tick(self.store, now=10)
            probe.assert_not_called()
            follow.configure(self.store, self.identity, True, now=10)
            follow.tick(self.store, now=10)
            self.assertEqual(self.value()['followup']['state'], 'ready')
            follow.tick(self.store, now=400)
            self.assertEqual(len(notifications.snapshot()['items']), 1)
            self.assertEqual(self.toast.call_count, 1)
            self.assertEqual(self.value()['status'], 'failed')
            self.assertFalse((self.target / self.source.name).exists())

    def test_offline_backoff_snooze_and_stop_survive_reopening_store(self):
        follow.configure(self.store, self.identity, True, now=10)
        with patch.object(follow, 'probe', return_value='waiting') as probe:
            follow.tick(self.store, now=10)
            first = self.value()['followup']['next_check']
            self.assertGreaterEqual(first, 70)
            follow.tick(Store(self.store.directory), now=first - 1)
            self.assertEqual(probe.call_count, 1)
            follow.tick(self.store, now=first)
            self.assertGreater(self.value()['followup']['next_check'] - first, first - 10)
            follow.snooze(self.store, self.identity, now=first)
            self.assertEqual(self.value()['followup']['next_check'], first + 3600)
            follow.tick(self.store, now=first + 3500)
            self.assertEqual(probe.call_count, 2)
            follow.configure(self.store, self.identity, False, now=first + 3500)
            follow.tick(self.store, now=first + 8000)
            self.assertEqual(probe.call_count, 2)
        self.assertEqual(notifications.snapshot()['items'], [])

    def test_opt_out_during_probe_drops_stale_result(self):
        follow.configure(self.store, self.identity, True, now=10)

        def stop(*args):
            follow.configure(self.store, self.identity, False, now=11)
            return 'ready'

        with patch.object(follow, 'probe', side_effect=stop):
            follow.tick(self.store, now=10)
        self.assertFalse(self.value()['followup']['enabled'])
        self.assertEqual(notifications.snapshot()['items'], [])
        self.toast.assert_not_called()

    def test_new_disconnect_invalidates_old_notice_and_new_readiness_is_reported(self):
        follow.configure(self.store, self.identity, True, now=10)
        with patch.object(follow, 'probe', side_effect=['ready', 'waiting', 'ready']):
            follow.tick(self.store, now=10)
            identity = notifications.snapshot()['items'][0]['id']
            notifications.change(identity, 'read')
            follow.tick(self.store, now=self.value()['followup']['next_check'])
            self.assertTrue(all(n['archived'] for n in notifications.snapshot()['items']))
            self.assertEqual(notifications.snapshot()['unread'], 0)
            follow.tick(self.store, now=self.value()['followup']['next_check'])
        self.assertEqual(notifications.snapshot()['unread'], 1)
        self.assertEqual(self.toast.call_count, 2)

    def test_resume_and_cancel_revoke_followup_and_archive_notice(self):
        for operation in (transfers.retry, transfers.cancel):
            follow.configure(self.store, self.identity, True, now=10)
            with patch.object(follow, 'probe', return_value='ready'):
                follow.tick(self.store, now=10)
            with patch.object(transfers, 'start'):
                operation(self.store, self.identity)
            self.assertFalse(self.value()['followup']['enabled'])
            self.assertTrue(all(n['archived'] for n in notifications.snapshot()['items']))
            self.assertEqual(notifications.snapshot()['unread'], 0)
            transfers.update(self.store, self.identity, status='failed', discard=False, cancel=False)

    def test_real_readonly_probe_refuses_changed_target_source_and_staging(self):
        value = self.value()
        before = self.source.read_bytes()
        self.assertEqual(follow.inspect(value), 'ready')
        offline = self.root / 'offline'
        self.target.rename(offline)
        self.assertEqual(follow.inspect(value), 'waiting')
        self.target.mkdir()
        self.assertEqual(follow.inspect(value), 'review')
        self.target.rmdir()
        offline.rename(self.target)
        self.assertEqual(self.source.read_bytes(), before)
        stage = self.target / value['copy_plan']['stage']
        previous = self.target / 'original-staging'
        stage.rename(previous)
        stage.mkdir()
        self.assertEqual(follow.inspect(value), 'review')
        stage.rmdir()
        previous.rename(stage)
        self.source.write_bytes(b'changed')
        self.assertEqual(follow.inspect(value), 'review')
        self.assertFalse((self.target / self.source.name).exists())

    def test_unknown_targets_and_other_transfer_kinds_cannot_be_watched(self):
        value = transfers.create(self.store, 'copy', [str(self.source)], str(self.target))
        with self.assertRaises(ValueError):
            follow.configure(self.store, value['id'], True)
        with self.assertRaises(ValueError):
            follow.configure(self.store, '../outside', True)

    def test_real_bounded_child_reads_only_and_keeps_stored_ticket(self):
        value = self.value()
        self.assertEqual(follow.probe(self.store, self.identity), 'ready')
        self.assertEqual(self.value(), value)
        self.assertFalse((self.target / self.source.name).exists())

    def test_probe_timeout_returns_without_waiting_indefinitely(self):
        import subprocess
        child = unittest.mock.Mock()
        child.communicate.side_effect = subprocess.TimeoutExpired('probe', 3)
        child.wait.side_effect = subprocess.TimeoutExpired('probe', .2)
        with patch.object(follow.subprocess, 'Popen', return_value=child):
            self.assertEqual(follow.probe(self.store, self.identity), 'waiting')
        child.kill.assert_called_once()
        child.wait.assert_called_once()


if __name__ == '__main__':
    unittest.main()
