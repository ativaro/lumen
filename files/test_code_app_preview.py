import os
import tempfile
import time
import unittest
from unittest.mock import patch


class PreviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.env=patch.dict(os.environ,{'QT_QPA_PLATFORM':'offscreen','LUMEN_DATA':cls.tmp.name+'/store','LUMEN_TOOLS_DATA':cls.tmp.name+'/tools','XDG_CONFIG_HOME':cls.tmp.name+'/config','LUMEN_LANGUAGE':'de','QTWEBENGINE_CHROMIUM_FLAGS':'--disable-gpu'})
        cls.env.start();cls.addClassCleanup(cls.env.stop)
        from PySide6.QtCore import QCoreApplication,Qt
        from PySide6.QtWidgets import QApplication
        if QApplication.instance() is None:QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
        from app import create_app
        cls.app=QApplication.instance() or create_app()
        cls.app.removeEventFilter(cls.app)

    def wait(self,condition):
        from PySide6.QtTest import QTest
        deadline=time.monotonic()+10
        while not condition() and time.monotonic()<deadline:QTest.qWait(20)
        self.assertTrue(condition())

    def js(self,preview,script,world=1):
        result=[];preview.page.runJavaScript(script,world,lambda value:result.append(value));self.wait(lambda:bool(result));return result[0]

    def preview(self,source):
        from code_app_preview import Preview
        w=Preview();w.resize(600,550);w.show();self.addCleanup(w.shutdown)
        w.set_source(source);self.wait(lambda:w.ready);return w

    def test_real_html_and_form_input_restore(self):
        source='<input id="amount" value="1"><output id="total"></output><script>oninput=()=>document.querySelector("#total").textContent=Number(document.querySelector("#amount").value)*2;oninput()</script>'
        w=self.preview(source);self.assertEqual(self.js(w,'document.querySelector("#total").textContent'),'2')
        self.js(w,'document.querySelector("#amount").value="42";document.querySelector("#amount").dispatchEvent(new Event("input",{bubbles:true}));true')
        values=[];w.snapshot(lambda result:values.append(result));self.wait(lambda:bool(values))
        w.set_source(source+'<p>Neue Fassung</p>');self.wait(lambda:w.ready);w.restore(values[0]);self.wait(lambda:self.js(w,'document.querySelector("#total").textContent')=='84')
        self.assertTrue(w.profile.isOffTheRecord())

    def test_repeatable_examples_observe_real_output_and_skip_password_fields(self):
        source='<input type="password" value="not-a-fixture"><input id="amount" value="2"><output id="out"></output><script>oninput=()=>out.textContent="Ergebnis: "+Number(amount.value)*2;oninput()</script>'
        w=self.preview(source);observed=[];w.inspect(observed.append);self.wait(lambda:bool(observed))
        self.assertEqual(len(observed[0]['fields']),1);self.assertNotIn('not-a-fixture',str(observed[0]))
        values=[{**observed[0]['fields'][0],'value':'42'}];result=[];w.inspect(result.append,values);self.wait(lambda:bool(result))
        self.assertIn('Ergebnis: 84',result[0]['text'])

    def test_external_navigation_and_browser_apis_are_denied(self):
        w=self.preview('<input id="password" type="password" value="secret"><input id="normal" value="safe"><p id="x">Offline</p>')
        self.assertEqual(self.js(w,'typeof RTCPeerConnection',0),'undefined')
        self.assertEqual(self.js(w,'typeof Worker',0),'undefined')
        self.assertIsNone(w.page.createWindow(None))
        self.assertEqual(w.page.chooseFiles(None,[],[]),[])
        from PySide6.QtCore import QUrl
        self.assertFalse(w.page.acceptNavigationRequest(QUrl('https://example.com'),None,True))
        self.assertFalse(w.page.acceptNavigationRequest(QUrl('file:///etc/passwd'),None,True))
        self.assertFalse(w.page.acceptNavigationRequest(QUrl('data:text/html,unsafe'),None,True))
        values=[];w.snapshot(lambda result:values.append(result));self.wait(lambda:bool(values))
        self.assertEqual(len(values[0]),1);self.assertEqual(values[0][0]['value'],'safe')
        self.assertFalse(w.page.settings().testAttribute(w.page.settings().WebAttribute.LocalContentCanAccessRemoteUrls))

    def test_app_resources_cannot_reach_a_local_server_or_files(self):
        import http.server
        import threading
        requests=[]
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):requests.append(self.path);self.send_response(200);self.end_headers()
            def log_message(self,*_):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        url='http://127.0.0.1:'+str(server.server_port)
        w=self.preview('<img src="'+url+'/image"><iframe src="'+url+'/frame"></iframe><script src="'+url+'/script"></script><script>fetch("'+url+'/fetch").catch(()=>{globalThis.blocked=true});fetch("file:///etc/passwd").catch(()=>{globalThis.fileBlocked=true});</script>')
        self.wait(lambda:self.js(w,'!!globalThis.blocked && !!globalThis.fileBlocked',0))
        self.assertEqual(requests,[])
