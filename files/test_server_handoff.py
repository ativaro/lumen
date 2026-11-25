import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
import lumen_connect_gui as gui

app = QApplication.instance() or QApplication([])

def wait(check):
    end=time.monotonic()+3
    while not check() and time.monotonic()<end:
        app.processEvents();time.sleep(.005)
    assert check()

class Backend(QObject):
    completed=Signal(bool,str)
    def __init__(self,directory,parent=None,project_config=True):
        super().__init__(parent);assert not project_config
        self.sent=None;self.stopped=False
    def send(self,text,**kwargs):
        assert self.read_only and self.background_task and kwargs['project_task']
        self.sent=text
    def shutdown(self):self.stopped=True

class HandoffTests(unittest.TestCase):
    def test_explicit_claim_result_and_lease_loss(self):
        for lose in (False,True):
            task=dict(id=str(uuid4()),prompt='Synthetic task',checkpoint='Approved checkpoint',generation=2,revision=4,state='waiting_device')
            calls=[]
            def request(config,path,body=None):
                calls.append((path,body))
                if path.endswith('/handoff'):return task
                if path.endswith('/claim'):return dict(task,revision=5,context='Selected context')
                if path.endswith('/lease') and lose:raise OSError('Offline')
                return {'ok':True}
            with tempfile.TemporaryDirectory() as root,patch.object(gui.client,'ROOT',Path(root)),patch.object(gui.client,'read_config',return_value={'server':'https://synthetic.invalid'}),patch.object(gui.client,'request',side_effect=request),patch.dict(sys.modules,{'assistant_backend':types.SimpleNamespace(OpenCodeBackend=Backend)}):
                dialog=gui.HandoffDialog(task['id'])
                wait(lambda:dialog.start_button.isEnabled())
                self.assertFalse(any(p.endswith('/claim') for p,b in calls))
                dialog.start_button.click();wait(lambda:dialog.running)
                self.assertIn('Selected context',dialog.backend.sent)
                self.assertEqual(len(list(Path(root).rglob('claim.json'))),1)
                if lose:
                    dialog.renew();wait(lambda:not dialog.running)
                    self.assertTrue(dialog.backend.stopped)
                    dialog.backend.completed.emit(True,'Stale result')
                    self.assertFalse(any(p.endswith('/complete') for p,b in calls))
                else:
                    dialog.backend.completed.emit(True,'Synthetic answer')
                    wait(lambda:any(p.endswith('/complete') for p,b in calls))
                    payload=next(b for p,b in calls if p.endswith('/complete'))
                    self.assertEqual(payload,dict(generation=2,revision=5,result='Synthetic answer'))
                wait(lambda:not dialog.worker.isRunning())
                dialog.close();app.processEvents()

class LaunchTests(unittest.TestCase):
    def test_only_fixed_app_after_consent_and_live_claim(self):
        identity=str(uuid4());calls=[]
        state={'id':identity,'app':'companion','state':'pending','revision':1}
        def request(config,path,body=None):
            calls.append(body)
            if body:state.update(body,revision=body['revision']+1)
            return dict(state)
        with tempfile.TemporaryDirectory() as root,patch.object(gui,'desktop_files',Path(root)),patch.object(gui.client,'read_config',return_value={'server':'https://synthetic.invalid'}),patch.object(gui.client,'request',side_effect=request),patch.object(gui.subprocess,'Popen') as launch:
            (Path(root)/'screen_companion.py').write_text('# synthetic')
            dialog=gui.LaunchDialog(identity);wait(lambda:dialog.open.isEnabled())
            launch.assert_not_called()
            dialog.open.click();wait(lambda:launch.called)
            self.assertEqual(launch.call_args.args[0],[sys.executable,str(Path(root)/'screen_companion.py')])
            wait(lambda:not dialog.worker.isRunning())
            self.assertEqual(state['state'],'completed')
            dialog.close();app.processEvents()


