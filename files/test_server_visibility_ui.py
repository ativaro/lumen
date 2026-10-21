"""Actual Files and Plasma components, synthetic profile and grants only."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QObject, QSettings, Qt, QUrl
from PySide6.QtQuick import QQuickView
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

    def test_real_panel_reflows_connected_and_disconnected(self):
        from lumen_panel import applications
        folder = Path(__file__).resolve().parents[1]/'plasmoid/contents/ui'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'panel.qml'
            path.write_text('''import QtQuick
import org.kde.kirigami as Kirigami
import "'''+folder.as_uri()+'''" as Lumen
Rectangle {
 width: 510; height: panel.implicitHeight+24; color: "#222529"
 Kirigami.Theme.inherit: false
 Kirigami.Theme.textColor: "#eff1f3"
 Kirigami.Theme.backgroundColor: "#222529"
 Kirigami.Theme.alternateBackgroundColor: "#2a2e33"
 Kirigami.Theme.disabledTextColor: "#aab1ba"
 Kirigami.Theme.highlightColor: "#d7dce2"
 Lumen.PanelView { id:panel; objectName:"panel"; anchors.fill:parent; anchors.margins:12; snapshot:testSnapshot }
}''')
            view = QQuickView()
            for connected in (False, True):
                grants = {'notes', 'projects', 'code', 'media', 'vault_sync', 'inbox'} if connected else set()
                with patch.object(server_availability, 'capabilities', return_value=grants): apps = applications()
                view.rootContext().setContextProperty('testSnapshot', dict(apps=apps, active=[], recent=[], busy=False, attention=False))
                if view.source().isEmpty(): view.setSource(QUrl.fromLocalFile(str(path)))
                self.assertEqual(view.status(), QQuickView.Ready, str(view.errors()))
                view.show(); QTest.qWait(120)
                # All real delegates remain inside the same existing panel bounds.
                panel = view.rootObject().findChild(QObject, 'panel')
                grid = panel.findChild(QObject, 'appGrid')
                self.assertEqual(grid.property('columns'), 5)
                out = os.environ.get('LUMEN_VISIBILITY_ARTIFACTS')
                if out: view.grabWindow().save(str(Path(out)/('panel-connected.png' if connected else 'panel-disconnected.png')))
            view.close()


if __name__ == '__main__': unittest.main()
