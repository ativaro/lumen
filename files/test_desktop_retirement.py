"""Removed native apps cannot return through launchers, imports or upgrades."""
import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]


class DesktopRetirementTest(unittest.TestCase):
    def test_all_retired_product_files_are_absent_and_no_live_imports_refer_to_them(self):
        manifest=REPO/'packaging/retired-desktop-files.txt'
        names=[name for name in manifest.read_text().splitlines() if name and not name.startswith('#')]
        retired={Path(name).stem for name in names if name.endswith('.py')}
        for name in names:self.assertFalse((REPO/name).exists(),name)
        for path in (REPO/'files').glob('*.py'):
            if path.name.startswith('test_'):continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.Import):self.assertFalse({a.name.split('.')[0] for a in node.names}&retired,str(path))
                if isinstance(node,ast.ImportFrom) and node.module:self.assertNotIn(node.module.split('.')[0],retired,str(path))

    def test_shared_starters_never_construct_a_retired_local_library(self):
        import tools_app
        variants=[(['workbench'],'projects'),(['workbench','--section','automations'],'code'),
                  (['meetings'],'audio'),(['radio'],'audio'),(['inbox'],'inbox'),(['vault'],'vault')]
        for argv,kind in variants:
            with self.subTest(argv=argv),patch('sys.argv',['tools_app.py',*argv]),patch.object(tools_app,'create_app',return_value='own-app'), \
                    patch('tools_data.Library',side_effect=AssertionError('Old library opened')),patch('server_notes_app.run',return_value=0) as run:
                self.assertEqual(tools_app.main(),0)
                self.assertEqual(run.call_args.kwargs['kind'],kind)

    def test_old_household_shortcut_still_opens_the_native_household(self):
        import tools_app
        with patch('sys.argv',['tools_app.py','workbench','--section','household']),patch('lumen_detail_routes.launch') as launch:
            self.assertEqual(tools_app.main(),0);launch.assert_called_once_with('lumen',['--page','household'])

    def installer(self):
        spec=importlib.util.spec_from_file_location('retire_desktop',REPO/'packaging/retire-desktop.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

    def test_upgrade_removes_known_code_and_bytecode_and_preserves_data_and_custom_assets(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);files=root/'files';(files/'__pycache__').mkdir(parents=True)
            for name in ('tools_workbench.py','test_retired.py','__pycache__/tools_workbench.cpython-314.pyc'):(files/name).write_bytes(b'old code')
            (files/'notes_web').mkdir();(files/'notes_web/custom.txt').write_bytes(b'custom untouched')
            data=root/'tools/user.sqlite';data.parent.mkdir();data.write_bytes(b'private data')
            removed=self.installer().retire(root)
            self.assertEqual(len(removed),3);self.assertEqual(data.read_bytes(),b'private data')
            self.assertEqual((files/'notes_web/custom.txt').read_bytes(),b'custom untouched')
            self.assertEqual(self.installer().retire(root),[])

    def test_cleanup_preflights_symlinks_before_any_removal(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);files=root/'files';files.mkdir();target=root/'untouched';target.write_bytes(b'private')
            (files/'tools_workbench.py').write_bytes(b'old code');(files/'tools_inbox.py').symlink_to(target)
            with self.assertRaises(ValueError):self.installer().retire(root)
            self.assertEqual(target.read_bytes(),b'private');self.assertTrue((files/'tools_workbench.py').exists())

    def test_local_inbox_data_helpers_do_not_include_mail_or_calendar_clients(self):
        import inbox_data
        for name in ('connect_mail','sync_mail','send_draft','calendar_operation','calendar_client','calendar_python'):
            self.assertFalse(hasattr(inbox_data,name))
        with tempfile.TemporaryDirectory() as root:
            library=inbox_data.store(root);self.assertEqual(inbox_data.draft_attachments(library,[]),[])
            with self.assertRaises(ValueError):inbox_data.draft_attachments(library,[dict(asset='../outside',name='unsafe')])

    def test_native_user_notes_cannot_be_reopened_by_direct_constructor(self):
        from tools_wissen import Wissen
        with patch('tools_ui.ToolWindow.__init__',side_effect=AssertionError('No widget or library may be constructed')):
            with self.assertRaisesRegex(ValueError,'Lumen Server'):Wissen(memory_only=False)

    def test_native_device_page_has_no_workspace_or_local_project_view(self):
        import server_workspace
        self.assertTrue(hasattr(server_workspace,'ServerDevices'))
        self.assertFalse(hasattr(server_workspace,'ServerWorkspace'))
