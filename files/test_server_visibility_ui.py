"""Actual Files and Plasma components, synthetic profile and grants only."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from app import Window, create_app
import server_availability


class ServerVisibilityUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = create_app()

    def wait(self, check):
        for _ in range(400):
            QTest.qWait(10)
            if check(): return
        self.fail('Visibility update timed out')

    def test_live_files_sidebar_updates_without_touching_tabs(self):
        grants = set()
        with tempfile.TemporaryDirectory() as tmp, patch.object(server_availability, 'capabilities', side_effect=lambda: frozenset(grants)):
            window = Window(tmp, QSettings(tmp+'/files.ini', QSettings.IniFormat))
            window.resize(1380, 860); window.show()
            self.wait(lambda: window.server_job is None)
            window.server_timer.stop()
            original = window.current_location
            def count():
                return sum(window.places.item(i).data(Qt.UserRole) == 'lumen-drive://' for i in range(window.places.count()))
            self.assertEqual(count(), 0)
            for connected in (True, False, True):
                grants.clear()
                if connected: grants.add('drive')
                window.refresh_server(); self.wait(lambda: window.server_job is None)
                self.assertEqual(count(), int(connected))
                self.assertEqual(window.current_location, original)
                out = os.environ.get('LUMEN_VISIBILITY_ARTIFACTS')
                if out: window.grab().save(str(Path(out)/('files-connected.png' if connected else 'files-disconnected.png')))
            window.close()
            self.assertTrue(window._closed)


if __name__ == '__main__': unittest.main()
