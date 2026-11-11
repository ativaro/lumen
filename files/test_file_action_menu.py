"""Run with QT_QPA_PLATFORM=offscreen LUMEN_LANGUAGE=de python -m unittest test_file_action_menu."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton, QApplication, QMenu, QToolButton, QWidget
from app import Window, create_app
from file_action_menu import ActionMenu, ActionSearch, entries
from file_spaces import SHELF
from lumen_i18n import tr,language


class FileActionMenuTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or create_app()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, LUMEN_DATA=str(self.root / 'state'),
                              LUMEN_TOOLS_DATA=str(self.root / 'tools'))
        self.env.start()
        self.addCleanup(self.env.stop)
        self.window = Window(str(self.root), QSettings(str(self.root / 'prefs.ini'), QSettings.IniFormat))
        self.addCleanup(self.window.close)
        self.folder = self.root / 'Norwegen'
        self.folder.mkdir()

    def names(self, menu):
        return {a.text().split('\t')[0] for a, _ in entries(menu)}

    def test_local_commands_all_survive_grouping_and_search(self):
        menu = self.window.build_context_menu([str(self.folder)])
        self.assertIsInstance(menu, ActionMenu)
        expected = {tr('Öffnen'), tr('Große Vorschau'), tr('Dateiversionen …'), tr('Umbenennen'), tr('Kopieren'),
            tr('Ausschneiden'), tr('Papierkorb'), tr('Pfad kopieren'), tr('In Ordner kopieren …'),
            tr('Zur Sammelfläche hinzufügen'), tr('Enthaltenden Ordner öffnen'), tr('In neuem Tab öffnen'),
            tr('Mit Lumen Drive synchronisieren …'), tr('Ordnergröße berechnen'), tr('Speicher analysieren'),
            tr('Verwendet in …'), tr('Lesefortschritt und Sicherungen …'), tr('Versionen in Lumen Vault …'),
            tr('Besprechen'), tr('Erklären'), tr('Fehler beheben'), tr('Git-Diff prüfen'),
            tr('Intelligent umbenennen …'), tr('Dateien sortieren …'), tr('Hier einfügen'), tr('Neuer Ordner'),
            tr('Letzte Lumen-Dateiaktion rückgängig …')}
        self.assertFalse(expected - self.names(menu), expected - self.names(menu))
        self.assertEqual(len(menu.quick_actions), 4)
        self.assertLessEqual(sum(not a.isSeparator() and a.text() != '' for a in menu.actions()), 8)
        dialog = ActionSearch(menu)
        dialog.search.setText('back version' if language()=='en' else 'sichern version')
        self.assertEqual(dialog.results.count(), 2)
        dialog.search.setText('absolutely missing')
        self.assertEqual(dialog.results.count(), 0)
        dialog.search.returnPressed.emit()
        self.assertIsNone(dialog.chosen)
        dialog.close()

    def test_pdf_network_shelf_and_multiselection_commands(self):
        pdf = self.root / 'article.pdf'; pdf.write_bytes(b'')
        self.assertIn(tr('Mit Lumen Reader öffnen'), self.names(self.window.build_context_menu([str(pdf)])))
        with patch.object(self.window.network, 'remote', return_value='smb://nas/photos'):
            menu = self.window.build_context_menu([str(self.folder)])
        self.assertIn(tr('Offline verfügbar machen …'), self.names(menu))
        self.window.current_location = SHELF
        self.assertIn(tr('Aus Sammelfläche entfernen (Dateien behalten)'),
                      self.names(self.window.build_context_menu([str(pdf)])))
        menu = self.window.build_context_menu([str(pdf), str(self.folder)])
        self.assertNotIn(tr('Große Vorschau'), self.names(menu))
        self.assertIn(tr('Intelligent umbenennen …'), self.names(menu))
        background = self.window.build_context_menu([])
        self.assertNotIsInstance(background, ActionMenu)
        self.assertEqual(self.names(background), {tr('Hier einfügen'), tr('Neuer Ordner'), tr('Letzte Lumen-Dateiaktion rückgängig …')})
        self.window.current_location=str(self.root)
        self.assertIn(tr('Eigenschaften …'),self.names(self.window.build_context_menu([])))

    def test_quick_click_and_keyboard_invoke_existing_callback_once(self):
        calls = []
        self.window.copy = lambda cut: calls.append(('copy', cut))
        self.window.rename = lambda: calls.append(('rename',))
        self.window.trash = lambda: calls.append(('trash',))
        menu = self.window.build_context_menu([str(self.folder)])
        menu.popup(QPoint(0, 0)); QTest.qWait(10)
        button = next(b for b in menu.findChildren(QToolButton) if b.text() == tr('Kopieren'))
        QTest.mouseClick(button, Qt.LeftButton)
        self.assertEqual(calls, [('copy', False)])
        self.assertFalse(menu.isVisible())
        menu.popup(QPoint(0, 0)); QTest.keyClick(menu, Qt.Key_F2)
        self.assertEqual(calls[-1], ('rename',))
        self.assertEqual(len(calls), 2)
        menu.popup(QPoint(0, 0)); QTest.keyClick(menu, Qt.Key_Delete)
        self.assertEqual(calls[-1], ('trash',))
        self.assertEqual(len(calls), 3)

    def test_large_selection_keeps_native_menu_and_complete_copy(self):
        from PySide6.QtWidgets import QApplication
        self.addCleanup(QApplication.clipboard().clear)
        paths = []
        for n in range(101):
            path = self.root / f'photo-{n:04}.jpg'
            path.touch()
            paths.append(str(path))
        with patch.object(self.window, 'selected_paths', return_value=paths):
            menu = self.window.build_context_menu(paths)
            self.assertTrue({tr('Kopieren'), tr('Ausschneiden'), tr('Papierkorb'), tr('Eigenschaften …'),
                             tr('In Ordner kopieren …')} <= self.names(menu))
            from interop_targets import ACTIONS
            with patch('interop_ui.reviewed_send') as send:
                action = next(a for a, _ in entries(menu) if a.text() == ACTIONS['workbench.add']['label'])
                action.trigger()
                self.assertEqual(send.call_args.args[1]['paths'], paths)
                self.assertEqual(send.call_args.args[2], 'workbench.add')
            menu.popup(QPoint(20, 20))
            QTest.qWait(10)
            self.assertTrue(menu.isVisible())
            button = next(b for b in menu.findChildren(QToolButton) if b.text() == tr('Kopieren'))
            QTest.mouseClick(button, Qt.LeftButton)
            self.assertEqual([u.toLocalFile() for u in QApplication.clipboard().mimeData().urls()], paths)
        # Large network selections must not stat the first 100 remote files just to show the menu.
        large = [str(self.root / f'photo-{n:05}.jpg') for n in range(10000)]
        with patch('interop_sources.from_paths', side_effect=AssertionError('No bulk handoff capture')):
            menu = self.window.build_context_menu(large)
            self.assertTrue(menu.quick_actions[0].isEnabled())
            menu.close()

    def test_search_uses_same_action_and_blocks_disabled_or_back_button(self):
        calls = []; parent = QWidget(); menu = ActionMenu(parent, 'Selection')
        menu.addMenu('History').addAction('Versions', lambda: calls.append('versions'))
        disabled = menu.addAction('Disabled', lambda: calls.append('disabled')); disabled.setEnabled(False)
        menu.finish(); dialog = ActionSearch(menu); dialog.show()
        dialog.search.setText('disabled'); dialog.choose(dialog.results.item(0))
        self.assertIsNone(dialog.chosen)
        dialog.search.setText('history versions')
        QTest.mouseClick(dialog.results.viewport(), Qt.BackButton)
        self.assertIsNone(dialog.chosen)
        QTest.keyClick(dialog.search, Qt.Key_Return)
        self.assertEqual(calls, [])
        dialog.chosen.trigger()
        self.assertEqual(calls, ['versions'])
        dialog = ActionSearch(menu); dialog.show(); QTest.keyClick(dialog.search, Qt.Key_Escape)
        self.assertFalse(dialog.isVisible()); self.assertIsNone(dialog.chosen)

    def test_side_mouse_buttons_never_activate_card_or_nested_menu(self):
        calls = []
        parent = QWidget(); menu = ActionMenu(parent, 'Selection')
        menu.quick('Copy', 'edit-copy', lambda: calls.append('copy'))
        child = menu.addMenu('Organize')
        command = child.addAction('Remove', lambda: calls.append('remove'))
        menu.finish(); menu.popup(QPoint(20, 20)); QTest.qWait(10)
        for button in (Qt.BackButton, Qt.ForwardButton):
            QTest.mouseClick(menu, button, pos=menu.actionGeometry(menu.actions()[-1]).center())
        self.assertEqual(calls, [])
        self.assertIsNone(self.app.activeModalWidget())
        menu.popup(QPoint(20, 20))
        QTest.keyClick(menu, Qt.Key_Tab)
        self.assertIsInstance(menu.focusWidget(), QAbstractButton)
        if not isinstance(menu.focusWidget(), QToolButton):
            QTest.keyClick(menu.focusWidget(), Qt.Key_Tab)
        self.assertIsInstance(menu.focusWidget(), QToolButton)
        QTest.keyClick(menu.focusWidget(), Qt.Key_Return)
        self.assertEqual(calls, ['copy'])
        menu.popup(QPoint(20, 20)); child.popup(QPoint(390, 20))
        for button in (Qt.BackButton, Qt.ForwardButton):
            QTest.mouseClick(child, button, pos=child.actionGeometry(command).center())
        self.assertEqual(calls, ['copy'])
        child.close(); menu.close(); parent.close()

    def test_drive_card_preserves_actions_and_multi_rename_is_disabled(self):
        drive = self.window.drive
        paths = ['lumen-drive://example/file/first', 'lumen-drive://example/file/second']
        for p in paths: drive.entries[p] = ('file', {'name': p.rsplit('/', 1)[1], 'can_write':True})
        menu = drive.build_context_menu(paths)
        self.assertFalse(menu.quick_actions[2].isEnabled())
        self.assertTrue({tr('Öffnen'), tr('Kopieren'), tr('Ausschneiden'), tr('Umbenennen'), tr('Papierkorb'),
            tr('Herunterladen …'), tr('Hier einfügen'), tr('Neuer Ordner'), tr('Offline verfügbar …'),
            tr('Synchronisation und Offline-Verfügbarkeit …'), tr('Aktualisieren')} <= self.names(menu))
        self.assertIsInstance(drive.build_context_menu([]), QMenu)
        self.assertEqual(self.names(menu),self.names(self.window.build_context_menu(paths)))
        for path in paths:drive.entries[path][1]['can_write']=False
        readonly=drive.build_context_menu(paths)
        self.assertTrue(readonly.quick_actions[0].isEnabled())
        self.assertTrue(all(not a.isEnabled() for a in readonly.quick_actions[1:]))


if __name__ == '__main__': unittest.main()
