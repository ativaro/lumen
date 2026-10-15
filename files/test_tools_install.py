import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('install_tools', REPO/'install-tools.py')
installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)


class ToolsInstallTest(unittest.TestCase):
    def test_install_is_repeatable_preserves_data_and_has_native_launchers(self):
        from gi.repository import Gio, GLib
        with tempfile.TemporaryDirectory(prefix='lumen install ') as tmp:
            data, binaries = Path(tmp)/'data', Path(tmp)/'bin'
            library = data/'lumen-tools/workbench/notes.txt'
            library.parent.mkdir(parents=True); library.write_text('Meine Notiz')
            runtime = installer.install(REPO,data,binaries)
            self.assertEqual(installer.install(REPO,data,binaries),runtime)
            self.assertEqual(library.read_text(),'Meine Notiz')
            self.assertEqual((runtime/'tools_app.py').read_bytes(),(REPO/'files/tools_app.py').read_bytes())
            for catalog in (REPO/'files/translations/en').glob('*.json'):
                self.assertEqual((runtime/'translations/en'/catalog.name).read_bytes(),catalog.read_bytes())
            handler=data/'applications/lumen-open.desktop'
            entry=Gio.DesktopAppInfo.new_from_filename(str(handler))
            self.assertEqual(GLib.shell_parse_argv(entry.get_commandline())[1],[str(binaries/'lumen-open'),'%u'])
            self.assertIn('x-scheme-handler/lumen',entry.get_supported_types())
            self.assertTrue((runtime/'interop_open.py').exists())
            for tool in installer.TOOLS:
                name='lumen-'+tool; binary=binaries/name
                desktop=data/'applications'/f'{name}.desktop'
                entry=Gio.DesktopAppInfo.new_from_filename(str(desktop))
                self.assertIsNotNone(entry); self.assertEqual(GLib.shell_parse_argv(entry.get_commandline())[1], [str(binary)]+(['%f'] if tool in ('reader','translate') else []))
                subprocess.run(['desktop-file-validate',str(desktop)],check=True)
                subprocess.run(['/bin/sh','-n',str(binary)],check=True)
                self.assertIn(f'exec /usr/bin/{name}',binary.read_text())
            # Exercise both launcher routes without touching /usr/bin or starting a GUI.
            launcher=(binaries/'lumen-workbench').read_text()
            packaged=Path(tmp)/'package';packaged.write_text('#!/bin/sh\nprintf packaged');packaged.chmod(0o755)
            script=launcher.replace('/usr/bin/lumen-workbench',str(packaged).replace(' ','\\ '))
            self.assertEqual(subprocess.check_output(['/bin/sh','-c',script]),b'packaged')
            packaged.unlink()
            (runtime/'tools_app.py').write_text('print("fallback")')
            self.assertEqual(subprocess.check_output(['/bin/sh','-c',script]),b'fallback\n')

    def test_custom_starters_stop_installation_before_any_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,binaries=Path(tmp)/'data',Path(tmp)/'bin';binaries.mkdir()
            existing=binaries/'lumen-radio';existing.write_text('custom')
            with self.assertRaises(ValueError): installer.install(REPO,data,binaries)
            self.assertEqual(existing.read_text(),'custom');self.assertFalse(data.exists())

    def test_assets_are_complete_and_changes_create_a_new_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); repo = root/'source'; (repo/'files').mkdir(parents=True)
            (repo/'files/tools_app.py').write_text('print("synthetic")')
            for name in ('bin', 'data', 'icons'): (repo/name).symlink_to(REPO/name)
            assets = []
            for name in ('translations', 'qml', 'fonts', 'notes_icons', 'project_fonts', 'memory-runtime'):
                asset = repo/'files'/name/'nested/asset.dat'
                asset.parent.mkdir(parents=True); asset.write_bytes(name.encode()); assets.append(asset)
            first = installer.install(repo, root/'data', root/'bin')
            for asset in assets:
                self.assertEqual((first/asset.relative_to(repo/'files')).read_bytes(), asset.read_bytes())
            assets[-1].write_bytes(b'updated runtime notice')
            second = installer.install(repo, root/'data', root/'bin')
            self.assertNotEqual(first, second)
            self.assertEqual((first/'memory-runtime/nested/asset.dat').read_bytes(), b'memory-runtime')
            self.assertEqual((second/'memory-runtime/nested/asset.dat').read_bytes(), assets[-1].read_bytes())


if __name__=='__main__': unittest.main()
