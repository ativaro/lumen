import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

import lumen_crash as crash


class CrashMonitorTest(unittest.TestCase):
    def test_diagnosis_selects_only_report_and_log_without_replaying_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); run = root/'crash report'; run.mkdir()
            for name in ('report.json', 'stderr.log', 'state.json'):
                (run/name).write_text('{}')
            binary = root/'bin'; binary.mkdir(); (binary/'lumen-agent-app').touch()
            with patch.dict(os.environ, {'LUMEN_BIN_DIR':str(binary), 'LUMEN_ASK_PROMPT':'Old task'}), \
                    patch.object(crash.subprocess, 'Popen') as launch:
                crash.check_with_lumen(run)
                args = launch.call_args.args[0]
                self.assertEqual(args[:3], [str(binary/'lumen-agent-app'), '--action', 'diagnose'])
                self.assertEqual(args[3:], ['--file', str(run/'report.json'), '--file', str(run/'stderr.log')])
                self.assertNotIn('LUMEN_ASK_PROMPT', launch.call_args.kwargs['env'])
                self.assertTrue((run/'state.json').exists())
                (run/'stderr.log').unlink(); (run/'stderr.log').symlink_to(run/'state.json')
                crash.check_with_lumen(run)
                self.assertNotIn(str(run/'stderr.log'), launch.call_args.args[0])
                (run/'report.json').unlink()
                with self.assertRaises(ValueError): crash.check_with_lumen(run)

    def test_recovery_dialog_can_check_report_and_keeps_recovery_available(self):
        from app import create_app
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
        app = QApplication.instance() or create_app()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA':tmp}):
            run = crash.directory()/'run-example'; run.mkdir()
            crash.write_json(run/'report.json', {'app':'files', 'status':'crashed'})
            crash.write_json(run/'state.json', {'tabs':['saved-folder']})
            current = Path(tmp)/'current'; current.mkdir()
            window = QMainWindow(); window.recovery_state = lambda: {'tabs':['current-folder']}
            def choose(box):
                button = next(b for b in box.buttons() if b.text() == 'Mit Lumen prüfen')
                button.click()
            try:
                for error in (None, OSError('Launcher unavailable')):
                    with self.subTest(error=error), patch.object(crash, 'RUN', current), \
                            patch.object(crash, 'HEARTBEAT', -1), patch.object(QMessageBox, 'exec', choose), \
                            patch.object(QMessageBox, 'warning') as warning, \
                            patch.object(crash, 'check_with_lumen', side_effect=error) as launch:
                        crash.attach(app, window, 'files')
                        QCoreApplication.processEvents()
                        launch.assert_called_once_with(run)
                        self.assertEqual(warning.call_count, int(error is not None))
                        self.assertEqual(crash.recoveries('files')[0][0], run)
                        self.assertEqual(crash.read_json(run/'state.json')['tabs'], ['saved-folder'])
                        app.crash_timer.stop(); app.crash_timer.deleteLater()
            finally: window.close(); window.deleteLater(); QCoreApplication.processEvents()

    def test_exit_signal_hang_and_recovery_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp}), patch.object(crash, 'notify', return_value=None):
            self.assertEqual(crash.monitor([sys.executable, '-c', 'pass'], 'files', poll=.01), 0)
            self.assertEqual(list(crash.directory().iterdir()), [])
            script = """
import os, signal, json
from pathlib import Path
path = Path(os.environ['LUMEN_CRASH_RUN'])
(path/'state.json').write_text(json.dumps({'tabs':['/tmp'], 'draft':'Entwurf'}))
os.kill(os.getpid(), signal.SIGKILL)
"""
            self.assertEqual(crash.monitor([sys.executable, '-c', script], 'files', poll=.01), -signal.SIGKILL)
            pending = crash.recoveries('files')
            self.assertEqual(len(pending), 1)
            path, report = pending[0]
            self.assertEqual(report['exit_code'], -signal.SIGKILL)
            self.assertEqual(crash.read_json(path/'state.json')['draft'], 'Entwurf')
            self.assertEqual(crash.directory().stat().st_mode & 0o777, 0o700)
            self.assertEqual((path/'report.json').stat().st_mode & 0o777, 0o600)
            crash.acknowledge(path)
            self.assertEqual(crash.recoveries('files'), [])
            script = """
import os, faulthandler, signal, time
from pathlib import Path
path = Path(os.environ['LUMEN_CRASH_RUN'])
faulthandler.enable(); faulthandler.register(signal.SIGUSR1)
(path/'ready').touch()
os.write(int(os.environ['LUMEN_HEARTBEAT_FD']), b'1')
time.sleep(.3)
os.write(int(os.environ['LUMEN_HEARTBEAT_FD']), b'1')
time.sleep(.05)
"""
            self.assertEqual(crash.monitor([sys.executable, '-c', script], 'search', hang_after=.15, poll=.01), 0)
            reports = [crash.read_json(p/'report.json') for p in crash.directory().iterdir()]
            hang = next(r for r in reports if r['app'] == 'search')
            self.assertEqual(hang['status'], 'closed')
            self.assertIn('responsive_again', hang)
            self.assertEqual(crash.recoveries('search'), [])
            self.assertTrue(any('File' in (p/'stderr.log').read_text() for p in crash.directory().iterdir()))

    def test_restart_drops_action_arguments_and_prompt_environment(self):
        import subprocess
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp, 'LUMEN_ASK_PROMPT': 'Never replay'}):
            script = Path(tmp)/'fail.py'; script.write_text('raise SystemExit(1)')
            command = [sys.executable, str(script), '--action', 'fix', '--prompt=Never replay']
            notice = Mock(); notice.communicate.return_value = ('restart', '')
            popen = subprocess.Popen
            restarts = []
            def launch(args, **kwargs):
                if 'pass_fds' in kwargs: return popen(args, **kwargs)
                restarts.append((args, kwargs)); return Mock()
            with patch.object(crash, 'notify', return_value=notice), patch.object(crash.subprocess, 'Popen', side_effect=launch):
                self.assertEqual(crash.monitor(command, 'lumen', poll=.01), 1)
            self.assertEqual(len(restarts), 1)
            self.assertEqual(restarts[0][0], command[:2])
            self.assertNotIn('LUMEN_ASK_PROMPT', restarts[0][1]['env'])
            self.assertNotIn('LUMEN_CRASH_RUN', restarts[0][1]['env'])

    def test_running_windows_are_not_recovered_and_stale_runs_are(self):
        import fcntl
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp}):
            run = crash.directory()/'run-example'; run.mkdir()
            crash.write_json(run/'report.json', {'app':'lumen', 'status':'running'})
            with (run/'lock').open('w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                self.assertEqual(crash.recoveries('lumen'), [])
            self.assertEqual(crash.recoveries('files'), [])
            self.assertEqual(crash.recoveries('lumen')[0][1]['status'], 'interrupted')


    def test_real_windows_survive_a_crash_without_replaying_requests(self):
        import subprocess
        repo = Path(__file__).resolve().parents[1]
        fixture = r'''import os, sys, signal, importlib.util
from pathlib import Path
import lumen_crash as crash
crash.notify = lambda *args: None
kind, mode = sys.argv[1:]
crash.supervise(kind)
from app import create_app, Window
from assistant_backend import OpenCodeBackend
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox
app = create_app()
def forbidden(*args, **kwargs): raise AssertionError('Recovery contacted the engine')
OpenCodeBackend.ensure_server = forbidden
OpenCodeBackend.send = forbidden
home = Path.home()
if kind == 'files':
    window = Window(str(home))
else:
    spec = importlib.util.spec_from_file_location('lumen_main', str(Path(os.environ['LUMEN_TEST_REPO'])/'agent-app/main.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    window = module.LumenWindow(str(home))
window.show()
if mode == 'crash':
    if kind == 'files':
        window.new_tab(str(home/'second'))
        window.ask_lumen('open', [], recovery={'draft':'Entwurf behalten', 'directory':str(home)})
    else:
        window.chat.composer.setPlainText('Entwurf behalten')
        window.chat.backend.session = 'ses_preserved'
        window.show_page(3); window.file_window.new_tab(str(home/'second'))
    QTimer.singleShot(1400, lambda: os.kill(os.getpid(), signal.SIGKILL))
else:
    accepted = False
    def accept_recovery():
        global accepted
        for item in app.topLevelWidgets():
            if isinstance(item, QMessageBox) and item.windowTitle() == 'Sitzung wiederherstellen':
                for button in item.buttons():
                    if button.text() == 'Wiederherstellen':
                        accepted = True; button.click(); return
    clicker = QTimer(app); clicker.timeout.connect(accept_recovery); clicker.start(50)
    def check():
        assert accepted, 'Recovery was not offered'
        state = window.recovery_state()
        assert state['chat']['draft'] == 'Entwurf behalten', state
        if kind == 'files': assert state['tabs'][-1] == str(home/'second'), state
        elif kind == 'lumen': assert state['files']['tabs'][-1] == str(home/'second'), state
        assert crash.recoveries(kind) == []
        assert window.close()
        app.quit()
    QTimer.singleShot(1200, check)
crash.attach(app, window, kind)
sys.exit(app.exec())
'''
        for kind in ('files', 'lumen'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); (root/'second').mkdir()
                script = root/'fixture.py'; script.write_text(fixture)
                env = os.environ | {'HOME':tmp, 'XDG_CONFIG_HOME':tmp+'/config', 'XDG_DATA_HOME':tmp+'/data',
                    'XDG_STATE_HOME':tmp+'/state', 'XDG_CACHE_HOME':tmp+'/cache', 'LUMEN_DATA':tmp+'/state/lumen',
                    'PYTHONPATH':str(repo/'files'), 'QT_QPA_PLATFORM':'offscreen', 'LUMEN_TEST_REPO':str(repo),
                    'DBUS_SESSION_BUS_ADDRESS':'unix:path=/nonexistent/lumen-test-bus'}
                result = subprocess.run([sys.executable, str(script), kind, 'crash'], env=env, capture_output=True, text=True, timeout=12)
                self.assertEqual(result.returncode, 137, result.stderr)
                result = subprocess.run([sys.executable, str(script), kind, 'restore'], env=env, capture_output=True, text=True, timeout=12)
                logs = '\n'.join(p.read_text() for p in (root/'state/lumen/crashes').glob('*/stderr.log'))
                self.assertEqual(result.returncode, 0, result.stderr + logs)


if __name__ == '__main__': unittest.main()
