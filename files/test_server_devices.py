"""Native selection, actions, account boundaries and asynchronous lifetime."""
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import QSettings
from server_devices import ServerDevices
APP=QApplication.instance() or QApplication([])

def idle(w):
    for _ in range(300):
        QTest.qWait(10)
        if not w.job:QTest.qWait(10)
        if not w.job:return
    raise AssertionError('Native request did not finish')

class NativeServerTest(unittest.TestCase):
    def test_widgets_and_lifecycle(self):
        with tempfile.TemporaryDirectory() as folder:
            config=dict(server='https://example.test',token='synthetic')
            space,item,task,device=[str(uuid4()) for _ in range(4)];calls=[]
            work=dict(id=item,title='Wochenbericht',kind='automation',state='completed',archived=False,
                revision=2,goal='## Ergebnis',interval_minutes=60,automation=None,operation='analysis',notes='',attachments=[],depends=[],done=False)
            data=dict(role='manager',items=[work],tasks=[dict(id=task,project_item_id=item,state='completed',
                revision=3,created='2026-10-07',result='- [ ] Prüfen\n- [x] Sichern')],members=[dict(id='u',name='Alex',role='manager')],notes=[],files=[])
            def request(c,path,body=None):
                calls.append((path,body))
                if path=='/bridge/me':return dict(capabilities=['projects','tasks','device_control','wake'])
                if path=='/bridge/projects':return [dict(id=space,title='Workshop')]
                if path.endswith('/activity'):return data
                if path=='/bridge/management' and body is None:return [dict(id=device,name='Desktop',inventory={'hostname':'desktop'},operations=['services'],last_seen=None,wake_ready=True)]
                if path=='/bridge/management':return dict(id=body['request_id'],actions=[dict(id='a',state='claimed',progress={'checks':{'lumen-watch.service':{'state':'active','expected':'running','load':'loaded'}},'current':'lumen-jobs.service'})])
                return {}
            with patch('server_devices.lumen_connect.read_config',lambda:config),patch('server_devices.lumen_connect.request',request):
                d=ServerDevices();d.show();idle(d)
                self.assertTrue(d.run.isEnabled());self.assertTrue(d.wake.isEnabled());d.run.click();idle(d)
                self.assertIn('lumen-watch.service',d.progress.item(1).text());self.assertFalse(d.run.isEnabled());self.assertIsNotNone(d.receipt)
                d.show_progress(dict(actions=[dict(state='completed',result=dict(services={'lumen-watch.service':'active'}))]))
                self.assertIsNone(d.receipt);self.assertTrue(d.run.isEnabled())
                with patch('server_devices.lumen_connect.request',side_effect=lambda *a,**k:(__import__('time').sleep(.05),request(*a,**k))[1]):
                    d.reload();d.close();d.deleteLater()
                    for _ in range(200):
                        QTest.qWait(10)
                        if not APP._server_jobs:break
                self.assertFalse(APP._server_jobs)
if __name__=='__main__':unittest.main()
