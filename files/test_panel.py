import os
from pathlib import Path
import tempfile
import unittest

from lumen_panel import snapshot, valid_task
from lumen_store import Store


class PanelTest(unittest.TestCase):
    def test_dismissal_persists_without_deleting_history_and_rejects_active_tasks(self):
        from contextlib import redirect_stdout
        import io, json
        from unittest.mock import patch
        from lumen_panel import main
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp}):
            store = Store()
            for i in range(6): store.create_task(str(i), directory=tmp, status='completed')
            task = store.tasks()[0]['id']; store.update_task(task, result='Ergebnis behalten')
            store.event(task, 'completed', 'Verlauf behalten')
            before, events = store.task(task), store.events(task)
            output = io.StringIO()
            with patch('sys.argv', ['lumen-panel', '--dismiss-task', task]), redirect_stdout(output): main()
            self.assertEqual(len(json.loads(output.getvalue())['recent']), 5)
            self.assertNotIn(task, [r['id'] for r in snapshot()['recent']])
            restarted = Store(tmp)
            self.assertEqual(restarted.task(task), before); self.assertEqual(restarted.events(task), events)
            self.assertEqual(len(restarted.tasks()), 6); self.assertEqual(len(restarted.tasks(False)), 5)
            restarted.dismiss_task(task)  # Duplicate clicks remain harmless.
            active = store.create_task('Aktiv', directory=tmp, status='running')
            with self.assertRaises(ValueError): store.dismiss_task(active)
            with self.assertRaises(ValueError): store.dismiss_task('0' * 32)
            self.assertIsNone(store.setting('tasks/dismissed/' + active))
            restarted.update_task(task, result='Neues Ergebnis')
            self.assertIn(task, [r['id'] for r in snapshot()['recent']])
            cancelled = store.create_task('Abgebrochen', directory=tmp, status='cancelled')
            store.event(cancelled, 'cancelled', 'Durch Nutzer abgebrochen')
            before, events = store.task(cancelled), store.events(cancelled)
            with patch('sys.argv', ['lumen-panel', '--dismiss-task', cancelled]), redirect_stdout(io.StringIO()): main()
            self.assertNotIn(cancelled, [r['id'] for r in snapshot()['recent']])
            self.assertNotIn(cancelled, [r['id'] for r in Store(tmp).tasks(False)])
            self.assertEqual(store.task(cancelled), before)
            self.assertEqual(store.events(cancelled), events)
            store.dismiss_task(cancelled)

    def test_native_controls_validate_input_and_report_missing_services(self):
        from unittest.mock import patch
        import subprocess
        import lumen_controls as controls
        with patch.object(controls, 'run', side_effect=['Volume: 0.55 [MUTED]', '10000', '7500', 'connected']):
            self.assertEqual(controls.snapshot(), {'volume': 55, 'muted': True, 'brightness': 75, 'network': 'Verbunden'})
        with patch.object(controls, 'run', side_effect=FileNotFoundError):
            self.assertEqual(controls.snapshot()['volume'], None)
            self.assertEqual(controls.snapshot()['brightness'], None)
        with patch.object(controls, 'run') as run:
            for value in (-1, 101, '50; false', None, True):
                with self.assertRaises(ValueError): controls.control('volume', value)
            run.assert_not_called()
            controls.control('volume', 45)
            self.assertEqual(run.call_args.args[0], ['wpctl', 'set-volume', '-l', '1', '@DEFAULT_AUDIO_SINK@', '45%'])
        with patch.object(controls, 'run', side_effect=['10000', '100', '']) as run:
            controls.control('brightness', 0)
            self.assertEqual(run.call_args.args[0][-1], '100')
        with patch.object(controls, 'run', side_effect=subprocess.TimeoutExpired('wpctl', 3)):
            self.assertIsNone(controls.snapshot()['volume'])

    def test_shared_snapshot_is_bounded_read_only_and_detects_lost_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'state'
            self.assertEqual(snapshot(directory)['active'], [])
            self.assertFalse(directory.exists())
            store = Store(directory); other = Store(directory)
            task = store.create_task('Dateien aus Files', directory=tmp, status='running')
            lease = store.acquire(task)
            try:
                self.assertTrue(snapshot(directory)['busy'])
                other.update_task(task, status='needs_input')
                self.assertTrue(snapshot(directory)['attention'])
                other.update_task(task, status='completed', result='<b>$(false)</b>' + 'x' * 2000)
                photo = snapshot(directory)
                self.assertEqual(photo['active'], [])
                self.assertEqual(len(photo['recent'][0]['result']), 1600)
                self.assertTrue(photo['recent'][0]['truncated'])
                self.assertTrue(photo['recent'][0]['result'].startswith('<b>$(false)</b>'))
                other.update_task(task, status='running')
            finally: os.close(lease)
            before = store.path.read_bytes()
            self.assertEqual(snapshot(directory)['active'][0]['status'], 'interrupted')
            self.assertEqual(store.path.read_bytes(), before)
            self.assertEqual(store.task(task)['status'], 'running')
            for i in range(12): store.create_task(str(i), directory=tmp, status='completed')
            self.assertEqual(len(snapshot(directory)['recent']), 5)
            with store.connect() as db:
                db.execute('BEGIN EXCLUSIVE')
                self.assertTrue(snapshot(directory)['error'])
            store.path.write_bytes(b'broken')
            self.assertTrue(snapshot(directory)['error'])

    def test_app_catalogue_launches_every_app_and_tasks_load_more(self):
        from lumen_panel import applications, main
        from lumen_apps import catalogue
        from unittest.mock import patch
        self.assertEqual({a['id'] for a in applications()}, {a[0] for a in catalogue()})
        for app in applications():
            with patch('sys.argv', ['lumen-panel','--open-app',app['id']]), patch('lumen_panel.subprocess.Popen') as start:
                main()
                self.assertTrue(Path(start.call_args.args[0][0]).is_file())
                self.assertNotIn('shell',start.call_args.kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp)
            for i in range(31):store.create_task(str(i),directory=tmp,status='completed')
            self.assertEqual(len(snapshot(tmp,20)['recent']),20);self.assertTrue(snapshot(tmp,20)['more'])
            self.assertEqual(len(snapshot(tmp,40)['recent']),31);self.assertFalse(snapshot(tmp,40)['more'])
            with self.assertRaises(ValueError):snapshot(tmp,1001)

    def test_task_ids_cannot_be_commands_or_paths(self):
        for value in ['../task', 'a;touch /tmp/x', '', '<b>', '0'*33]:
            with self.assertRaises(ValueError): valid_task(value)
        self.assertEqual(valid_task('a'*32), 'a'*32)

    def test_launcher_passes_only_explicit_arguments_without_shell(self):
        from unittest.mock import patch
        from lumen_panel import main
        with patch.dict(os.environ, {'LUMEN_BIN_DIR': '/tmp/Lumen with spaces'}), \
             patch('sys.argv', ['lumen-panel', '--open-task', 'a'*32]), \
             patch('lumen_panel.subprocess.Popen') as launch:
            main()
            self.assertEqual(launch.call_args.args[0], [str(Path(__file__).resolve().parents[1]/'bin/lumen-agent-app'), '--task', 'a'*32])
            self.assertTrue(launch.call_args.kwargs['start_new_session'])
            self.assertNotIn('shell', launch.call_args.kwargs)
        for flag, binary in [('--search', 'lumen-search'), ('--voice', 'lumen-search'), ('--settings', 'lumen-settings')]:
            with patch('sys.argv', ['lumen-panel', flag]), patch('lumen_panel.subprocess.Popen') as launch:
                main()
                self.assertEqual(launch.call_args.args[0], [str(Path(__file__).resolve().parents[1]/'bin'/binary)] + (['--voice'] if flag == '--voice' else []))
