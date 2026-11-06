"""Native server lifecycle: uncertain submission, recovery and late cancellation."""
import os
import tempfile
import time
import unittest
from uuid import uuid4
from unittest.mock import patch
from urllib.error import HTTPError
from PySide6.QtCore import QSettings, QObject
from PySide6.QtWidgets import QApplication
from desktop_backend import DesktopBackend, PREFIX, _workers


class ServerConversationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait(self, predicate):
        until = time.monotonic()+5
        while not predicate() and time.monotonic() < until:
            self.app.processEvents(); time.sleep(.01)
        self.assertTrue(predicate())

    def test_notes_keep_the_original_reference_and_reject_changed_access(self):
        account=str(uuid4());note_id=str(uuid4())
        note=dict(reference=dict(version=2,app='note',id=note_id,title='Workshop',
            locator=dict(server='https://synthetic.invalid',account=account)),revision=4)
        for allowed in (True,False):
            with self.subTest(allowed=allowed),tempfile.TemporaryDirectory() as tmp, \
                    patch.dict(os.environ,LUMEN_DATA=tmp),patch('lumen_connect.read_config',return_value=dict(server='https://synthetic.invalid',token='synthetic')):
                backend=DesktopBackend(tmp);backend.settings=QSettings(tmp+'/settings.ini',QSettings.IniFormat)
                backend.execution='server';from desktop_backend import connection
                backend.binding=connection()[1];backend.server_origin='https://synthetic.invalid'
                requests=[];errors=[];backend.failed.connect(errors.append)
                def request(config,path,body=None):
                    requests.append((path,body))
                    if path=='/bridge/me':return dict(id=account)
                    if path=='/bridge/context/capability':
                        if not allowed:raise HTTPError(config['server']+path,403,'Private server body',{},None)
                        return dict(body,supported=True)
                    if path.startswith('/bridge/context-files/'):return dict(id=str(uuid4()),version=1)
                    if path=='/bridge/tasks':return dict(id=str(uuid4()))
                    raise AssertionError(path)
                try:
                    with patch('lumen_connect.request',side_effect=request),patch.object(backend,'poll'):
                        self.assertTrue(backend.send('Zusammenfassen',context_data=dict(note_reference=note)))
                        self.wait(lambda:not _workers and not backend.submitting)
                    tasks=[body for path,body in requests if path=='/bridge/tasks']
                    if allowed:
                        self.assertEqual(tasks[0]['attachments'][0],dict(id=note_id,kind='note',revision=4,mode='reference'))
                        self.assertFalse(errors)
                    else:
                        self.assertFalse(tasks);self.assertFalse(backend.remote_key)
                        self.assertTrue(errors);self.assertNotIn('Private server body',errors[0])
                finally:backend.set_busy(False);backend.shutdown();self.wait(lambda:not _workers)

    def test_confirmed_context_rejection_clears_only_its_exact_submission(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,LUMEN_DATA=tmp),patch('lumen_connect.read_config',return_value=dict(server='https://synthetic.invalid',token='synthetic')):
            backend=DesktopBackend(tmp);backend.settings=QSettings(tmp+'/settings.ini',QSettings.IniFormat)
            backend.execution='server'
            from desktop_backend import connection
            backend.binding=connection()[1]
            backend.server_origin='https://synthetic.invalid'
            errors=[];backend.failed.connect(errors.append)
            def request(config,path,body=None):
                if path=='/bridge/me':return dict(id=str(uuid4()))
                raise HTTPError(config['server']+path,413,'Do not display secret body',{},None)
            try:
                with patch('lumen_connect.request',side_effect=request):
                    self.assertTrue(backend.send('Two individually readable sources exceed the combined limit'))
                    self.wait(lambda:not _workers and not backend.busy)
                self.assertEqual(backend.remote_key,'');self.assertFalse(backend.remote_active)
                self.assertEqual(backend.pending(),[])
                self.assertEqual(len(errors),1);self.assertIn('Serverlimit',errors[0]);self.assertNotIn('secret',errors[0])
                old_key,new_key=str(uuid4()),str(uuid4())
                backend.remote_key=new_key;backend.remote_active=True;backend.set_busy(True);backend.remember(new_key)
                late=dict(local_context_error='Old rejection',rejected_submission=(backend.binding,backend.session,old_key))
                backend._apply_response((backend.generation,'submit',late,False))
                self.assertEqual(backend.remote_key,new_key);self.assertTrue(backend.busy)
                self.assertIn(new_key,backend.pending())
                late['rejected_submission']=(backend.binding,'another-conversation',new_key)
                backend._apply_response((backend.generation,'submit',late,False))
                self.assertEqual(backend.remote_key,new_key);self.assertTrue(backend.busy)
                late['rejected_submission']=(backend.binding,backend.session,new_key)
                backend._apply_response((backend.generation-1,'submit',late,False))
                self.assertEqual(backend.remote_key,new_key);self.assertTrue(backend.busy)
            finally:backend.set_busy(False);backend.shutdown();self.wait(lambda:not _workers)

    def test_other_http_failures_remain_uncertain(self):
        for status,path in ((503,'/bridge/tasks'),(413,'/bridge/context/capability')):
            with self.subTest(status=status,path=path),tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,LUMEN_DATA=tmp),patch('lumen_connect.read_config',return_value=dict(server='https://synthetic.invalid',token='synthetic')):
                backend=DesktopBackend(tmp);backend.settings=QSettings(tmp+'/settings.ini',QSettings.IniFormat)
                backend.execution='server'
                from desktop_backend import connection
                backend.binding=connection()[1];backend.server_origin='https://synthetic.invalid'
                def request(config,route,body=None):
                    if route=='/bridge/me':return dict(id=str(uuid4()))
                    raise HTTPError(config['server']+path,status,'Not a confirmed task rejection',{},None)
                try:
                    with patch('lumen_connect.request',side_effect=request):
                        self.assertTrue(backend.send('Keep uncertain receipt'))
                        self.wait(lambda:not _workers and not backend.busy)
                    self.assertTrue(backend.remote_active)
                    self.assertTrue(backend.remote_key)
                    self.assertIn(backend.remote_key,backend.pending())
                finally:backend.shutdown();self.wait(lambda:not _workers)

    def test_delivery_recovery_followup_cancel_and_privacy(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp}):
            cfg = {'server': 'https://synthetic.invalid', 'token': 'synthetic-token'}
            rows = {}; requests = []; uncertain = [True]; hold = [False]
            def request(config, path, body=None):
                requests.append((path, body))
                if path == '/bridge/me': return {'workspace_id': 'test-workspace'}
                if path == '/bridge/conversations': return {'items': list(rows.values())[-5:]}
                if path == '/bridge/tasks':
                    identity = str(uuid4())
                    rows[identity] = dict(body, id=identity, title=body['prompt'], result='', state='queued')
                    while hold[0]: time.sleep(.01)
                    if uncertain[0]:
                        uncertain[0] = False
                        raise OSError('Response lost after commit')
                    return rows[identity]
                if path.startswith('/bridge/task-receipts/'):
                    return next((r for r in rows.values() if r['idempotency_key'] == path.rsplit('/',1)[-1]), None)
                identity = path.split('/')[3]; row = rows[identity]
                if path.endswith('/cancel'): row['state'] = 'cancelled'; return row
                if path.endswith('/history'):
                    parent = row.get('parent_id')
                    return ([rows[parent]] if parent else [])+[row]
                return row
            with patch('lumen_connect.read_config', return_value=cfg), patch('lumen_connect.request', side_effect=request), patch('assistant_backend.OpenCodeBackend.send') as local:
                backend = DesktopBackend(tmp); backend.settings = QSettings(tmp+'/state.ini', QSettings.IniFormat)
                errors=[]; completions=[]
                backend.failed.connect(errors.append); backend.completed.connect(lambda *args: completions.append(args))
                self.assertTrue(backend.set_execution('server')); self.wait(lambda: not _workers)
                self.assertFalse(backend.preflight(['/private/secret.txt']))
                backend.send('Synthetic question')
                self.wait(lambda: errors and not backend.busy and bool(rows) and not _workers)
                self.assertTrue(backend.remote_active)
                key = backend.remote_key
                self.assertIn(key, backend.pending())
                backend.send('Do not duplicate'); self.assertEqual(len(rows),1)
                backend.poll()
                self.wait(lambda: backend.session.startswith(PREFIX) and not backend.remote_key and backend.busy)
                identity = backend.identity(); rows[identity].update(state='completed', result='Synthetic answer')
                self.wait(lambda: not backend.busy)
                self.assertEqual(completions[-1], (True,'Synthetic answer')); self.assertEqual(backend.pending(),[])
                hold[0]=True; backend.send('Follow-up'); self.wait(lambda: len(rows)==2)
                backend.stop(); hold[0]=False; self.wait(lambda: len(completions)==2)
                child = list(rows.values())[-1]
                self.assertEqual(child['parent_id'], identity); self.assertEqual(child['state'],'cancelled')
                self.assertEqual([m['info']['role'] for m in backend.messages], ['user','assistant','user'])
                self.assertTrue(all('/private/' not in str(body) for _,body in requests if body))
                local.assert_not_called()
                backend.remember(key)
                recovered = DesktopBackend(tmp); recovered.settings = backend.settings
                recovered.set_execution('server'); recovered.select_session(PREFIX+backend.binding+'/pending/'+key)
                self.wait(lambda: recovered.session.endswith(identity) and not recovered.busy)
                self.assertEqual(recovered.messages[-1]['parts'][0]['text'],'Synthetic answer')
                recovered.shutdown();self.wait(lambda: not _workers)
                cfg['token']='replacement-token';before=len(requests);backend.poll()
                self.wait(lambda: not _workers);self.assertEqual(len(requests), before)
                backend.shutdown()

    def test_widgets_and_search_keep_attachment_drafts(self):
        from search_controller import SearchController
        from studio_chat import StudioChat
        from search_qml import create_window
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp}), patch.object(DesktopBackend, 'refresh_sessions'), patch('lumen_connect.read_config', return_value={'server':'https://test.invalid','token':'test'}):
            panel = StudioChat(tmp); controller = SearchController(tmp, applications=[])
            engine, window = create_window(self.app, controller)
            try:
                self.assertEqual(panel.backend.execution,'local')
                panel.execution.setCurrentIndex(1); panel.choose_execution()
                self.assertFalse(panel.persona.isEnabled())
                panel.backend.set_busy(True)
                with patch('assistant.QMessageBox.question', side_effect=AssertionError('Closing must not offer to cancel a remote task')):
                    self.assertTrue(panel.can_close())
                panel.backend.set_busy(False)
                panel.paths=['/private/data.txt'];panel.composer.setPlainText('Keep this draft')
                panel.submit(panel.composer.toPlainText());self.assertEqual(panel.composer.toPlainText(),'Keep this draft')
                controller.set_execution('server');controller.show_conversation()
                controller._attachments=['/private/data.txt'];controller.set_query('Keep search draft')
                controller.submit(True);self.assertEqual(controller.query,'Keep search draft')
                self.assertIsNotNone(window.findChild(QObject, 'executionChoice'))
                self.assertEqual(controller.execution,'server')
                panel.paths=[];panel.composer.setPlainText('x'*20001);panel.submit(panel.composer.toPlainText())
                self.assertEqual(len(panel.composer.toPlainText()),20001)
                controller._attachments=[];controller.set_query('x'*20001);controller.submit(True)
                self.assertEqual(len(controller.query),20001)
            finally:
                controller.shutdown();window.hide();engine.deleteLater()
                panel.context_tools.close();panel.backend.shutdown();panel.close();panel.deleteLater();self.app.processEvents()


