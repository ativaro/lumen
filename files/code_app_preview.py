"""Offline, ephemeral rendering without an app-to-host bridge."""
import json
from shiboken6 import delete
from PySide6.QtCore import QUrl, Signal, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile,
    QWebEngineSettings, QWebEngineScript, QWebEngineUrlRequestInterceptor)
from code_library_contract import APP_CSP
from lumen_i18n import tr


class Offline(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self,info):
        if info.requestUrl().scheme() not in ('data','about'):info.block(True)


class Page(QWebEnginePage):
    pending=False

    def acceptNavigationRequest(self,url,kind,main):
        if self.pending and main and url.scheme() in ('data','about'):
            self.pending=False;return True
        return False

    def createWindow(self,kind):return None
    def chooseFiles(self,mode,old,types):return []
    def javaScriptAlert(self,origin,message):pass
    def javaScriptConfirm(self,origin,message):return False
    def javaScriptPrompt(self,origin,message,default):return (False,'')


# Chromium's network interceptor does not cover WebRTC's own UDP transport.
ISOLATE='''for(const key of ['RTCPeerConnection','webkitRTCPeerConnection',
 'RTCDataChannel','Worker','SharedWorker','WebTransport']) {
 try { Object.defineProperty(globalThis,key,{value:undefined,writable:false,configurable:false}); } catch {} }
'''
CAPTURE='''JSON.stringify(Array.from(document.querySelectorAll('input,textarea,select'))
 .filter(e=>!['password','file','hidden'].includes(e.type)).slice(0,200)
 .map((e,i)=>({id:e.id,name:e.name,type:e.type,index:i,value:e.value.slice(0,20000),checked:!!e.checked,
 selected:e.multiple?Array.from(e.selectedOptions).map(o=>o.value):null})))'''
RESTORE='''const fields=Array.from(document.querySelectorAll('input,textarea,select'))
 .filter(e=>!['password','file','hidden'].includes(e.type)).slice(0,200);
 for(const v of VALUES){const e=fields.find(e=>v.id&&e.id===v.id&&e.type===v.type)
 ||fields.find(e=>v.name&&e.name===v.name&&e.type===v.type)
 ||fields[v.index];if(!e||e.type!==v.type||e.id!==v.id||e.name!==v.name)continue;
 e.value=v.value;e.checked=v.checked;if(e.multiple&&v.selected)for(const o of e.options)o.selected=v.selected.includes(o.value);
 e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));}'''


class Preview(QWidget):
    loaded=Signal(bool)

    def __init__(self,parent=None):
        super().__init__(parent);self.ready=False;self.closed=False;self.generation=0;self.source=None
        box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0)
        self.message=QLabel();self.message.setWordWrap(True);self.message.hide();box.addWidget(self.message)
        self.view=QWebEngineView();box.addWidget(self.view,1)
        self.profile=QWebEngineProfile(self);self.interceptor=Offline(self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.profile.downloadRequested.connect(lambda request:request.cancel())
        self.page=Page(self.profile,self.view);self.view.setPage(self.page)
        settings=self.page.settings();attrs=QWebEngineSettings.WebAttribute
        for name in ('LocalContentCanAccessRemoteUrls','LocalContentCanAccessFileUrls','LocalStorageEnabled',
                     'JavascriptCanOpenWindows','JavascriptCanAccessClipboard','JavascriptCanPaste',
                     'PluginsEnabled','HyperlinkAuditingEnabled','DnsPrefetchEnabled','FullScreenSupportEnabled','ScreenCaptureEnabled'):
            settings.setAttribute(getattr(attrs,name),False)
        settings.setUnknownUrlSchemePolicy(QWebEngineSettings.DisallowUnknownUrlSchemes)
        self.page.permissionRequested.connect(lambda permission:permission.deny())
        self.page.fileSystemAccessRequested.connect(lambda request:request.reject())
        self.page.fullScreenRequested.connect(lambda request:request.reject())
        self.page.webAuthUxRequested.connect(lambda request:request.cancel())
        script=QWebEngineScript();script.setName('Lumen offline app');script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        script.setWorldId(QWebEngineScript.MainWorld);script.setRunsOnSubFrames(True);script.setSourceCode(ISOLATE)
        self.page.scripts().insert(script)
        self.page.loadFinished.connect(self.finished)
        self.page.renderProcessTerminated.connect(lambda *_:self.failed())

    def set_source(self,source):
        if self.closed:return
        if source==self.source and self.ready:return
        if not isinstance(source,str) or len(source)>262144:raise ValueError('App-Inhalt ist zu groß.')
        self.source=source;self.ready=False;self.generation+=1;self.message.hide();self.page.pending=True
        document='<meta http-equiv="Content-Security-Policy" content="'+APP_CSP+'">'+source
        self.page.setHtml(document,QUrl('https://lumen-app.invalid/'))

    def finished(self,ok):
        if self.closed:return
        self.page.pending=False;self.ready=ok
        if not ok:self.failed()
        self.loaded.emit(ok)

    def failed(self):
        if self.closed:return
        self.ready=False;self.message.setText(tr('Die App-Vorschau konnte nicht geladen werden. Der Entwurf bleibt erhalten.'));self.message.show()

    def snapshot(self,callback):
        if not self.ready or self.closed:callback([]);return
        generation=self.generation
        def result(raw):
            if self.closed or generation!=self.generation:return
            try:value=json.loads(raw) if isinstance(raw,str) and len(raw)<=300000 else []
            except ValueError:value=[]
            callback(value)
        self.page.runJavaScript(CAPTURE,QWebEngineScript.ApplicationWorld,result)

    def restore(self,values):
        if self.ready and not self.closed:
            self.page.runJavaScript('(()=>{'+RESTORE.replace('VALUES',json.dumps(values))+'})();',QWebEngineScript.ApplicationWorld)

    def inspect(self,callback,values=None):
        if not self.ready or self.closed:callback(None);return
        generation=self.generation
        if values is not None:self.restore(values)
        def capture():
            if self.closed or generation!=self.generation:callback(None);return
            script='JSON.stringify({fields:JSON.parse('+CAPTURE+'),text:(document.body?.innerText||"").slice(0,30000)})'
            def result(raw):
                if self.closed or generation!=self.generation:callback(None);return
                try:value=json.loads(raw) if isinstance(raw,str) and len(raw)<=400000 else None
                except ValueError:value=None
                callback(value)
            self.page.runJavaScript(script,QWebEngineScript.ApplicationWorld,result)
        QTimer.singleShot(200,capture)

    def shutdown(self):
        if self.closed:return
        self.closed=True;self.generation+=1;self.view.stop()
        # The page must die before its off-record profile.
        delete(self.page);delete(self.view);delete(self.profile);self.hide()
