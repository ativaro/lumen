import tempfile
import unittest
import os
from pathlib import Path
from lumen_store import Store
from wissen_data import Notebook,activate
from lumen_memory import Memory,stamp


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name);self.store=Store(self.base/'state');activate(self.store);self.notes=Notebook(self.store);self.memory=Memory(self.store)

    def test_private_notes_and_folder_overrides_project_scope(self):
        self.memory.configure(True,True)
        private=self.notes.create('Privat','Projekt geheimes Detail')
        shared=self.notes.create('Freigegeben','Projekt gemeinsamer Plan')
        global_note=self.memory.remember('Stil','Ich bevorzuge kurze Antworten.',kind='preference')
        self.memory.remember('Projektentscheidung','Projekt bleibt lokal.',scope=str(self.base/'one'))
        result=self.memory.prepare('Projekt',str(self.base/'two'))
        self.assertIn('kurze Antworten',result['context']);self.assertNotIn('geheimes',result['context']);self.assertNotIn('gemeinsamer',result['context']);self.assertNotIn('bleibt lokal',result['context'])
        self.memory.share('.',True,True);self.memory.share(private['path'],False)
        result=self.memory.prepare('Projekt',str(self.base/'one/sub'))
        self.assertIn('gemeinsamer Plan',result['context']);self.assertNotIn('geheimes',result['context']);self.assertIn('bleibt lokal',result['context'])
        before=stamp(self.store);self.memory.share(shared['path'],False);self.assertNotEqual(stamp(self.store),before)
        self.assertNotIn('gemeinsamer',self.memory.prepare('Projekt',str(self.base))['context'])
        self.assertEqual(self.notes.read(private['path'])['text'],private['text'])
        self.memory.configure(False,False);self.assertEqual(self.memory.prepare('Projekt',str(self.base))['context'],'')

    def test_learning_evidence_conflicts_deduplication_and_forget(self):
        self.memory.configure(True,True);user='Ich möchte kurze Antworten.'
        item=dict(title='Antwortlänge',text='Der Nutzer möchte kurze Antworten.',kind='preference',scope='global',evidence=user)
        revision=self.store.setting('memory/revision',0)
        self.assertEqual(self.memory.apply([item,item],user,str(self.base),'Gespräch 1',[],revision),1)
        note=self.memory.scan()['notes'][0];self.assertTrue(note['memory']['automatic']);self.assertEqual(note['memory']['evidence'],user)
        prepared=self.memory.prepare('Antworten',str(self.base))
        changed=dict(item,path=note['path'],text='Antworten sollen sehr kurz sein.')
        edited=self.memory.write(note['path'],'# Antwortlänge\nMeine Korrektur.',note['hash'])
        self.assertEqual(self.memory.apply([changed],user,str(self.base),'Gespräch 2',prepared['candidates'],self.store.setting('memory/revision',0)),0)
        self.assertIn('Meine Korrektur',self.memory.book.read(note['path'])['text'])
        self.memory.forget(note['path'],edited['hash']);self.assertEqual(self.memory.scan()['notes'],[]);self.assertEqual(self.memory.book.versions(note['path']),[])
        self.assertEqual(self.memory.apply([item],user,str(self.base),'Gespräch 3',[],self.store.setting('memory/revision',0)),0)
        self.assertEqual(self.memory.apply([dict(item,title='Geänderte Formulierung')],user,str(self.base),'Gespräch 3',[],self.store.setting('memory/revision',0)),0)
        self.assertEqual(Memory(self.store).prepare('Antworten',str(self.base))['context'],'')

    def test_invalid_or_stale_suggestions_and_path_boundaries(self):
        self.memory.configure(True,True);revision=self.store.setting('memory/revision',0)
        item=dict(title='Schriftart',text='Bevorzugt eine große Schrift.',kind='preference',scope='global',evidence='Ich mag große Schrift.')
        self.assertEqual(self.memory.apply([item],'Anderer Text',str(self.base),'Quelle',[],revision),0)
        self.assertEqual(self.memory.apply([dict(item,path='../outside.md')],item['evidence'],str(self.base),'Quelle',[],revision),0)
        self.memory.configure(True,False)
        self.assertEqual(self.memory.apply([item],item['evidence'],str(self.base),'Quelle',[],revision),0)
        self.memory.configure(True,True)
        self.assertEqual(self.memory.apply([item],item['evidence'],str(self.base),'Quelle',[],revision),0)
        for path in ('../','/tmp'):
            with self.assertRaises((ValueError,OSError)):self.memory.share(path,True,True)
        self.assertEqual(self.store.setting('memory/shares',[]),[])


class MemoryBackendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_learning_recall_and_revocation_in_shared_backend(self):
        import json,threading,time
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from unittest.mock import patch
        from PySide6.QtTest import QTest
        from assistant_backend import OpenCodeBackend
        state={'sessions':{},'prompts':[],'counter':0}
        user='Ich möchte kurze Antworten.'
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_GET(self):self.handle_request('GET')
            def do_POST(self):self.handle_request('POST')
            def handle_request(self,method):
                path=self.path.split('?')[0];body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or 'null');result={}
                if path=='/session' and method=='POST':
                    state['counter']+=1;result={'id':'session-'+str(state['counter'])};state['sessions'][result['id']]=[]
                elif path.endswith('/prompt_async'):
                    session=path.split('/')[2];state['prompts'].append((session,body))
                    answer=json.dumps({'memories':[dict(title='Antwortlänge',text='Der Nutzer möchte kurze Antworten.',kind='preference',scope='global',evidence=user)]}) if body.get('tools')=={'*':False} else 'Verstanden.'
                    state['sessions'][session]=[{'info':{'role':'assistant','parentID':body['messageID'],'time':{'completed':123}},'parts':[{'type':'text','text':answer}]}]
                elif path.endswith('/message'):result=state['sessions'][path.split('/')[2]]
                elif path in ('/session','/permission','/question'):result=[]
                raw=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        def wait(predicate):
            deadline=time.monotonic()+12
            while not predicate() and time.monotonic()<deadline:QTest.qWait(20)
            self.assertTrue(predicate())
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_DATA':tmp+'/state'}):
            store=Store();memory=Memory(store);memory.configure(True,True)
            backend=OpenCodeBackend(tmp,server_url='http://127.0.0.1:'+str(server.server_port),password='test');backend.ensure_server=lambda callback:callback()
            try:
                backend.send(user);wait(lambda:memory.scan()['notes']);wait(lambda:not backend.busy)
                first=state['prompts'][0][0];backend.send('Welche Antwortlänge passt?');wait(lambda:len(state['prompts'])>=3 and not backend.busy)
                self.assertIn('kurze Antworten',state['prompts'][2][1]['system']);self.assertEqual(first,state['prompts'][2][0])
                note=memory.scan()['notes'][0];prepare=backend.memory.prepare
                def revoke_while_preparing(text,directory,done):
                    backend.memory.prepare=prepare;memory.forget(note['path'],note['hash']);prepare(text,directory,done)
                backend.memory.prepare=revoke_while_preparing
                backend.send('Welche Antwortlänge passt jetzt?');wait(lambda:len(state['prompts'])>=4 and not backend.busy)
                self.assertNotEqual(first,state['prompts'][3][0]);self.assertNotIn('kurze Antworten',state['prompts'][3][1]['system'])
                backend.send('Native Vorschläge',proposal=True);wait(lambda:len(state['prompts'])>=5 and not backend.busy)
                self.assertNotIn('lumen-memory',state['prompts'][4][1]['system']);self.assertEqual(state['prompts'][4][1]['tools'],{'*':False})
                memory.remember('Schreibstil','Schreibe freundliche kurze Mails.',kind='preference')
                other=OpenCodeBackend(tmp,server_url=backend.url,password='test');other.ensure_server=lambda callback:callback()
                try:
                    other.send('Mail entwerfen',proposal=True,memory_context=True,memory_text='Mail schreiben');wait(lambda:len(state['prompts'])>=6 and not other.busy)
                    self.assertIn('freundliche kurze Mails',state['prompts'][5][1]['system']);self.assertEqual(state['prompts'][5][1]['tools'],{'*':False})
                finally:other.shutdown();other.deleteLater()
                delayed=[];backend.memory.prepare=lambda text,directory,done:delayed.append(done)
                backend.send('Diese Anfrage abbrechen');self.assertTrue(backend.busy);self.assertEqual(len(delayed),1)
                backend.stop();delayed[0](memory.prepare('Antworten',tmp));QTest.qWait(50)
                self.assertFalse(backend.busy);self.assertEqual(len(state['prompts']),6)
            finally:backend.shutdown();backend.deleteLater();QTest.qWait(30)
        server.shutdown();server.server_close()

    def test_native_areas_sharing_correction_forget_and_chat_capture(self):
        from unittest.mock import patch
        from PySide6.QtCore import QCoreApplication,QEvent,QSettings
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QMessageBox
        from tools_wissen import Wissen
        from assistant import ChatPanel
        def wait(window,predicate=lambda:True):
            for _ in range(300):
                QTest.qWait(20)
                if not window.job and not window.poller and predicate():return
            self.fail(window.status.text())
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_DATA':tmp+'/state'}):
            store=Store();activate(store);book=Notebook(store);personal=book.create('Eigene Ideen','Privater Gedanke')
            memory=Memory(store);memory.configure(True,True);learned=memory.remember('Stil','Ich möchte kurze Antworten.',automatic=True,evidence='Ich möchte kurze Antworten.',kind='preference')
            window=Wissen(Path(tmp)/'tools');window.show();wait(window,lambda:personal['path'] in window.notes)
            window.open_note(personal['path']);wait(window);self.assertFalse(window.share_note.isChecked())
            window.share_note.setChecked(True);wait(window);self.assertTrue(memory.shared(book,personal['path']))
            window.editor.appendPlainText('Eigene Ergänzung');window.switch_area('lumen');wait(window,lambda:window.area=='lumen' and learned['path'] in window.notes)
            self.assertIn('Eigene Ergänzung',book.read(personal['path'])['text']);self.assertNotIn(personal['path'],window.notes)
            window.open_note(learned['path']);wait(window);window.editor.appendPlainText('Meine Korrektur');window.save_note();wait(window)
            self.assertFalse(store.setting('memory/records')[learned['path']]['automatic'])
            with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):window.archive()
            wait(window);self.assertEqual(memory.scan()['notes'],[]);self.assertEqual(memory.book.versions(learned['path']),[])
            window.close();window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
            panel=ChatPanel(tmp,settings=QSettings(tmp+'/assistant.ini',QSettings.IniFormat));panel.last_prompt='Ein gespeicherter Gedanke';panel.last_answer='Eine hilfreiche Antwort.'
            for remember in (False,True):
                panel.show_messages([{'info':{'role':'assistant'},'parts':[{'type':'text','text':'Eine hilfreiche Antwort.'}]}])
                panel.capture_knowledge(remember)
                self.assertIsNotNone(panel.memory_capture_job,(remember,panel.last_answer,panel.memory_status.text()))
                for _ in range(200):
                    QTest.qWait(20)
                    if panel.memory_capture_job is None:break
                self.assertIsNone(panel.memory_capture_job)
                self.assertEqual(panel.memory_status.text(),'Im Lumen-Gedächtnis gespeichert.' if remember else 'In deinem Notizbuch gespeichert.',panel.error.text())
            self.assertEqual(len(book.scan()['notes']),2);self.assertEqual(len(memory.scan()['notes']),1)
            panel.context_tools.close();panel.backend.shutdown();panel.close();panel.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


if __name__=='__main__':unittest.main()
