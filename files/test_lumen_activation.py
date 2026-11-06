"""Real relaunches use a private D-Bus, home, and runtime; never user windows."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ActivationTest(unittest.TestCase):
    def test_startup_queue_and_invalid_requests(self):
        code = '''
from PySide6.QtCore import QCoreApplication
from lumen_activation import SingleWindow
app = QCoreApplication([])
endpoint = SingleWindow('org.lumen.Test')
assert not endpoint.running
for value in ('[1]', '{', 'x'*65537): assert not endpoint.Open(value)
for _ in range(32): assert endpoint.Open('{"location":"draft"}')
assert not endpoint.Open('{}')
received = []
endpoint.bind(received.append)
app.processEvents()
assert received == [{'location':'draft'}]*32
assert endpoint.Open('{}') and received[-1] == {}
'''
        result = subprocess.run(['dbus-run-session', '--', sys.executable, '-c', code],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_focus_targets(self):
        from lumen_activation import activate_process
        for pid, name in [(True, 'lumen'), (0, 'lumen'), (None, 'lumen'), (42, None),
                          (42, 'firefox'), (42, 'lumen"; throw 1;')]:
            self.assertFalse(activate_process(pid, name))

    def test_real_app_relaunches(self):
        for name in ('files', 'updater', 'companion', 'household', 'meetings'):
            with self.subTest(app=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); (root/'runtime').mkdir(mode=0o700)
                config = root/'config/Lumen'; config.mkdir(parents=True)
                (config/'Assistant.conf').write_text('[General]\ncrashDetection=false\n')
                env = dict(os.environ, HOME=tmp, XDG_RUNTIME_DIR=str(root/'runtime'),
                           XDG_CONFIG_HOME=str(root/'config'), XDG_DATA_HOME=str(root/'data'),
                           XDG_CACHE_HOME=str(root/'cache'), XDG_STATE_HOME=str(root/'state'),
                           LUMEN_DATA=str(root/'state'), LUMEN_TOOLS_DATA=str(root/'tools'),
                           QT_QPA_PLATFORM='offscreen', LUMEN_OPENCODE_BIN='/nonexistent/test-engine')
                result = subprocess.run(['dbus-run-session', '--', sys.executable, __file__, '--worker', name],
                                        env=env, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)




def verify_private_kde():
    if os.environ.get('LUMEN_PRIVATE_KDE_TEST') != '1':
        raise RuntimeError('Use the isolated KDE runner')
    from PySide6.QtWidgets import QApplication, QMainWindow, QDialog
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest
    from lumen_activation import activate_process, present
    from lumen_modes import window_script
    from types import SimpleNamespace
    app = QApplication([]); app.setApplicationName('lumen-test-preview'); app.setDesktopFileName('lumen-test')
    window = QMainWindow(); window.setWindowTitle('Lumen focus test')
    window.showMaximized(); QTest.qWait(200)
    window.showMinimized(); QTest.qWait(500)
    with tempfile.TemporaryDirectory() as tmp:
        assert window_script(SimpleNamespace(directory=Path(tmp)),
                             'return workspace.windowList().find(w => w.caption === \"Lumen focus test\").minimized;')
    present(window); QTest.qWait(300)
    assert not window.isMinimized() and window.isMaximized() and window.isActiveWindow()
    dialog = QDialog(window); dialog.setModal(True); dialog.setWindowTitle('Lumen open dialog'); dialog.show()
    QTest.qWait(150)
    assert activate_process(os.getpid(), 'lumen-test')
    QTest.qWait(150); assert dialog.isActiveWindow()
    dialog.close()
    with tempfile.TemporaryDirectory() as tmp:
        store = SimpleNamespace(directory=Path(tmp))
        window_script(store, '''workspace.createDesktop(workspace.desktops.length, "Test");
            workspace.activeWindow.desktops = [workspace.desktops[workspace.desktops.length-1]]; return true;''')
        assert activate_process(os.getpid(), 'lumen-test')
        QTest.qWait(150)
        assert window_script(store, 'return workspace.activeWindow.desktops.includes(workspace.currentDesktop);')
    window.close()
    quick = QQuickWindow(); quick.setTitle('Lumen QML window'); quick.resize(600, 400); quick.show(); QTest.qWait(300)
    quick.showMinimized(); QTest.qWait(100); present(quick); QTest.qWait(250)
    assert quick.isActive(); quick.close()
    binary = Path(__file__).resolve().parents[1]/'native/vault-ui/build/lumen-vault-lab'
    assert binary.exists(), 'Build the native Vault target first'
    with tempfile.TemporaryDirectory() as tmp:
        store = SimpleNamespace(directory=Path(tmp))
        with open(Path(tmp)/'vault.log', 'w') as output:
            native = subprocess.Popen([str(binary), '--laboratory-only'], stdout=output, stderr=output)
            try:
                target = f'workspace.windowList().find(w => Number(w.pid) === {native.pid} && w.normalWindow)'
                for _ in range(40):
                    QTest.qWait(150)
                    assert native.poll() is None
                    if window_script(store, f'return Boolean({target});'): break
                assert window_script(store, f'const w = {target}; w.minimized = true; return w.minimized;')
                second = subprocess.run([str(binary), '--laboratory-only'], capture_output=True, timeout=5)
                assert second.returncode == 0, second.stderr.decode()
                for _ in range(30):
                    QTest.qWait(150)
                    if window_script(store, f'return workspace.activeWindow === {target} && !{target}.minimized;'): break
                else: raise AssertionError('Native Vault relaunch did not activate its existing window')
                assert native.poll() is None
            finally:
                native.terminate(); native.wait(timeout=5)
    print('LUMEN_KDE_FOCUS_OK', flush=True)


if __name__ == '__main__':
    if sys.argv[1:2] == ['--kde']: verify_private_kde()
    elif sys.argv[1:2] in (['--worker'], ['--client']):
        raise SystemExit(worker(sys.argv[2], sys.argv[1] == '--client'))
    else: unittest.main()
