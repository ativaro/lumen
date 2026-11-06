"""Private actual Qt/HTTPS/actor fixture; no external OS opener or personal profile."""
import hashlib
import json
import os
import ssl
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from PySide6.QtCore import QFile, QIODevice, QObject, QThread, QTimer, QUrl, Qt, Slot, QCoreApplication, QEvent
from PySide6.QtGui import QDesktopServices
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox
from shiboken6 import isValid
import lumen_connect_gui as gui

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)
BASE = 'https://127.0.0.1:18479'
CONTROL = Path('/scratch/control')
OUTPUT = Path('/output')/os.environ['LUMEN_GUI_PROFILE']
OUTPUT.mkdir(exist_ok=True)


def wait(check,seconds=5):
    deadline = time.monotonic()+seconds
    while not check() and time.monotonic()<deadline:
        app.processEvents()
        time.sleep(.005)
    if not check():
        raise AssertionError('Private Qt boundary did not finish')
    app.processEvents()


class FileReceiver(QObject):
    def __init__(self,test):
        super().__init__()
        self.test = test
        self.records = []
        self.errors = []
        self.reenter = None

    @Slot(QUrl)
    def receive(self,url):
        try:
            path = Path(url.toLocalFile())
            file = QFile(str(path))
            if not file.open(QIODevice.ReadOnly):
                raise OSError('Private Qt file could not be opened')
            try:
                data = bytes(file.readAll())
            finally:
                file.close()
            self.records.append(dict(path=str(path),size=len(data),sha256=hashlib.sha256(data).hexdigest(),
                                     gui_thread=QThread.currentThread()==app.thread()))
            if self.reenter:
                self.reenter()
        except Exception as error:
            self.errors.append(type(error).__name__)


class ArtifactGuiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        profile=Path.home()
        credentials=json.loads((profile/'credentials.json').read_text())
        cls.owner=httpx.Client(base_url=BASE,verify=ssl.create_default_context(cafile='/profile/keys/fixture-ca.pem'),trust_env=False,timeout=8,headers={'Origin':BASE})
        cls.addClassCleanup(cls.owner.close)
        response=cls.owner.post('/api/auth/login',json={'email':credentials['email'],'password':credentials['password']})
        if response.status_code!=200:
            raise AssertionError('Owned GUI login failed: '+str(response.status_code))
        hidden=json.loads(Path('/profile/secrets.json').read_text())
        hidden += [response.json()['csrf'],*list(cls.owner.cookies.values())]
        Path('/profile/secrets.json').write_text(json.dumps(hidden))
        cls.owner.headers['X-Lumen-CSRF']=response.json()['csrf']

    def setUp(self):
        self.profile = Path.home()
        self.credentials = json.loads((self.profile/'credentials.json').read_text())
        self.ca = self.profile/'trust.pem'
        self.ca.write_bytes(Path('/profile/keys/fixture-ca.pem').read_bytes())
        hidden = json.loads(Path('/profile/secrets.json').read_text())
        response = self.owner.post('/api/devices',json={'name':'Lumen isolated Qt receiver','capabilities':['desktop','artifacts']})
        self.assertEqual(response.status_code,200)
        device = response.json()
        self.addCleanup(lambda:self.owner.delete('/api/devices/'+device['id']))
        hidden.append(device['token']);Path('/profile/secrets.json').write_text(json.dumps(hidden))
        self.config = dict(server=BASE,device_id=device['id'],token=device['token'],ca_file=str(self.ca))
        gui.client.ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.assertEqual(gui.client.ROOT,self.profile/'config/lumen-server')
        gui.client.save_private(gui.client.CONFIG,json.dumps(self.config))
        CONTROL.mkdir(exist_ok=True,mode=0o700)
        for file in CONTROL.iterdir():
            file.unlink()
        self.dialogs = []
        self.calls = []
        self.responses = []
        self.qt_errors = []
        self.lose_claim = self.lose_receipt = False
        self.enterContext(patch.object(sys,'excepthook',lambda kind,value,tb:self.qt_errors.append(kind.__name__)))
        original = gui.client.request
        def request(config,path,body=None,**kwargs):
            state = body.get('state') if body else None
            self.calls.append((path,state))
            result = original(config,path,body,**kwargs)
            if state=='claimed' and self.lose_claim:
                self.lose_claim = False
                raise OSError('Owned lost claim acknowledgment after actual server decision')
            if state=='completed' and self.lose_receipt:
                self.lose_receipt = False
                raise OSError('Owned lost terminal acknowledgment after actual server decision')
            return result
        self.enterContext(patch.object(gui.client,'request',request))
        original_open = gui.client.urllib.request.OpenerDirector.open
        def opened(opener,request,*args,**kwargs):
            response = original_open(opener,request,*args,**kwargs)
            if '/bridge/artifacts/' in request.full_url:
                self.responses.append(response)
            return response
        self.enterContext(patch.object(gui.client.urllib.request.OpenerDirector,'open',opened))
        self.receiver = FileReceiver(self)
        QDesktopServices.setUrlHandler('file',self.receiver,'receive')

    def tearDown(self):
        (CONTROL/'release').touch(mode=0o600)
        for dialog in self.dialogs:
            if dialog.worker and dialog.worker.isRunning():
                wait(lambda:not dialog.worker.isRunning())
            dialog.close()
            dialog.deleteLater()
        QDesktopServices.unsetUrlHandler('file')
        self.receiver.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        app.processEvents()
        self.assertFalse(isValid(self.receiver))
        self.assertTrue(all(response.closed for response in self.responses))
        self.assertEqual(self.qt_errors,[])

    def status(self,action):
        response = self.owner.get('/api/desktop-actions/'+action['id'])
        self.assertEqual(response.status_code,200)
        return response.json()

    def prepare(self,*,gate=True,launch=False):
        if launch:
            response = self.owner.post('/api/devices/'+self.config['device_id']+'/launch',json={'app':'system'})
            self.assertEqual(response.status_code,200)
            action = response.json()
            dialog = gui.LaunchDialog(action['id'])
        else:
            self.payload = (b'Actual Qt HTTPS artifact\n'*12000)[:262161]
            response = self.owner.post('/api/files',files={'file':('Lumen '+('ausfuehrliche Besprechungsnotizen '*4)+str(uuid4())+'.txt',self.payload,'text/plain')})
            self.assertEqual(response.status_code,200)
            file = response.json()
            response = self.owner.post('/api/devices/'+self.config['device_id']+'/open-artifact',json={'file_id':file['id']})
            self.assertEqual(response.status_code,200)
            action = response.json()
            self.target = gui.client.ROOT/'received'/(file['id']+'.txt')
            if gate:
                from server.db import connection
                with connection(self.credentials['id']) as db:
                    row = db.execute('SELECT storage_key FROM files WHERE id=%s',(file['id'],)).fetchone()
                (CONTROL/'target.json').write_text(json.dumps({'key':row['storage_key'] or file['id']}))
            dialog = gui.ArtifactDialog(action['id'])
        self.dialogs.append(dialog)
        dialog.show()
        wait(lambda:dialog.open.isEnabled())
        self.action = action
        return dialog

    def run_at_boundary(self,dialog,operation,*,published=None):
        self.boundary = {}
        deadline = time.monotonic()+6
        timer = QTimer()
        def poll():
            ready = published.is_set() if published else (CONTROL/'paused.json').exists()
            if ready or time.monotonic()>deadline:
                timer.stop()
                try:
                    self.assertTrue(ready)
                    progress = QApplication.activeModalWidget()
                    if progress is dialog:
                        progress = None
                    self.boundary['modal'] = progress is not None
                    if progress:
                        from lumen_jobs import Job
                        jobs = progress.findChildren(Job)
                        self.assertEqual(len(jobs),1)
                        self.boundary['job_cancel_before'] = jobs[0].cancelled.is_set()
                    operation(progress)
                    if progress:
                        self.boundary['job_cancel_after'] = jobs[0].cancelled.is_set()
                    self.boundary['parent_visible_before_release'] = dialog.isVisible()
                except Exception as error:
                    self.boundary['error'] = type(error).__name__
                finally:
                    if published:
                        self.release_publish.set()
                    (CONTROL/'release').touch(mode=0o600)
        timer.timeout.connect(poll)
        timer.start(5)
        dialog.open.click()
        wait(lambda:not timer.isActive())
        wait(lambda:not (dialog.worker and dialog.worker.isRunning()))
        app.processEvents()
        self.assertNotIn('error',self.boundary)
        return self.boundary

    def cancel(self,kind):
        dialog = self.prepare()
        def cancel(progress):
            if progress is None:
                dialog.close()
            elif kind=='button':
                progress.findChild(QDialogButtonBox).button(QDialogButtonBox.Cancel).click()
            elif kind=='escape':
                QTest.keyClick(progress,Qt.Key_Escape)
            else:
                progress.close()
        boundary = self.run_at_boundary(dialog,cancel)
        self.assertEqual(self.receiver.records,[])
        self.assertTrue(boundary['modal'])
        self.assertFalse(boundary['job_cancel_before'])
        self.assertTrue(boundary['job_cancel_after'])
        self.assertEqual(self.status(self.action)['state'],'failed')
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.target.parent.glob('.receive-*')),[])
        self.assertTrue((CONTROL/'closed.json').exists())

    def test_progress_cancel_button(self): self.cancel('button')
    def test_progress_escape(self): self.cancel('escape')
    def test_progress_close(self): self.cancel('close')

    def test_deferred_parent_close_does_not_cancel_job_or_deliver(self):
        dialog = self.prepare()
        boundary = self.run_at_boundary(dialog,lambda progress:dialog.close())
        self.assertEqual(self.receiver.records,[])
        self.assertTrue(boundary['parent_visible_before_release'])
        self.assertFalse(boundary['job_cancel_after'])
        self.assertFalse(dialog.isVisible())
        self.assertEqual(self.target.read_bytes(),self.payload)
        self.assertEqual(self.status(self.action)['state'],'claimed')

    def test_late_cancel_after_verified_replace_keeps_cache_without_delivery(self):
        dialog = self.prepare(gate=False)
        published = threading.Event()
        self.release_publish = threading.Event()
        original = gui.client.os.replace
        def replace(source,target):
            original(source,target)
            if Path(source).name.startswith('.receive-'):
                published.set()
                if not self.release_publish.wait(6):
                    raise TimeoutError('Owned publication boundary not released')
        with patch.object(gui.client.os,'replace',replace):
            self.run_at_boundary(dialog,lambda progress:progress.findChild(QDialogButtonBox).button(QDialogButtonBox.Cancel).click() if progress else dialog.close(),published=published)
        self.assertEqual(self.receiver.records,[])
        self.assertEqual(self.target.read_bytes(),self.payload)
        self.assertEqual(self.status(self.action)['state'],'failed')

    def fence(self,kind):
        dialog = self.prepare()
        def invalidate(progress):
            if kind=='config':
                other=json.loads(Path('/profile/other-config.json').read_text())
                gui.client.save_private(gui.client.CONFIG,json.dumps(other))
            elif kind=='config-identity':
                gui.client.save_private(gui.client.CONFIG,gui.client.CONFIG.read_text())
            elif kind=='ca':
                self.ca.write_bytes(self.ca.read_bytes()+b'\n')
            elif kind=='unreadable-config':
                gui.client.CONFIG.write_bytes(b' '*65537)
            elif kind=='generation':
                dialog.__dict__.setdefault('_receive_generation',0)
                dialog._receive_generation+=1
            elif kind=='pending-revision':
                dialog.action['revision']+=1
            else:
                dialog.identity=str(uuid4())
        self.run_at_boundary(dialog,invalidate)
        self.assertEqual(self.receiver.records,[])
        self.assertEqual(self.status(self.action)['state'],'claimed')
        self.assertEqual(self.target.read_bytes(),self.payload)
        self.assertEqual(sum(state=='completed' for path,state in self.calls),0)

    def test_config_value_fence(self): self.fence('config')
    def test_config_file_identity_fence(self): self.fence('config-identity')
    def test_ca_bytes_fence(self): self.fence('ca')
    def test_bounded_config_read_error_is_contained(self): self.fence('unreadable-config')
    def test_operation_generation_fence(self): self.fence('generation')
    def test_pending_action_revision_fence(self): self.fence('pending-revision')
    def test_dialog_identity_fence(self): self.fence('identity')

    def test_reentrant_url_handler_config_change_prevents_receipt(self):
        dialog = self.prepare(gate=False)
        self.receiver.reenter=lambda:gui.client.save_private(gui.client.CONFIG,json.dumps(dict(self.config,device_id=str(uuid4()))))
        dialog.open.click()
        wait(lambda:len(self.receiver.records)==1)
        wait(lambda:not (dialog.worker and dialog.worker.isRunning()))
        self.assertEqual(self.status(self.action)['state'],'claimed')
        self.assertFalse(any(state=='completed' for path,state in self.calls))

    def test_reentrant_url_handler_reject_prevents_receipt(self):
        dialog = self.prepare(gate=False)
        self.receiver.reenter=dialog.reject
        dialog.open.click()
        wait(lambda:len(self.receiver.records)==1)
        wait(lambda:not (dialog.worker and dialog.worker.isRunning()))
        self.assertEqual(self.status(self.action)['state'],'claimed')
        self.assertFalse(any(state=='completed' for path,state in self.calls))

    def test_double_activation_while_receiving_claims_once(self):
        dialog = self.prepare()
        self.run_at_boundary(dialog,lambda progress:dialog.accepted_request())
        wait(lambda:self.status(self.action)['state']=='completed')
        self.assertEqual(sum(state=='claimed' for path,state in self.calls),1)
        self.assertEqual(len(self.receiver.records),1)

    def test_unknown_claim_ack_does_not_reclaim(self):
        dialog = self.prepare(gate=False)
        self.lose_claim=True
        dialog.open.click()
        wait(lambda:not (dialog.worker and dialog.worker.isRunning()))
        dialog.accepted_request()
        wait(lambda:not (dialog.worker and dialog.worker.isRunning()))
        self.assertEqual(sum(state=='claimed' for path,state in self.calls),1)
        self.assertEqual(self.receiver.records,[])
        self.assertEqual(self.status(self.action)['state'],'claimed')

    def test_receipt_lost_ack_does_not_reopen_or_retry(self):
        dialog = self.prepare(gate=False)
        self.lose_receipt=True
        dialog.open.click()
        wait(lambda:self.status(self.action)['state']=='completed')
        wait(lambda:not (dialog.worker and dialog.worker.isRunning()))
        dialog.accepted_request()
        wait(lambda:not (dialog.worker and dialog.worker.isRunning()))
        self.assertEqual(sum(state=='claimed' for path,state in self.calls),1)
        self.assertEqual(sum(state=='completed' for path,state in self.calls),1)
        self.assertEqual(len(self.receiver.records),1)

    def test_real_revoke_during_receive_prevents_delivery(self):
        dialog = self.prepare()
        def revoke(progress):
            response=self.owner.put('/api/devices/'+self.config['device_id']+'/permissions',json={'capabilities':['desktop']})
            self.assertEqual(response.status_code,200)
        self.run_at_boundary(dialog,revoke)
        self.assertEqual(self.receiver.records,[])
        self.assertNotEqual(self.status(self.action)['state'],'completed')
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.target.parent.glob('.receive-*')),[])

    def test_real_foreign_actor_and_rls_are_denied(self):
        from server.db import connection
        other=json.loads(Path('/profile/foreign-action.json').read_text())
        response=self.owner.get('/api/desktop-actions/'+other['id'])
        self.assertEqual(response.status_code,404)
        with self.assertRaises(gui.urllib.error.HTTPError) as error:
            gui.client.request(self.config,'/bridge/actions/'+other['id'])
        self.assertIn(error.exception.code,(403,404))
        with connection(self.credentials['id']) as db:
            self.assertIsNone(db.execute('SELECT id FROM files WHERE id=%s',(other['file_id'],)).fetchone())

    def test_success_uses_real_qt_file_dispatch_and_current_receipt(self):
        dialog = self.prepare(gate=False)
        dialog.open.click()
        wait(lambda:self.status(self.action)['state']=='completed')
        self.assertEqual(len(self.receiver.records),1)
        self.assertEqual(self.receiver.errors,[])
        self.assertTrue(self.receiver.records[0]['gui_thread'])
        self.assertEqual(self.receiver.records[0]['sha256'],hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(self.receiver.records[0]['size'],len(self.payload))
        self.assertEqual(self.target.stat().st_mode&0o777,0o600)

    def test_launch_inheritance_actual_spawn_decline_error_and_close(self):
        directory=self.profile/'launch';directory.mkdir(exist_ok=True)
        marker=directory/'spawned'
        script=directory/'system_app.py'
        script.write_text('from pathlib import Path\nPath('+repr(str(marker))+').write_text("synthetic launched")\n')
        children=[]
        original_spawn=gui.subprocess.Popen
        def spawn(*args,**kwargs):
            child=original_spawn(*args,**kwargs);children.append(child)
            return child
        self.addCleanup(lambda:[child.wait(timeout=3) for child in children])
        with patch.object(gui,'desktop_files',directory),patch.object(gui.subprocess,'Popen',spawn):
            dialog=self.prepare(launch=True)
            entered=threading.Event();release=threading.Event()
            original_request=gui.client.request
            def claim(config,path,body=None,**kwargs):
                result=original_request(config,path,body,**kwargs)
                if body and body.get('state')=='claimed':
                    entered.set()
                    if not release.wait(4):raise TimeoutError('Owned launch claim was not released')
                return result
            with patch.object(gui.client,'request',claim):
                dialog.open.click();wait(entered.is_set)
                try:
                    dialog.close();self.assertTrue(dialog.isVisible())
                finally:
                    release.set()
                wait(lambda:self.status(self.action)['state']=='completed')
            wait(marker.exists)
            self.assertEqual(marker.read_text(),'synthetic launched')
            wait(lambda:not dialog.worker.isRunning())
            dialog.close()
            dialog=self.prepare(launch=True)
            dialog.decline.click()
            wait(lambda:self.status(self.action)['state']=='declined')
            wait(lambda:not dialog.worker.isRunning())
            dialog.close()
            script.unlink()
            dialog=self.prepare(launch=True)
            dialog.open.click()
            wait(lambda:self.status(self.action)['state']=='failed')
            wait(lambda:not dialog.worker.isRunning())
            dialog.close()
            dialog=self.prepare(launch=True)
            dialog.reject()
            self.assertFalse(dialog.isVisible())
            self.assertEqual(self.status(self.action)['state'],'pending')
        self.assertEqual(self.receiver.records,[])

    def test_panorama_actual_themes_sizes_and_labels(self):
        from appearance import apply_design
        metrics=[]
        for theme in ('glass','atelier'):
            apply_design(app,theme)
            for width,height,language in ((720,420,'de'),(420,520,'en')):
                os.environ['LUMEN_LANGUAGE']=language
                dialog=self.prepare(gate=False)
                dialog.resize(width,height);app.processEvents()
                name=f'{theme}-{width}x{height}-{language}'
                self.assertTrue(dialog.grab().save(str(OUTPUT/(name+'.png'))))
                margins=dialog.layout().contentsMargins()
                metrics.append(dict(name=name,size=[dialog.width(),dialog.height()],margins=[margins.left(),margins.top(),margins.right(),margins.bottom()],title=dialog.heading.text(),open=dialog.open.text(),close=dialog.decline.text(),scale=dialog.devicePixelRatioF()))
                self.assertLessEqual(dialog.width(),width)
                self.assertTrue(dialog.rect().contains(dialog.open.geometry()))
                self.assertTrue(dialog.rect().contains(dialog.decline.geometry()))
                dialog.decline.click();wait(lambda:not dialog.worker.isRunning())
                dialog.close()
        (OUTPUT/'panorama-metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
        self.assertTrue(all(row['margins']==[24,24,24,24] for row in metrics))
        os.environ['LUMEN_LANGUAGE']='de'


if __name__=='__main__':unittest.main()