class ConnectionTests(unittest.TestCase):
    def test_connection_view_and_offline_clear(self):
        data={'name':'Test Desktop','capabilities':['tasks','backup','memory'],
              'tasks':[{'title':'Synthetic report','state':'completed','target':'server'}],
              'backup':{'last_backup':'2026-10-06','last_check':None,'last_restore':None,'backup_state':'failed','backup_error':'quota'},
              'memory':{'memory_synced_count':2,'memory_synced_at':'2026-10-06'}}
        with patch.object(gui.client,'read_config',return_value={'server':'https://synthetic.invalid'}),patch.object(gui.client,'request',return_value=data),patch.object(gui.client,'initialize_system_access'):
            dialog=gui.ConnectionDialog();wait(lambda:dialog.refresh_button.isEnabled())
            self.assertIn('Synthetic report',dialog.sections['tasks'].text())
            self.assertIn('2026-10-06',dialog.sections['backup'].text())
            self.assertIn('Speichergrenze erreicht',dialog.sections['backup'].text())
            self.assertIn('2',dialog.sections['memory'].text())
            with patch.object(gui.client,'request',side_effect=OSError('offline')):
                dialog.refresh();wait(lambda:dialog.refresh_button.isEnabled())
                self.assertTrue(all(not section.text() for section in dialog.sections.values()))
            # Delete now: a later garbage collection of the dialog crashes Qt in the next test.
            dialog.worker.wait();dialog.close();dialog.deleteLater();app.processEvents()

    def test_browser_setup_blocks_competing_connection_changes(self):
        import browser_connector, threading
        data={'name':'Test Desktop','capabilities':['desktop'], 'tasks':[], 'backup':None,'memory':None}
        release=threading.Event()
        with patch.object(gui.client,'read_config',return_value={'server':'https://synthetic.invalid'}),patch.object(gui.client,'request',return_value=data),patch.object(gui.client,'initialize_system_access'),patch.object(browser_connector,'set_access',side_effect=lambda enabled:release.wait(2)):
            dialog=gui.ConnectionDialog();wait(lambda:dialog.refresh_button.isEnabled())
            dialog.browser_access_button.click()
            self.assertFalse(dialog.system_access_button.isEnabled())
            self.assertFalse(dialog.disconnect_button.isEnabled())
            release.set();wait(lambda:dialog.refresh_button.isEnabled())
            wait(lambda:not dialog.worker.isRunning())
            dialog.close()

if __name__=='__main__':unittest.main()

class SnapshotTests(unittest.TestCase):
    def test_measurement_is_only_sent_after_native_consent(self):
        for accept in (True, False):
            identity=str(uuid4());calls=[]
            state=dict(id=identity,app='system_snapshot',state='pending',revision=1)
            sample=dict(measured='2026-10-06T08:00:00Z',cpu=17.5,cores=8,memory_total=8*1024**3,memory_used=2*1024**3,disk_total=100*1024**3,disk_used=30*1024**3,receive=1024,send=2048)
            def request(config,path,body=None):
                calls.append(body)
                if body:state.update(body,revision=body['revision']+1)
                return dict(state)
            with patch.object(gui.client,'read_config',return_value={'server':'https://synthetic.invalid'}),patch.object(gui.client,'request',side_effect=request),patch.object(gui,'system_snapshot',return_value=sample):
                dialog=gui.SnapshotDialog(identity);wait(lambda:dialog.open.isEnabled())
                self.assertIn('17.5',dialog.details.text())
                self.assertFalse(any(body for body in calls))
                (dialog.open if accept else dialog.decline).click()
                wait(lambda:state['state'] in ('completed','declined'))
                wait(lambda:not dialog.worker.isRunning())
                self.assertEqual(state.get('result'),sample if accept else None)
                dialog.close();app.processEvents()

    def test_sampling_excludes_process_and_hardware_identity(self):
        from datetime import datetime,timezone
        import system_data
        raw=dict(measured=datetime.now(timezone.utc).timestamp(),cpu=2,cores=4,
            memory={'total':20,'used':10},disk={'total':100,'used':50},network={'send':0,'receive':1},
            processes=[{'name':'private-app'}],cpuName='Private host',gpus=[{'name':'private'}])
        with patch.object(system_data.Sampler,'sample',return_value=raw):
            measured=gui.system_snapshot()
        self.assertNotIn('private',str(measured))
        self.assertEqual(set(measured),{'measured','cpu','cores','memory_total','memory_used','disk_total','disk_used','receive','send'})
