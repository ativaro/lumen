"""Updater contracts with a synthetic Git remote; no real installation/network."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import updater_data as updater

DISCOVER = updater.component_definitions


class UpdaterTest(unittest.TestCase):
    def setUp(self):
        self.temp=self.enterContext(tempfile.TemporaryDirectory());self.root=Path(self.temp)
        self.enterContext(patch.dict(os.environ,{'XDG_DATA_HOME':str(self.root/'data'), 'XDG_STATE_HOME':str(self.root/'state'), 'XDG_CACHE_HOME':str(self.root/'cache')}))
        self.repo=self.root/'remote';self.repo.mkdir()
        self.git('init','-b','main');self.git('config','user.email','test@example.test');self.git('config','user.name','Test')
        (self.repo/'files').mkdir();(self.repo/'files/lumen_setup.py').write_text('# synthetic installer\n')
        self.git('add','.');self.git('commit','-m','Synthetic update')
        self.revision=self.git('rev-parse','HEAD')
        self.enterContext(patch.object(updater,'REMOTE',str(self.repo)))
        self.events=[];self.enterContext(patch.object(updater,'report',side_effect=lambda **event:self.events.append(event)))
        self.install=updater.data_root();(self.install/'files').mkdir(parents=True)
        (self.install/'files/app.py').write_text('old app');(self.install/'personal.txt').write_text('private')
        self.enterContext(patch.object(updater,'installations',return_value=[self.install]))
        self.enterContext(patch.object(updater,'component_definitions',return_value=[('engine','Engine','Test engine',True,['files/lumen_setup.py'])]))

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.repo),*args],stderr=subprocess.DEVNULL,text=True).strip()

    def test_check_does_not_install_and_dirty_or_stale_source_is_refused(self):
        with patch.object(updater,'install_bundle') as install:
            plan=updater.check();install.assert_not_called()
        self.assertEqual(plan['revision'],self.revision)
        self.assertTrue(all(row['pending'] for row in plan['rows']))
        self.assertEqual((self.install/'personal.txt').read_text(),'private')
        self.assertEqual((self.install/'files/app.py').read_text(),'old app')
        self.assertEqual(updater.read_json(updater.state_root()/'components.json'),{})
        (updater.source_root()/'files/lumen_setup.py').write_text('local change')
        with self.assertRaises(ValueError):updater.check()
        with patch.object(updater,'install_bundle') as install:
            with self.assertRaises(ValueError):updater.apply(self.revision,['lumen'])
            install.assert_not_called()

    def test_apply_uses_checked_revision_records_success_and_preserves_data(self):
        updater.check();real_run=updater.run;calls=[]
        def run(args,**kwargs):
            if args[0]=='git':return real_run(args,**kwargs)
            calls.append(args);return ''
        def install(source,revision):
            self.assertEqual(revision,self.revision)
            updater.save_json(self.install/'install.json',dict(revision=revision))
        with patch.object(updater,'run',side_effect=run),patch.object(updater,'install_bundle',side_effect=install):
            self.assertTrue(updater.apply(self.revision,['lumen','engine']))
        self.assertEqual(calls[0][-1],'engine')
        self.assertEqual((self.install/'personal.txt').read_text(),'private')
        plan=updater.check()
        self.assertFalse(any(row['pending'] for row in plan['rows'] if not row['optional']))
        self.assertTrue(self.events[-2]['message'])

    def test_failed_bundle_stops_dependencies_and_never_marks_success(self):
        updater.check()
        with patch.object(updater,'install_bundle',side_effect=RuntimeError('test failure')):
            self.assertFalse(updater.apply(self.revision,['lumen','engine']))
        self.assertFalse(self.events[-1]['success'])
        self.assertEqual(updater.read_json(updater.state_root()/'components.json'),{})
        self.assertFalse(any(e.get('component')=='engine' for e in self.events))
        with self.assertRaises(ValueError):updater.apply('f'*40,['lumen'])
        with self.assertRaises(ValueError):updater.apply(self.revision,['engine'])
        with self.assertRaises(ValueError):updater.apply(self.revision,['unknown'])

    def test_bundle_updates_system_and_user_without_resetting_desktop(self):
        source=updater.source_root();source.mkdir(parents=True)
        package=source/'packaging/arch/lumen-test-any.pkg.tar.zst';package.parent.mkdir(parents=True);package.touch()
        def result(args,**kwargs):return str(package) if args[:2]==['makepkg','--packagelist'] else ''
        with patch.object(updater,'installations',return_value=[Path('/usr/share/lumen'),self.install]),patch.object(updater,'run',side_effect=result) as run:
            updater.install_bundle(source,'f'*40)
        calls=[call.args[0] for call in run.call_args_list]
        self.assertIn(['pkexec','pacman','-U','--noconfirm',str(package)],calls)
        self.assertIn([str(source/'bin/lumen-desktop-setup'),'--refresh-decoration'],calls)
        self.assertIn(['bash',str(source/'install.sh'),'--no-mcp'],calls)
        self.assertFalse(any('--desktop' in args for args in calls))
        self.assertEqual(run.call_args.kwargs['env']['PREFIX'],str(self.install))

    def test_install_source_identity_and_credential_rejection(self):
        self.assertEqual(updater.source_url(), str(self.repo))
        url = 'https://forge.example.test/team/lumen.git'
        updater.save_json(self.install/'install.json', dict(source_url=url))
        self.assertEqual(updater.source_url(), url)
        for bad in ('https://user:secret@forge.example.test/lumen.git',
                    'http://forge.example.test/lumen.git',
                    'https://forge.example.test/lumen.git?token=test', 42):
            updater.save_json(self.install/'install.json', dict(source_url=bad))
            with self.assertRaises(ValueError): updater.source_url()
        updater.save_json(self.install/'install.json', dict(source_url=url))
        with patch.object(updater, 'installations', return_value=[self.install, self.root/'legacy']):
            with self.assertRaises(ValueError): updater.source_url()

    def test_origin_change_after_check_cannot_install(self):
        plan = updater.check()
        updater.save_json(self.install/'install.json', dict(source_url='https://forge.example.test/team/lumen.git'))
        with patch.object(updater, 'install_bundle') as install:
            with self.assertRaises(ValueError): updater.apply(plan['revision'], ['lumen'])
            install.assert_not_called()

    def test_optional_components_follow_installed_files(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(updater,'data_root',return_value=Path(tmp)),patch.object(updater.shutil,'which',return_value=None):
            root=Path(tmp)
            for rel in ('vision/env-v1/bin/python','speech/qwen-env/bin/python','vault-lab/bin/lumen-vault-lab'):
                p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.touch()
            found={row[0] for row in DISCOVER() if row[3]}
            self.assertTrue({'image-search','voice-multilingual','native-vault'}<=found)
            self.assertNotIn('voice',found);self.assertNotIn('inbox',found)

    def test_bundle_cannot_replace_a_native_topbar_with_an_older_helper(self):
        (self.install/'files/topbar_data.py').touch()
        with patch.object(updater,'run') as run:
            with self.assertRaises(ValueError):
                updater.install_bundle(self.repo,self.revision)
            run.assert_not_called()

    def test_official_channel_keeps_prior_cached_checkout_and_old_plans_separate(self):
        previous=Path(os.environ['XDG_CACHE_HOME'])/'lumen/updater/source'
        previous.mkdir(parents=True);(previous/'local-edit').write_text('keep')
        source=updater.source_root()
        updater.save_json(self.install/'install.json',dict(source_url=updater.PREVIOUS_OFFICIAL_REMOTE))
        self.assertEqual(updater.source_url(),str(self.repo))
        self.assertNotEqual(previous,source)
        updater.save_json(self.install/'install.json',dict(source_url='https://forge.example.test/team/lumen.git'))
        self.assertNotEqual(source,updater.source_root())
        self.assertEqual((previous/'local-edit').read_text(),'keep')

    def test_native_inbox_cannot_replace_installed_server_host(self):
        (self.install/'files/server_notes_app.py').touch()
        for name in ('server_notes_app','server_app_session','server_app_window','tools_app','tools_inbox'):
            (self.repo/'files'/f'{name}.py').touch()
        with patch.object(updater,'run') as run:
            with self.assertRaisesRegex(ValueError,'Server-Apps'):
                updater.install_bundle(self.repo,self.revision)
            run.assert_not_called()
            (self.repo/'files/tools_inbox.py').unlink()
            updater.install_bundle(self.repo,self.revision)
            self.assertEqual(run.call_args.args[0][:2],['bash',str(self.repo/'install.sh')])

    def test_native_topbar_bundle_checks_the_actual_helper_before_copying(self):
        (self.install/'files/topbar_data.py').touch()
        for name in ('topbar_data.py','topbar_activity.py','topbar_system.py','topbar_context.py','topbar_conversation.py'):
            (self.repo/'files'/name).touch()
        (self.repo/'native/topbar').mkdir(parents=True)
        (self.repo/'native/topbar/CMakeLists.txt').touch()
        (self.repo/'bin').mkdir();(self.repo/'bin/lumen-panel').touch()
        with patch.object(updater,'run',return_value='--snapshot') as run:
            with self.assertRaises(ValueError):
                updater.install_bundle(self.repo,self.revision)
            self.assertEqual(run.call_count,1)
        with patch.object(updater,'run',return_value='--bar-snapshot --system-topic --conversation --topbar-note') as run:
            updater.install_bundle(self.repo,self.revision)
            self.assertEqual(run.call_args_list[0].args[0], [str(self.repo/'bin/lumen-panel'),'--help'])
            self.assertEqual(run.call_args_list[1].args[0][:2], ['bash',str(self.repo/'install.sh')])

    def test_another_worker_cannot_check_or_install_during_an_update(self):
        import sys
        from PySide6.QtCore import QLockFile
        updater.state_root().mkdir(parents=True)
        lock=QLockFile(str(updater.state_root()/'worker.lock'));lock.setStaleLockTime(0)
        self.assertTrue(lock.tryLock(0))
        try:
            result=subprocess.run([sys.executable,updater.__file__,'check'],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,1)
            self.assertIn('läuft bereits',json.loads(result.stdout)['error'])
            self.assertFalse((updater.state_root()/'plan.json').exists())
        finally:lock.unlock()

    def test_system_and_flatpak_only_run_when_selected(self):
        plan=updater.check()
        plan['rows']=[row for row in plan['rows'] if row['id'] not in ('system','flatpak')]
        plan['rows'] += [dict(id=key,title=key,optional=True,pending=True) for key in ('system','flatpak')]
        updater.save_json(updater.state_root()/'plan.json',plan)
        real_run=updater.run;commands=[]
        def run(args,**kwargs):
            if args[0]=='git':return real_run(args,**kwargs)
            commands.append(args);return ''
        with patch.object(updater,'run',side_effect=run),patch.object(updater,'install_bundle') as install:
            self.assertTrue(updater.apply(self.revision,['system','flatpak']))
            install.assert_not_called()
        self.assertEqual(commands,[['pkexec','pacman','-Syu','--ignore','lumen','--noconfirm'],['flatpak','update','--noninteractive','--assumeyes']])


class UpdaterUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or create_app()

    def test_selection_apply_and_close_guard(self):
        from updater_app import UpdaterWindow
        from PySide6.QtGui import QCloseEvent
        from PySide6.QtCore import QCoreApplication,QEvent
        window=UpdaterWindow()
        try:
            plan=dict(revision='a'*40,notes='Test update',rows=[
                dict(id='lumen',title='Lumen',detail='Apps',pending=True,optional=False),
                dict(id='engine',title='Engine',detail='Current',pending=False,optional=False),
                dict(id='system',title='Linux',detail='Optional',pending=True,optional=True)])
            window.set_plan(plan)
            self.assertTrue(window.rows['lumen'][0].isChecked())
            self.assertFalse(window.rows['system'][0].isChecked())
            self.assertFalse(window.rows['engine'][0].isEnabled())
            with patch.object(window,'start') as start:
                window.install_button.click()
                self.assertEqual(start.call_args.args,('apply',['--revision','a'*40,'--components','lumen']))
            window.running=True;event=QCloseEvent();window.closeEvent(event)
            self.assertFalse(event.isAccepted())
            window.running=False;window.closeEvent(event);self.assertTrue(event.isAccepted())
        finally:
            window.running=False;window.close();window.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
