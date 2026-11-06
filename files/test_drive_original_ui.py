"""The announced return path is a real action in both receiving native apps."""
import hashlib
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
from PySide6.QtWidgets import QApplication,QMenu
from PySide6.QtTest import QTest
from interop_data import Registry
from interop_targets import apply
from tools_ui import Job
import drive_references as drive
import interop_context
import interop_open
from lumen_i18n import tr

class OriginalUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.app=QApplication.instance() or create_app()

    def test_reader_and_translate_offer_the_real_original_opener(self):
        from tools_reader import Reader
        from tools_translate import Translate
        from app import Window
        from PySide6.QtCore import QSettings
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,LUMEN_TOOLS_DATA=tmp+'/tools',LUMEN_DATA=tmp+'/state',XDG_CACHE_HOME=tmp+'/cache'):
            root=Path(tmp)/'tools';config=dict(server='https://staging.invalid',token='never-in-reference');account=str(uuid4());family=str(uuid4())
            ref=dict(app='files',kind='drive_file',id=family,title='Original.txt',locator=dict(server=config['server'],account=account))
            row=dict(id=str(uuid4()),family=family,name='Original.txt',folder_id=None,trashed=False,can_write=True,size=5,mime='text/plain',revision=1,sha256=hashlib.sha256(b'hello').hexdigest())
            cache=dict(files={family:row},folders={});url=Registry(root).register(ref)
            payload=dict(title='Original',source=ref,source_url=url,paths=[],references=[ref])
            files=Window(tmp,QSettings(tmp+'/files.ini',QSettings.IniFormat));windows=[files];errors=[]
            files.error=lambda *args:errors.append(args)
            def wait(predicate):
                until=time.monotonic()+20
                while not predicate() and time.monotonic()<until:QTest.qWait(20)
                self.assertTrue(predicate(),str(errors))
            def download(config,folder,row,progress):
                Path(folder['path'],'stage').write_bytes(b'hello');return 'stage'
            def launch(app,args,origin):
                self.assertEqual((app,args,origin),('files',['--ref',url],root))
                files.drive.follow_reference(Registry(origin).resolve(args[1]))
            with patch.object(drive.lumen_connect,'read_config',return_value=config),patch.object(drive.lumen_connect,'request',return_value=dict(id=account,can_create=True)),patch.object(drive.sync,'inventory',return_value=cache),patch('drive_transport.download',side_effect=download) as fetch,patch.object(interop_open,'launch',side_effect=launch) as opened:
                try:
                    for cls,action in ((Reader,'reader.import'),(Translate,'translate.import')):
                        result=apply(action,payload,dict(title='Copy',mode='copy',token=uuid4().hex),Job(lambda _:None),root)
                        w=cls(root);windows.append(w);w.error=lambda value:errors.append(value);w.show();w.focus_record(result['id']);wait(lambda:not w.job)
                        menu=QMenu(w);interop_context.add_actions(w,menu)
                        original=next(a for a in menu.actions() if a.text()==tr('Original öffnen'))
                        calls=fetch.call_count;original.trigger();wait(lambda:not files.drive.jobs)
                        self.assertEqual(fetch.call_count,calls,'Opening original must not copy or upload')
                        self.assertEqual(files.selected_paths(),[next(key for key,(_,entry) in files.drive.entries.items() if entry.get('family')==family)])
                    self.assertEqual(opened.call_count,2);self.assertEqual(errors,[])
                finally:
                    for w in reversed(windows):
                        if getattr(w,'job',None):w.job.cancelled.set();w.job.wait(5000)
                        w.close();w.deleteLater()
                    QTest.qWait(50)

if __name__=='__main__':unittest.main()
