import tempfile
import unittest
import os
from pathlib import Path
from lumen_store import Store
from wissen_data import Notebook,activate
from lumen_memory import Memory,stamp
from lumen_i18n import tr


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name);self.store=Store(self.base/'state');activate(self.store);self.notes=Notebook(self.store);self.memory=Memory(self.store)

    def test_identity_survives_reload_and_edit_but_isolates_profiles(self):
        self.memory.remember('Original','PostgreSQL')
        first=self.memory.scan()['notes'][0]
        again=Memory(self.store).scan()['notes'][0]
        self.assertEqual(first['id'],again['id'])
        self.memory.write(first['path'],'# Neuer Titel\nSQLite',first['hash'])
        edited=Memory(self.store).scan()['notes'][0]
        self.assertEqual(first['id'],edited['id'])
        self.assertNotEqual(first['revision'],edited['revision'])
        other=Memory(Store(self.base/'other'))
        self.assertNotEqual(first['id'],other.identity(first['path']))

    def test_external_edit_during_search_is_not_returned_as_current(self):
        from unittest.mock import patch
        self.memory.configure(True,False)
        note=self.memory.remember('Server','PostgreSQL')
        def changed(*args,**kwargs):
            self.memory.book.write(note['path'],'# Server\nSQLite',note['hash'])
            return dict(mode='text',reason='not_installed',scores={})
        with patch('memory_local.retrieve',side_effect=changed):
            result=self.memory.prepare('PostgreSQL',str(self.base))
        self.assertEqual(result['context'],'');self.assertEqual(result['notes'],[])
        result=self.memory.prepare('SQLite',str(self.base))
        self.assertIn('SQLite',result['context'])
        for source in result['notes']:
            self.assertIn(source['id'],result['context']);self.assertIn(source['revision'],result['context'])
        self.assertLessEqual(len(result['context']),18000)

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
        self.memory.configure(True,True,automatic=True);user='Ich möchte kurze Antworten.'
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
        from app import create_app
        cls.app=QApplication.instance() or create_app()

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
                    session=path.split('/')[2]
                    is_learning=body['parts'][0]['text'].startswith('Load the lumen-memory-learning skill')
                    if not is_learning:state['prompts'].append((session,body))
                    answer='Verstanden.'
                    if is_learning:
                        import subprocess,sys
                        event=Path(state['learning_directory'])/'event.json';payload=json.loads(event.read_text())
                        items=[dict(title='Antwortlänge',text='Der Nutzer möchte kurze Antworten.',kind='preference',scope='global',evidence=user,path='',source_answer='',confirmed=False,correction=False)] if payload['text']==user else []
                        calls=[dict(jsonrpc='2.0',id=1,method='tools/call',params=dict(name='lumen_memory_learning_context',arguments={})),dict(jsonrpc='2.0',id=2,method='tools/call',params=dict(name='lumen_memory_learn',arguments=dict(memories=items)))]
                        run=subprocess.run([sys.executable,str(Path(__file__).with_name('memory_agent_stdio.py')),str(event)],input='\n'.join(map(json.dumps,calls))+'\n',capture_output=True,text=True,check=True)
                        assert not any(json.loads(line)['result'].get('isError') for line in run.stdout.splitlines())
                    state['sessions'][session]=[{'info':{'role':'assistant','parentID':body['messageID'],'time':{'completed':123}},'parts':[{'type':'text','text':answer}]}]
                elif path.endswith('/message'):result=state['sessions'][path.split('/')[2]]
                elif path in ('/session','/permission','/question'):result=[]
                raw=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        def wait(predicate):
            deadline=time.monotonic()+12
            while not predicate() and time.monotonic()<deadline:QTest.qWait(20)
            self.assertTrue(predicate())
        def ensure(engine, callback):
            engine.url='http://127.0.0.1:'+str(server.server_port)
            if getattr(engine,'learning_environment',None):state['learning_directory']=engine.directory
            callback()
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_DATA':tmp+'/state'}),patch.object(OpenCodeBackend,'ensure_server',ensure):
            store=Store();memory=Memory(store);memory.configure(True,True,automatic=True)
            backend=OpenCodeBackend(tmp,server_url='http://127.0.0.1:'+str(server.server_port),password='test');backend.ensure_server=lambda callback:callback();backend.selected_model='test/model'
            seen=[];backend.memoryContextChanged.connect(seen.append)
            try:
                backend.send(user);wait(lambda:memory.scan()['notes']);wait(lambda:not backend.busy)
                first=state['prompts'][0][0];backend.send('Welche Antwortlänge passt?');wait(lambda:len(state['prompts'])>=2 and not backend.busy)
                self.assertIn('kurze Antworten',state['prompts'][1][1]['system']);self.assertEqual(first,state['prompts'][1][0])
                used=[x for x in seen if x['phase']=='submitted' and x['sources']][-1]
                self.assertEqual(used['version'],1);self.assertEqual(used['sources'][0]['source_kind'],'memory')
                self.assertNotIn('text',used['sources'][0]);self.assertTrue(used['message_id'])
                note=memory.scan()['notes'][0];prepare=backend.memory.prepare
                def revoke_while_preparing(text,directory,done):
                    backend.memory.prepare=prepare;memory.forget(note['path'],note['hash']);prepare(text,directory,done)
                backend.memory.prepare=revoke_while_preparing
                backend.send('Welche Antwortlänge passt jetzt?');wait(lambda:len(state['prompts'])>=3 and not backend.busy)
                self.assertNotEqual(first,state['prompts'][2][0]);self.assertNotIn('kurze Antworten',state['prompts'][2][1]['system'])
                backend.send('Native Vorschläge',proposal=True);wait(lambda:len(state['prompts'])>=4 and not backend.busy)
                self.assertNotIn('lumen-memory',state['prompts'][3][1]['system']);self.assertEqual(state['prompts'][3][1]['tools'],{'*':False})
                memory.remember('Schreibstil','Schreibe freundliche kurze Mails.',kind='preference')
                other=OpenCodeBackend(tmp,server_url=backend.url,password='test');other.ensure_server=lambda callback:callback()
                try:
                    other.selected_model='test/model'
                    other.send('Mail entwerfen',proposal=True,memory_context=True,memory_text='Mail schreiben');wait(lambda:len(state['prompts'])>=5 and not other.busy)
                    self.assertIn('freundliche kurze Mails',state['prompts'][4][1]['system']);self.assertEqual(state['prompts'][4][1]['tools'],{'*':False})
                finally:other.shutdown();other.deleteLater()
                delayed=[];backend.memory.prepare=lambda text,directory,done:delayed.append(done)
                backend.send('Diese Anfrage abbrechen');self.assertTrue(backend.busy);self.assertEqual(len(delayed),1)
                backend.stop();delayed[0](memory.prepare('Antworten',tmp));QTest.qWait(50)
                self.assertFalse(backend.busy);self.assertEqual(len(state['prompts']),5)
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
                self.assertEqual(panel.memory_status.text(),tr('Im Lumen-Gedächtnis gespeichert.' if remember else 'In deinem Notizbuch gespeichert.'),panel.error.text())
            self.assertEqual(len(book.scan()['notes']),2);self.assertEqual(len(memory.scan()['notes']),1)
            panel.context_tools.close();panel.backend.shutdown();panel.close();panel.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


if __name__=='__main__':unittest.main()
