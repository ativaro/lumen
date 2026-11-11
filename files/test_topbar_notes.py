"""Explicit Notes references retain account, revision and AI access checks."""
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from uuid import uuid4

from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtCore import QCoreApplication,QEvent
from topbar_context import validate_note,note_attachment,saved_note,install_note


class TopbarNotesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def bundle(self):
        return dict(reference=dict(version=2,app='note',id=str(uuid4()),title='Workshop',
            locator=dict(server='https://synthetic.invalid',account=str(uuid4()))),revision=3)

    def test_reference_is_versioned_and_bound_to_exact_account(self):
        note=self.bundle();locator=note['reference']['locator']
        self.assertEqual(note_attachment(note,**dict(server=locator['server'],account=locator['account'])),
            dict(id=note['reference']['id'],kind='note',revision=3,mode='reference'))
        for revision in (True,0,'3'):
            with self.assertRaises(ValueError):validate_note(dict(note,revision=revision))
        for server,account in (('https://other.invalid',locator['account']),(locator['server'],str(uuid4()))):
            with self.assertRaises(ValueError):note_attachment(note,server,account)

    def test_only_current_ai_allowed_saved_notes_are_returned(self):
        bundle=self.bundle();ref=bundle['reference']
        context=SimpleNamespace(binding=SimpleNamespace(origin=ref['locator']['server'],account=ref['locator']['account']),
            session=Mock(),check=Mock())
        note=dict(id=ref['id'],kind='note',deleted=False,ai_allowed=True,title=ref['title'],revision=3,body='Must never leave Notes')
        context.session.request.return_value=note;job=Mock()
        with patch('server_notes_links._profile',return_value=({},7)) as proof:
            self.assertEqual(saved_note(context,ref['id'],job),bundle)
            self.assertNotIn('body',json.dumps(bundle));self.assertEqual(proof.call_count,2)
            for field,value in (('ai_allowed',False),('deleted',True),('id',str(uuid4())),('revision',0)):
                context.session.request.return_value={**note,field:value}
                with self.assertRaises(ValueError):saved_note(context,ref['id'],job)

    def test_real_dom_and_dbus_capture_only_the_open_saved_reference(self):
        note=self.bundle();window=QWidget();page=QWebEnginePage(window)
        page.setHtml('<section class="knowledge-editor" data-document-id="'+note['reference']['id']+'">Private body</section>')
        loaded=[];page.loadFinished.connect(loaded.append)
        until=time.monotonic()+8
        while not loaded and time.monotonic()<until:self.app.processEvents();time.sleep(.01)
        self.assertTrue(loaded and loaded[-1])
        window.page=page;window.profile=page.profile();window.view=Mock();window.session=SimpleNamespace(_generation=0)
        window._binding=Mock();window._generation=0;window._worker=None;window._import_running=False
        window._import_destroyed=Mock();window._import_close=False
        context=Mock()
        install_note(window)
        try:
            with patch('server_notes_links.Context',return_value=context),patch('server_app_window._connection',return_value=({},())), \
                    patch('interop_dialogs.run_job',return_value=note) as capture:
                script='import json;from topbar_context import read_note;print(json.dumps(read_note('+str(os.getpid())+')))'
                process=subprocess.Popen([sys.executable,'-c',script],cwd=Path(__file__).parent,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                until=time.monotonic()+8
                while process.poll() is None and time.monotonic()<until:self.app.processEvents();time.sleep(.01)
                if process.poll() is None:process.kill()
                out,err=process.communicate();self.assertEqual(process.returncode,0,err)
                self.assertEqual(json.loads(out),note);capture.assert_called_once()
                done=[];page.runJavaScript("window.addEventListener('beforeunload',event=>event.preventDefault())",0,lambda _:done.append(True))
                until=time.monotonic()+3
                while not done and time.monotonic()<until:self.app.processEvents();time.sleep(.01)
                value=json.loads(window._topbar_note.Reference())
                self.assertIn('speichern',value['error']);self.assertEqual(capture.call_count,1)
        finally:
            window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


if __name__=='__main__':unittest.main()
