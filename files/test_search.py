"""Native unified search: real file results, keyboard selection and in-place replies."""
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication
from app import create_app
from lumen_search import SearchPalette


class SearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or create_app()

    def test_resident_search_tracks_external_themes_and_refreshes_on_activation(self):
        # Separate process gives create_app its own real QSettings/file watcher.
        with tempfile.TemporaryDirectory() as tmp:
            script = '''
import subprocess, sys
from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QPalette
from PyQt5.QtTest import QTest
from app import create_app
from appearance import COLORS, DESIGNS
from lumen_search import SearchPalette
app = create_app(); window = SearchPalette(applications=[]); window.show()
window.conversation = True
window.chat.backend.session = 'preserved-session'
window.query.setPlainText('Entwurf behalten')
def save(name):
    subprocess.run([sys.executable, '-c', "from PyQt5.QtCore import QSettings; s=QSettings('Lumen','Assistant'); s.setValue('appearance'," + repr(name) + "); s.sync()"], check=True)
try:
    for _, name in DESIGNS:
        save(name)
        for _ in range(50):
            QTest.qWait(20)
            if app.property('lumenDesign') == name: break
        assert app.property('lumenDesign') == name, name
        assert window.query.palette().color(QPalette.Text).name() == COLORS[name][3], name
    app.theme_watcher.blockSignals(True)
    window.hide(); save('atelier'); window.present()
    assert app.property('lumenDesign') == 'atelier'
    assert window.query.palette().color(QPalette.Text).name() == COLORS['atelier'][3]
    assert window.chat.backend.session == 'preserved-session'
    assert window.query.toPlainText() == 'Entwurf behalten'
finally:
    window.shutdown(); window.hide()
'''
            result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).parent,
                                    env=os.environ | {'XDG_CONFIG_HOME':tmp+'/config', 'LUMEN_DATA':tmp+'/state', 'QT_QPA_PLATFORM':'offscreen'},
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_files_selection_and_conversation_share_one_composer(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp + '/state'}):
            first = Path(tmp) / 'Reise A.txt'; first.write_text('a')
            second = Path(tmp) / 'Reise B.txt'; second.write_text('b')
            window = SearchPalette(tmp, applications=[('Reiseplaner', 'example.desktop')])
            window.show(); QTest.qWait(20)
            try:
                with patch.object(window.chat.backend, 'send') as send:
                    window.query.setPlainText('Reise')
                    deadline = time.monotonic() + 5
                    while (window.debounce.isActive() or window.scan_jobs) and time.monotonic() < deadline: QTest.qWait(10)
                    self.assertFalse(window.scan_jobs)
                    self.assertEqual(window.results.count(), 4)
                    send.assert_not_called()
                    # Move past the app and open the selected file, not the first result.
                    window.query.setFocus(); QTest.keyClick(window.query, Qt.Key_Down)
                    target = window.results.currentItem().data(Qt.UserRole)
                    self.assertEqual(target[0], 'file')
                    with patch('lumen_search.QDesktopServices.openUrl', return_value=True) as opened:
                        QTest.keyClick(window.query, Qt.Key_Return)
                        self.assertEqual(opened.call_args.args[0].toLocalFile(), target[1])
                    send.assert_not_called()
                    window.show(); window.query.setFocus()
                    # Immediate Return must use the freshly typed question, not a stale file.
                    window.query.setPlainText('Wie ordne ich meine Bilder?')
                    QTest.keyClick(window.query, Qt.Key_Return)
                    self.assertTrue(window.conversation)
                    self.assertIs(window.stack.currentWidget(), window.chat)
                    self.assertEqual(send.call_args.args[0], 'Wie ordne ich meine Bilder?')
                    window.chat.backend.session = 'same-session'
                    window.chat.backend.messagesChanged.emit([{'info': {'role': 'assistant'}, 'parts': [{'type': 'text', 'text': 'Nach Datum sortieren.'}]}])
                    self.assertIn('Nach Datum sortieren.', window.chat.transcript.toPlainText())
                    window.chat.backend.busyChanged.emit(True)
                    self.assertTrue(window.query.isReadOnly()); self.assertFalse(window.reset_button.isEnabled())
                    window.chat.backend.busyChanged.emit(False)
                    window.query.setPlainText('Und nach Ort?')
                    QTest.keyClick(window.query, Qt.Key_Return, Qt.ControlModifier)
                    self.assertEqual(send.call_count, 2)
                    self.assertEqual(window.chat.backend.session, 'same-session')
                    self.assertEqual(send.call_args.args[0], 'Und nach Ort?')
                    window.reset(); self.assertFalse(window.conversation)
                    self.assertIs(window.stack.currentWidget(), window.results)
                    window.query.setPlainText('Reise')
                    QTest.keyClick(window.query, Qt.Key_Return, Qt.ControlModifier)
                    self.assertTrue(window.conversation); self.assertEqual(send.call_count, 3)
            finally:
                window.shutdown(); window.hide(); window.deleteLater(); QTest.qWait(20)


if __name__ == '__main__': unittest.main()
