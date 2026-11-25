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
                                cwd=Path(__file__).parent, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_focus_targets(self):
        from lumen_activation import activate_process
        for pid, name in [(True, 'lumen'), (0, 'lumen'), (None, 'lumen'), (42, None),
                          (42, 'firefox'), (42, 'lumen"; throw 1;')]:
            self.assertFalse(activate_process(pid, name))

def verify_private_kde():
    if os.environ.get('LUMEN_PRIVATE_KDE_TEST') != '1':
        raise RuntimeError('Use the isolated KDE runner')
    from PySide6.QtWidgets import QApplication, QMainWindow, QDialog
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest
    from lumen_activation import activate_process, present, window_script
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
    print('LUMEN_KDE_FOCUS_OK', flush=True)


if __name__ == '__main__':
    if sys.argv[1:2] == ['--kde']: verify_private_kde()
    else: unittest.main()
