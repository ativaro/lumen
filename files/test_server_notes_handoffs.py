"""Native review/selection plumbing; actual capture HTTP is tested separately."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from PySide6.QtWidgets import QApplication,QWidget,QMessageBox
from interop_data import Registry
from server_app_session import AppSession,Binding
from server_notes_handoffs import Requests


class NotesHandoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.env=patch.dict(os.environ,LUMEN_TOOLS_DATA=str(Path(self.temp.name)/'tools'));self.env.start();self.addCleanup(self.env.stop)
        self.registry=Registry();self.config=dict(server='https://synthetic.invalid',device_id=str(uuid4()),token='own-fixture')
        self.binding=Binding(self.config['server'],str(uuid4()),self.config['device_id'],'notes')
        self.window=QWidget();self.addCleanup(self.window.deleteLater)
        self.window.session=AppSession(self.config,self.binding);self.window._binding=self.binding;self.window._pilot_connection=('own',)
        self.requests=Requests(self.window)
        source=dict(app='files',kind='file',id='/fixture/source.txt',title='Own source',path='/fixture/source.txt')
        self.payload=dict(title='Own text',text='test\n\n\n\ntest1',source=source,source_url=self.registry.register(source))
        self.token=self.registry.enqueue('wissen','wissen.import',self.payload)
        self.choice=dict(id='',title='Own note',mode='copy',due='',token=self.token)
        self.reference=dict(version=2,app='note',id=str(uuid4()),title='Own note',locator=dict(server=self.binding.origin,account=self.binding.account))
        self.calls=[]
        def job(parent,title,function):return function(SimpleNamespace(check=lambda:None))
        for active in (patch('server_notes_handoffs.run_job',side_effect=job),
            patch('server_notes_app.context',return_value=(self.config,self.binding,('own',),7)),
            patch.object(AppSession,'connect'),patch('server_notes_handoffs.collections',return_value=[dict(id='',title='Ohne Sammlung')]),
            patch('server_notes_handoffs.review',return_value=self.choice),
            patch('server_notes_handoffs.capture',side_effect=lambda *args,**kwargs:self.calls.append((args,kwargs)) or self.reference),
            patch.object(Registry,'save_choice',side_effect=AssertionError('Core owns durable choice'))):
            active.start();self.addCleanup(active.stop)

    def test_review_reaches_existing_core_with_fresh_session_and_no_choice_overwrite(self):
        self.assertEqual(self.requests.receive(self.token),self.reference)
        args,kwargs=self.calls[0]
        self.assertEqual(args[:2],(self.token,self.choice));self.assertIsNot(args[2],self.window.session)
        self.assertEqual(args[3],7);self.assertFalse(kwargs['retry']);self.assertFalse(args[2].has_cookie)

    def test_uncertain_result_requires_explicit_retry_and_keeps_original_choice(self):
        stored=dict(self.choice,note_capture=dict(attempted=True))
        # Fixture-only durable state, equivalent to an interrupted core request.
        import json
        with self.registry.library.connect() as db:db.execute('UPDATE handoffs SET choice=? WHERE id=?',(json.dumps(stored),self.token))
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):
            self.assertIsNone(self.requests.receive(self.token));self.assertEqual(self.calls,[])
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):
            self.assertEqual(self.requests.receive(self.token),self.reference)
        self.assertTrue(self.calls[0][1]['retry']);self.assertEqual(self.calls[0][0][1],self.choice)

    def test_changed_pair_is_rejected_before_collections_review_or_capture(self):
        from server_app_session import SessionError
        with patch('server_notes_app.context',return_value=(self.config,self.binding,('changed',),7)):
            with self.assertRaises(SessionError):self.requests.receive(self.token)
        self.assertEqual(self.calls,[])

    def test_version_two_note_link_launches_server_notes_not_legacy_app(self):
        import interop_open
        url=self.registry.register(self.reference)
        with patch.object(interop_open,'launch') as launch:
            interop_open.open_url(url)
            launch.assert_called_once_with('wissen',['--ref',url],None)

if __name__=='__main__':unittest.main()