if __name__ == '__main__': unittest.main()

class NativeContextTest(unittest.TestCase):
    def test_selected_text_is_copied_without_local_paths_and_history_is_paginated(self):
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_DATA':tmp}),patch('lumen_connect.read_config',return_value=dict(server='https://example.invalid',token='test')):
            from pathlib import Path
            path=Path(tmp)/'Selected.md';path.write_text('# Selected\n\nOnly this content')
            backend=DesktopBackend(tmp);backend.settings=QSettings(tmp+'/settings.ini',QSettings.IniFormat)
            backend.execution='server'
            from desktop_backend import connection
            _,backend.binding=connection()
            calls=[]
            def request(route,body=None):
                calls.append((route,body))
                if route=='/bridge/me':return dict(workspace_id=str(uuid4()))
                if route.startswith('/bridge/context-files/'):return dict(id=str(uuid4()),version=1)
                return dict(id=str(uuid4()))
            try:
                with patch.object(backend,'_run',side_effect=lambda op,fn:fn(request)):
                    self.assertTrue(backend.send('Read my selected file',[(str(path),'text/markdown')]))
                self.assertNotIn(tmp,str(calls))
                self.assertEqual(calls[1][1]['text'],path.read_text())
                self.assertEqual(len(calls[-1][1]['attachments']),1)
                backend.set_busy(False)
                older=str(uuid4());newer=str(uuid4());cursor=str(uuid4())
                backend._apply_response((backend.generation,'sessions',dict(items=[dict(id=newer,title='Newest')],next=cursor),False))
                self.assertEqual(backend.server_cursor,cursor)
                backend._apply_response((backend.generation,'sessions_more',dict(items=[dict(id=older,title='Older')],next=None),False))
                self.assertEqual(len(backend.server_sessions),2)
                self.assertIsNone(backend.server_cursor)
                backend.history_rows=[dict(id=newer,parent_id=older,prompt='New',result='Answer')]
                with patch.object(backend,'refresh_sessions'):
                    backend._apply_response((backend.generation,'history_more',[dict(id=older,parent_id=None,prompt='Old',result='Old answer')],False))
                self.assertFalse(backend.history_more)
                self.assertEqual(backend.messages[0]['parts'][0]['text'],'Old')
            finally:backend.shutdown();app.processEvents()
