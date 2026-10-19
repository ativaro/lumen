"""Actual notification-to-Files IPC on a private bus and synthetic profile."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class FollowupActivationTest(unittest.TestCase):
    def run_receiver(self, mode):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'runtime').mkdir(mode=0o700)
            environment = dict(os.environ, HOME=temporary, XDG_RUNTIME_DIR=str(root / 'runtime'),
                               XDG_CONFIG_HOME=str(root / 'config'), XDG_DATA_HOME=str(root / 'data'),
                               XDG_STATE_HOME=str(root / 'xdg-state'), XDG_CACHE_HOME=str(root / 'cache'),
                               LUMEN_DATA=str(root / 'state'), LUMEN_TOOLS_DATA=str(root / 'tools'),
                               QT_QPA_PLATFORM='offscreen', LUMEN_LANGUAGE='de')
            result = subprocess.run(['dbus-run-session', '--', sys.executable, __file__, '--receiver', mode],
                                    env=environment, capture_output=True, text=True, timeout=12)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_new_old_and_starting_files_receivers(self):
        for mode in ('new', 'old', 'starting'):
            with self.subTest(receiver=mode):
                self.run_receiver(mode)

    def test_cold_unknown_transfer_reports_visible_window_error(self):
        self.run_receiver('cold-unknown')


def receiver(mode):
    if mode == 'cold-unknown':
        return cold_unknown()
    from PySide6.QtCore import QProcess, QSettings, QTimer
    from app import Window, activate_files, create_app
    from files_activation import FilesActivation
    from lumen_activation import SingleWindow
    from lumen_store import Store
    import lumen_notifications as notifications
    import lumen_transfers as transfers
    from unittest.mock import patch
    application = create_app('graphite')
    root = Path.home()
    source = root / 'synthetic.iso'
    source.write_bytes(b'only synthetic data')
    target = root / 'target'
    target.mkdir()
    store = Store()
    value = transfers.create(store, 'copy', [str(source)], str(target))
    transfers.update(store, value['id'], status='failed')
    window = Window(str(target), QSettings(str(root / 'settings.ini'), QSettings.IniFormat))
    window.show()
    window.transfer_panel.hide()
    endpoint = SingleWindow('org.lumen.Files') if mode == 'old' else FilesActivation('org.lumen.Files')
    assert not endpoint.running
    generic = []
    endpoint.bind(generic.append)
    if mode == 'new':
        endpoint.bind_transfer(lambda identity: activate_files(window, {'transfer': identity}))
    card = notifications.publish('Lumen Files', 'synthetic', 'Synthetic ready', 'Synthetic only',
                                 target='transfer:' + value['id'], popup=False)
    child = QProcess()
    deadline = QTimer()
    deadline.setSingleShot(True)

    def done(code):
        def verify():
            try:
                assert code == 0, bytes(child.readAllStandardError()).decode()
                assert generic == ([{'location': 'synthetic-only'}] if mode == 'new' else []), generic
                assert notifications.snapshot()['unread'] == (0 if mode == 'new' else 1)
                if mode == 'new':
                    assert window.transfer_panel.isVisible()
                    assert window.transfer_panel.selected()['id'] == value['id']
                else:
                    assert not window.transfer_panel.isVisible()
                assert not (target / source.name).exists()
                deadline.stop()
                application.exit(0)
            except Exception as error:
                print(repr(error), flush=True)
                application.exit(1)
        QTimer.singleShot(30, verify)

    child.finished.connect(done)
    deadline.timeout.connect(lambda: (child.kill(), application.exit(2)))
    child.start(sys.executable, [__file__, '--client', card, mode])
    deadline.start(8000)
    with patch.object(transfers, 'start', side_effect=AssertionError('IPC must not copy')):
        result = application.exec()
    if child.state() != QProcess.NotRunning:
        child.kill()
        child.waitForFinished(1000)
    return result


def cold_unknown():
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    import app
    from unittest.mock import patch
    original = app.Window
    errors = []

    class Probe(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.error = errors.append
            QTimer.singleShot(100, self.verify)

        def verify(self):
            okay = errors == ['Transfer nicht gefunden.'] and self.isVisible()
            print('cold-unknown-visible-error', okay, errors, flush=True)
            QApplication.exit(0 if okay else 1)

    with patch.object(app, 'Window', Probe):
        return app.main(['--transfer', 'f' * 32])


if __name__ == '__main__':
    if sys.argv[1:2] == ['--receiver']:
        raise SystemExit(receiver(sys.argv[2]))
    if sys.argv[1:2] == ['--client']:
        import lumen_notifications as notifications
        try:
            notifications.change(sys.argv[2], 'open')
        except ValueError as error:
            assert sys.argv[3] != 'new' and 'schließen' in str(error)
        else:
            assert sys.argv[3] == 'new'
            from lumen_activation import SingleWindow
            endpoint = SingleWindow('org.lumen.Files')
            assert endpoint.running and endpoint.forward({'location': 'synthetic-only'}) == 0
    else:
        unittest.main()
