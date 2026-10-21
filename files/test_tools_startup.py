"""Headless acceptance must not claim a real user's single-instance libraries."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tools_app

class StartupIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def pilot_environment(self):
        root=Path(self.enterContext(tempfile.TemporaryDirectory(prefix='lcp-',dir=os.environ.get('LUMEN_PILOT_SHORT_BASE'))))
        (root/'.lumen-compose-text-pilot').write_text('private-synthetic-only\n')
        (root/'.lumen-compose-text-pilot').chmod(0o600)
        profile=root/'A';profile.mkdir(mode=0o700)
        home=profile/'home';home.mkdir(mode=0o700)
        self.enterContext(patch('pathlib.Path.home',return_value=home))
        paths={'LUMEN_DATA':'lumen','LUMEN_TOOLS_DATA':'tools','XDG_CONFIG_HOME':'config',
               'XDG_DATA_HOME':'data','XDG_CACHE_HOME':'cache','XDG_STATE_HOME':'state',
               'XDG_RUNTIME_DIR':'runtime','TMPDIR':'tmp'}
        env=dict(os.environ,LUMEN_COMPOSE_TEXT_PILOT='A',LUMEN_COMPOSE_TEXT_PILOT_ROOT=str(root))
        for key,name in paths.items():
            path=profile/name;path.mkdir(mode=0o700);env[key]=str(path)
        return root,profile,env

    def test_private_compose_rejects_unfenced_home_before_qt(self):
        root,profile,env=self.pilot_environment();other=profile/'other-home';other.mkdir(mode=0o700)
        with patch.dict(os.environ,env,clear=True),patch('pathlib.Path.home',return_value=other), \
             patch('sys.argv',['tools_app.py','translate']),patch.object(tools_app,'create_app') as app, \
             patch('server_app_window.run_text_pilot',return_value=0):
            with self.assertRaises(ValueError):tools_app.main()
            app.assert_not_called()

    def test_native_activation_accepts_only_empty_request_without_library(self):
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QWidget
        root,profile,env=self.pilot_environment();window=QWidget();received=[]
        server=tools_app.listen_window(window,received.append,root=profile/'runtime')
        try:
            for request in ({'vault_flush':'a'*32},{'path':'/unopened.pdf'},{}):
                self.assertTrue(tools_app.forward_window(profile/'runtime',request,private=True))
                QTest.qWait(30)
            self.assertEqual(received,[{}])
        finally:server.close();window.deleteLater()

    def test_private_compose_gate_precedes_library_clipboard_and_legacy(self):
        root,profile,env=self.pilot_environment()
        with patch.dict(os.environ,env,clear=True),patch('sys.argv',['tools_app.py','translate']), \
             patch.object(tools_app,'create_app',return_value=self.app), \
             patch('server_app_window.run_text_pilot',return_value=0,create=True) as native, \
             patch('tools_data.Library',side_effect=AssertionError('No legacy library')) as library:
            self.assertEqual(tools_app.main(),0)
            native.assert_called_once_with(self.app,profile);library.assert_not_called()

    def test_private_notes_activation_has_explicit_keys_and_no_command_tunnel(self):
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QWidget
        root,profile,env=self.pilot_environment();window=QWidget();received=[]
        server=tools_app.listen_window(window,received.append,root=profile/'runtime',request_keys=('reference','handoff'))
        try:
            requests=({'reference':'lumen://ref/own-fixture'}, {'handoff':'own-token'},
                      {'reference':{}}, {'reference':'x','handoff':'y'}, {'path':'/unopened.pdf'}, {})
            for request in requests:
                self.assertTrue(tools_app.forward_window(profile/'runtime',request,private=True));QTest.qWait(30)
            self.assertEqual(received,[requests[0],requests[1],{}])
        finally:server.close();window.deleteLater()

    def test_private_compose_rejects_bad_roots_and_inputs_before_start(self):
        root,profile,env=self.pilot_environment()
        changes=[{key:''} for key in ('LUMEN_DATA','LUMEN_TOOLS_DATA','XDG_CONFIG_HOME','XDG_DATA_HOME',
            'XDG_CACHE_HOME','XDG_STATE_HOME','XDG_RUNTIME_DIR','TMPDIR')]
        changes += [{'LUMEN_COMPOSE_TEXT_PILOT':'C'}, {'XDG_CONFIG_HOME':str(profile/'data')},
                    {'LUMEN_COMPOSE_TEXT_PILOT_ROOT':str(Path.home())}]
        for change in changes:
            with self.subTest(change=tuple(change)),patch.dict(os.environ,{**env,**change},clear=True), \
                 patch('sys.argv',['tools_app.py','translate']),patch.object(tools_app,'create_app') as app, \
                 patch('tools_data.Library') as library:
                with self.assertRaises(ValueError):tools_app.main()
                app.assert_not_called();library.assert_not_called()
        for args in (['code'],['reader'],['translate','/unopened.pdf'],['translate','--clipboard'],
                     ['translate','--ref','lumen://unopened'],['translate','--handoff','a'*32],
                     ['translate','--section','anything']):
            with self.subTest(args=args),patch.dict(os.environ,env,clear=True), \
                 patch('sys.argv',['tools_app.py',*args]),patch.object(tools_app,'create_app') as app, \
                 patch('tools_data.Library') as library, \
                 patch.dict('sys.modules',{'code_app':SimpleNamespace(main=lambda *_:(_ for _ in ()).throw(AssertionError('No legacy Code')))}), \
                 patch('PySide6.QtWidgets.QApplication.clipboard',side_effect=AssertionError('No clipboard')):
                with self.assertRaises((ValueError,SystemExit)):tools_app.main()
                app.assert_not_called();library.assert_not_called()

    def test_private_compose_rejects_symlink_or_unmarked_profile(self):
        root,profile,env=self.pilot_environment();marker=root/'.lumen-compose-text-pilot'
        marker.unlink()
        with patch.dict(os.environ,env,clear=True),patch('sys.argv',['tools_app.py','translate']), \
             patch.object(tools_app,'create_app') as app:
            with self.assertRaises(ValueError):tools_app.main()
            app.assert_not_called()
        marker.write_text('private-synthetic-only\n');marker.chmod(0o600)
        target=profile/'cache';target.rename(profile/'real-cache');target.symlink_to(profile/'real-cache')
        with patch.dict(os.environ,env,clear=True),patch('sys.argv',['tools_app.py','translate']), \
             patch.object(tools_app,'create_app') as app:
            with self.assertRaises(ValueError):tools_app.main()
            app.assert_not_called()

    def test_incomplete_headless_environment_never_constructs_app_or_library(self):
        for platform in ('offscreen','minimal'):
            for missing in ('LUMEN_DATA','LUMEN_TOOLS_DATA'):
                with self.subTest(platform=platform,missing=missing),tempfile.TemporaryDirectory() as tmp:
                    env={**os.environ,'QT_QPA_PLATFORM':platform,'LUMEN_DATA':tmp+'/state','LUMEN_TOOLS_DATA':tmp+'/tools'};env.pop(missing)
                    with patch.dict(os.environ,env,clear=True),patch('sys.argv',['tools_app.py','workbench']),patch.object(tools_app,'create_app',side_effect=AssertionError('GUI startup reached before isolation validation')) as app,patch('tools_data.Library') as library:
                        with self.assertRaisesRegex(ValueError,'LUMEN_DATA and LUMEN_TOOLS_DATA'):tools_app.main()
                        app.assert_not_called();library.assert_not_called()

    def test_explicit_headless_roots_retain_normal_warm_activation(self):
        class Socket:
            def connectToServer(self,*args):pass
            def waitForConnected(self,*args):return True
            def write(self,*args):pass
            def waitForBytesWritten(self,*args):return True
            def disconnectFromServer(self):pass
        with tempfile.TemporaryDirectory() as tmp:
            for platform in ('offscreen','wayland'):
                env={**os.environ,'QT_QPA_PLATFORM':platform}
                if platform=='offscreen':env.update(LUMEN_DATA=tmp+'/state',LUMEN_TOOLS_DATA=tmp+'/tools')
                else:
                    env.pop('LUMEN_DATA',None);env.pop('LUMEN_TOOLS_DATA',None)
                with patch.dict(os.environ,env,clear=True),patch('sys.argv',['tools_app.py','workbench']),patch.object(tools_app,'create_app'),patch('tools_data.Library',return_value=SimpleNamespace(root=Path(tmp)/'tools/workbench')),patch.object(tools_app,'QLocalSocket',Socket):
                    self.assertEqual(tools_app.main(),0)

    def test_system_rejects_incomplete_test_profiles_before_supervision(self):
        import system_app
        for platform in ('offscreen','minimal'):
            for missing in ('LUMEN_DATA','LUMEN_TOOLS_DATA'):
                with self.subTest(platform=platform,missing=missing),tempfile.TemporaryDirectory() as tmp:
                    env={**os.environ,'QT_QPA_PLATFORM':platform,'LUMEN_DATA':tmp+'/state','LUMEN_TOOLS_DATA':tmp+'/tools'};env.pop(missing)
                    with patch.dict(os.environ,env,clear=True),patch('lumen_crash.supervise') as supervisor,patch('app.create_app',side_effect=AssertionError('GUI startup reached before isolation validation')) as app:
                        with self.assertRaisesRegex(ValueError,'LUMEN_DATA and LUMEN_TOOLS_DATA'):system_app.main([])
                        supervisor.assert_not_called();app.assert_not_called()

    def test_shared_qt_bootstrap_rejects_incomplete_test_profiles(self):
        import app
        for platform in ('offscreen','minimal'):
            for missing in ('LUMEN_DATA','LUMEN_TOOLS_DATA'):
                with self.subTest(platform=platform,missing=missing),tempfile.TemporaryDirectory() as tmp:
                    env={**os.environ,'QT_QPA_PLATFORM':platform,'LUMEN_DATA':tmp+'/state','LUMEN_TOOLS_DATA':tmp+'/tools'};env.pop(missing)
                    with patch.dict(os.environ,env,clear=True),patch.object(app,'QApplication',side_effect=AssertionError('Qt constructed before isolation validation')) as qt:
                        with self.assertRaisesRegex(ValueError,'LUMEN_DATA and LUMEN_TOOLS_DATA'):app.create_app()
                        qt.assert_not_called()

if __name__=='__main__':unittest.main()
