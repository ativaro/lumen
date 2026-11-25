"""Isolated app associations: never launch a personal app or change user defaults."""
import tempfile
import unittest
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch
from file_open_with import applications, file_types, launch


def app(key, name=None):
    value = Mock()
    value.get_id.return_value = key
    value.get_display_name.return_value = name or key
    value.get_description.return_value = 'Test app'
    value.should_show.return_value = True
    value.supports_files.return_value = True
    return value


class FileOpenWithTest(unittest.TestCase):
    def test_recommendations_intersect_types_and_keep_current_default_first(self):
        a, b, hidden = app('a'), app('b'), app('hidden')
        hidden.should_show.return_value = False
        with patch('file_open_with.Gio.AppInfo.get_default_for_type', return_value=b), \
             patch('file_open_with.Gio.AppInfo.get_all_for_type', side_effect=[[a,b,hidden],[b]]):
            self.assertEqual(applications(('application/pdf','image/png')), ([b], None))
        with patch('file_open_with.Gio.AppInfo.get_default_for_type', return_value=b), \
             patch('file_open_with.Gio.AppInfo.get_all_for_type', return_value=[a,b,b,hidden]):
            self.assertEqual(applications(('application/pdf',)), ([b,a], 'b'))

    def test_launch_passes_literal_files_and_changes_no_default_implicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'Näme $(touch nope) & spaces.pdf'; path.touch()
            selected = app('selected')
            launch(selected, [str(path)])
            self.assertEqual(selected.launch.call_args.args[0][0].get_path(), str(path))
            selected.set_as_default_for_type.assert_not_called()
            selected.launch.reset_mock()
            selected.launch.return_value = False
            with self.assertRaises(ValueError):launch(selected, [str(path)], ('application/pdf',), make_default=True)
            selected.set_as_default_for_type.assert_not_called()

    def test_only_explicit_successful_known_type_updates_the_association(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'note.txt';path.touch();selected=app('selected')
            launch(selected,[str(path)],('text/plain',),make_default=True)
            selected.set_as_default_for_type.assert_called_once_with('text/plain')
            selected.launch.reset_mock()
            for types in [(),('application/octet-stream',),('text/plain','application/pdf')]:
                with self.assertRaises(ValueError):launch(selected,[str(path)],types,make_default=True)
            with self.assertRaises(ValueError):launch(selected,[tmp])
            with self.assertRaises(ValueError):launch(selected,[str(path)+'missing'])
            selected.launch.assert_not_called()

    def test_types_use_names_without_reading_or_stating_network_files(self):
        with patch.object(Path,'stat',side_effect=AssertionError('No network stat')):
            self.assertEqual(file_types(['/unmounted/file.pdf','another.PDF']),('application/pdf',))
            self.assertEqual(file_types(['unknown.veryunknownextension']),('application/octet-stream',))

    def test_real_gio_launch_and_associations_in_a_disposable_profile(self):
        with tempfile.TemporaryDirectory(prefix='lumen-open-with-') as tmp:
            root=Path(tmp);data=root/'data';config=root/'config';apps=data/'applications'
            apps.mkdir(parents=True);config.mkdir()
            record=root/'record.py'
            record.write_text('import json,os,sys\nfrom pathlib import Path\nPath(os.environ["LUMEN_OPEN_WITH_RESULT"]).write_text(json.dumps(sys.argv[1:]))\n')
            desktop=apps/'lumen-open-with-fixture.desktop'
            desktop.write_text('[Desktop Entry]\nType=Application\nName=Lumen open-with fixture\nExec=/usr/bin/python3 "'+str(record)+'" %F\nMimeType=text/plain;\n')
            subprocess.run(['update-desktop-database',str(apps)],check=True,capture_output=True)
            path=root/'Ä spaces $(touch NEVER) & literal.txt';path.touch()
            script='''import json,time,sys
from pathlib import Path
from gi.repository import Gio
from file_open_with import applications,launch
root=Path(sys.argv[1]);path=Path(sys.argv[2]);result=root/'result.json'
values,_=applications(('text/plain',))
selected=next(a for a in values if a.get_id()=='lumen-open-with-fixture.desktop')
launch(selected,[str(path)],('text/plain',))
deadline=time.monotonic()+5
while not result.exists() and time.monotonic()<deadline:time.sleep(.02)
assert json.loads(result.read_text())==[str(path)]
assert not (root/'NEVER').exists()
assert not list((root/'config').rglob('mimeapps.list'))
from PySide6.QtCore import QSettings,QTimer
from PySide6.QtWidgets import QApplication
from app import create_app,Window
from lumen_i18n import tr
qt=create_app();window=Window(str(root),QSettings(str(root/'prefs.ini'),QSettings.IniFormat))
menu=window.build_context_menu([str(path)])
submenu=next(a.menu() for a in menu.actions() if a.text()==tr('Öffnen mit'))
chosen=[]
def choose():
 dialog=QApplication.activeModalWidget()
 dialog.search.setText('Lumen open-with fixture')
 dialog.always.setChecked(True)
 chosen.append(dialog.selected_app().get_id())
 dialog.open_button.click()
QTimer.singleShot(0,choose)
QTimer.singleShot(3000,lambda:QApplication.activeModalWidget().reject() if QApplication.activeModalWidget() else None)
submenu.actions()[0].trigger()
assert chosen==[selected.get_id()]
assert Gio.AppInfo.get_default_for_type('text/plain',False).get_id()==selected.get_id()
assert list((root/'config').rglob('mimeapps.list'))
window.close();qt.processEvents()
print('Real GIO launch, literal arguments and explicit default passed')
'''
            env=dict(os.environ,HOME=tmp,XDG_CONFIG_HOME=str(config),XDG_DATA_HOME=str(data),
                     XDG_DATA_DIRS=str(root/'system-data'),XDG_CACHE_HOME=str(root/'cache'),
                     LUMEN_OPEN_WITH_RESULT=str(root/'result.json'),LUMEN_DATA=str(root/'lumen'),LUMEN_TOOLS_DATA=str(root/'tools'))
            completed=subprocess.run([sys.executable,'-c',script,tmp,str(path)],env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(completed.returncode,0,completed.stderr)


class AppChooserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.qt=QApplication.instance() or QApplication([])

    def dialog(self, types=('application/pdf',)):
        from file_open_with import AppChooser
        with patch('file_open_with.applications',return_value=([app('a','Alpha'),app('b','Beta')],'a')):
            dialog=AppChooser(None,['Document.pdf'],types)
        self.addCleanup(dialog.close)
        return dialog

    def test_search_select_keyboard_and_cancel_never_change_defaults(self):
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt
        dialog=self.dialog();dialog.show()
        self.assertFalse(dialog.always.isChecked())
        dialog.search.setText('beta')
        self.assertEqual(dialog.selected_app().get_id(),'b')
        dialog.search.setText('nothing found')
        self.assertIsNone(dialog.selected_app());self.assertFalse(dialog.open_button.isEnabled())
        QTest.keyClick(dialog.search,Qt.Key_Return)
        self.assertTrue(dialog.isVisible())
        dialog.search.setText('alpha');QTest.keyClick(dialog.search,Qt.Key_Return)
        from PySide6.QtWidgets import QDialog
        self.assertEqual(dialog.result(),QDialog.DialogCode.Accepted)
        dialog.selected_app().launch.assert_not_called()
        dialog.selected_app().set_as_default_for_type.assert_not_called()

    def test_unknown_or_mixed_types_cannot_rewrite_a_broad_default(self):
        for types in [('application/octet-stream',),('application/pdf','image/png')]:
            dialog=self.dialog(types)
            self.assertFalse(dialog.always.isEnabled());self.assertFalse(dialog.always.isChecked())


if __name__ == '__main__':unittest.main()
