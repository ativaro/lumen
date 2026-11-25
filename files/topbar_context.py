"""Explicit topbar handoffs and read-only summaries of current operations."""
import base64
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
from urllib.parse import urlsplit


def transfer_snapshot(directory, now=None):
    path = Path(directory) / 'lumen.sqlite3'
    now = time.time() if now is None else now
    if not path.is_file(): return None
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=.1) as db:
        rows = db.execute("""SELECT json_extract(value,'$.id'),json_extract(value,'$.action'),
            json_extract(value,'$.status'),json_extract(value,'$.updated'),json_extract(value,'$.bytes'),json_extract(value,'$.total')
            FROM settings WHERE key >= 'transfer/' AND key < 'transfer0' AND json_valid(value)""")
        active = []
        for row in rows:
            value = dict(zip(('id','action','status','updated','bytes','total'),row))
            if (value.get('action') not in ('drive-upload','drive-download','drive-copy')
                    or value.get('status') not in ('queued','running','cancelling')
                    or not re.fullmatch(r'[a-f0-9]{32}', str(value.get('id','')))
                    or type(value.get('updated')) not in (int,float) or not 0 <= now-value['updated'] <= 10
                    or any(type(value[k]) is not int or value[k]<0 for k in ('bytes','total'))): continue
            active.append(value)
    if not active: return None
    total = sum(v.get('total',0) for v in active if type(v.get('total')) is int and v['total'] > 0)
    done = sum(min(v.get('bytes',0),v.get('total',0)) for v in active
               if type(v.get('total')) is int and v['total'] > 0 and type(v.get('bytes')) is int and v['bytes'] >= 0)
    return dict(id=active[0]['id'], count=len(active), percent=min(100,done*100//total) if total and all(v.get('total',0)>0 for v in active) else None)


def recording(nodes, process_ids=()):
    for node in nodes:
        info = node.get('info') if isinstance(node,dict) else None
        if not isinstance(info,dict) or info.get('state')!='running': continue
        props = info.get('props')
        if not isinstance(props,dict) or props.get('media.class')!='Stream/Input/Audio': continue
        if (props.get('application.name') in ('Lumen Audio Studio','lumen-meetings')
                or belongs_to(props.get('application.process.id'),process_ids)): return True
    return False


def belongs_to(pid, parents):
    if not parents: return False
    try:
        pid = int(pid)
        for _ in range(12):
            if pid in parents: return True
            if pid < 2: return False
            pid = int(Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[1])
    except (OSError,ValueError,TypeError,IndexError): pass
    return False


def audio_processes():
    try: import dbus
    except ImportError: return set()
    try:
        bus = dbus.SessionBus(); result = set()
        for service in bus.list_names():
            if not re.fullmatch(r'org\.lumen\.Topbar\.Audio\.p[1-9][0-9]{0,8}',service): continue
            try:
                values = json.loads(str(bus.get_object(service,'/Audio').get_dbus_method('CaptureProcesses')(timeout=.3)))
                if isinstance(values,list): result.update(v for v in values if type(v) is int and 1 < v < 10**9)
            except (dbus.DBusException,ValueError): pass
        return result
    except dbus.DBusException: return set()


def install_audio(window):
    if hasattr(window,'_topbar_audio'): return
    from PySide6.QtCore import QObject,Slot
    from PySide6.QtDBus import QDBusConnection
    class AudioCapture(QObject):
        @Slot(result=str)
        def CaptureProcesses(self):
            from server_audio_permissions import context,current
            if not current(window,context(window)): return '[]'
            return json.dumps([os.getpid(),window.page.renderProcessPid()])
    capture = AudioCapture(window);bus = QDBusConnection.sessionBus()
    if bus.registerService('org.lumen.Topbar.Audio.p'+str(os.getpid())):
        bus.registerObject('/Audio',capture,QDBusConnection.RegisterOption.ExportAllSlots)
    window._topbar_audio = capture


def snapshot():
    from lumen_store import state_path
    value = dict(transfer=None, audio=False)
    try: value['transfer'] = transfer_snapshot(state_path())
    except (OSError,sqlite3.Error,TypeError,ValueError): pass
    processes = audio_processes()
    if not processes: return value
    try:
        result = subprocess.run(['pw-dump','-N'],capture_output=True,timeout=1,text=True)
        if result.returncode == 0 and len(result.stdout) <= 2*1024*1024:
            nodes = json.loads(result.stdout)
            if isinstance(nodes,list): value['audio'] = recording(nodes,processes)
    except (OSError,ValueError,subprocess.TimeoutExpired): pass
    return value


def page_source(encoded):
    if not isinstance(encoded,str) or len(encoded)>16000: raise ValueError('Ungültige Seitenübergabe.')
    value = json.loads(base64.b64decode(encoded,validate=True).decode())
    if (not isinstance(value,dict) or set(value)!={'title','app'}
            or any(not isinstance(v,str) or len(v)>4000 or any(ord(c)<32 for c in v) for v in value.values())
            or not re.search(r'chrom|brave|firefox|edge|vivaldi',value['app'],re.I)):
        raise ValueError('Ungültige Browserübergabe.')
    return value


def web_url(value):
    parts = urlsplit(value)
    if (not value or len(value)>8192 or parts.scheme not in ('http','https') or not parts.hostname
            or parts.username or parts.password or any(ord(c)<32 for c in value)):
        raise ValueError('Eine HTTP(S)-Adresse ohne Zugangsdaten eingeben.')
    return value


def browser_pages(source):
    """KDE supplies real tab URLs; ambiguous or unavailable context is reviewed in the dialog."""
    try: import dbus
    except ImportError: return []
    title = re.sub(r'\s[-—–]\s(?:Chromium|Google Chrome|Brave|Mozilla Firefox|Microsoft Edge|Vivaldi)$','',source['title'])
    if not title: return []
    try:
        bus = dbus.SessionBus()
        services = bus.list_names()
    except dbus.DBusException: return []
    pages = set()
    for service in services:
        if not re.fullmatch(r'org\.kde\.plasma\.browser_integration-\d+',service): continue
        try:
            rows = bus.get_object(service,'/TabsRunner').get_dbus_method('Match','org.kde.krunner1')(title,timeout=2)
            for row in rows:
                if len(row)!=6 or str(row[1])!=title: continue
                for url in row[5].get('urls',[]):
                    try: pages.add(web_url(str(url)))
                    except ValueError: pass
        except dbus.DBusException: continue
    return sorted(pages)


def remember_page(encoded):
    from PySide6.QtWidgets import QInputDialog, QLineEdit
    from interop_data import Registry
    from interop_open import launch
    source = page_source(encoded); pages = browser_pages(source)
    if len(pages)>1:
        url,accepted = QInputDialog.getItem(None,'Lumen Notes · Seite merken','Seite auswählen',pages,0,False)
    else:
        url,accepted = QInputDialog.getText(None,'Lumen Notes · Seite merken','Seitenadresse prüfen' if pages else 'Seitenadresse eingeben · der Browser stellt sie nicht bereit',QLineEdit.EchoMode.Normal,pages[0] if pages else '')
    if not accepted: return
    url = web_url(url.strip())
    token = Registry().enqueue('wissen','wissen.import',dict(title=source['title'][:200] or url,url=url,text=url))
    launch('wissen',['--handoff',token])


def reader_discuss(window):
    from lumen_launch import executable
    if getattr(window,'job',None) or not window.current: raise ValueError('Zuerst ein lesbares Dokument öffnen.')
    record = window.library.get(window.current)
    path = window.library.asset(record['asset'])
    if not path.is_file(): raise ValueError('Die Lesekopie ist nicht verfügbar.')
    subprocess.Popen([executable('lumen-agent-app'),'--details','--action','open','--file',str(path)],
                     start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def install_reader(window):
    from PySide6.QtCore import QObject, Slot
    from PySide6.QtDBus import QDBusConnection
    class ReaderActions(QObject):
        @Slot(result=str)
        def Discuss(self):
            try: reader_discuss(window); return ''
            except (OSError,ValueError,KeyError) as error: return str(error)
    actions = ReaderActions(window); bus = QDBusConnection.sessionBus()
    if bus.registerService('org.lumen.Topbar.Reader.p'+str(os.getpid())):
        bus.registerObject('/Reader',actions,QDBusConnection.RegisterOption.ExportAllSlots)
    window._topbar_actions = actions


def open_reader(pid):
    from PySide6.QtDBus import QDBusConnection, QDBusMessage
    if not re.fullmatch(r'[1-9][0-9]{0,8}',str(pid)): raise ValueError('Ungültiges Reader-Fenster.')
    call = QDBusMessage.createMethodCall('org.lumen.Topbar.Reader.p'+str(pid),'/Reader','','Discuss')
    reply = QDBusConnection.sessionBus().call(call,timeout=3000)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        raise ValueError('Lumen Reader bitte einmal normal schließen und neu öffnen, um die neue Übergabe zu laden.')
    if reply.arguments() and reply.arguments()[0]: raise ValueError(str(reply.arguments()[0]))



def validate_note(value):
    from server_app_links import validate_ref
    if not isinstance(value,dict) or set(value)!={'reference','revision'}:
        raise ValueError('Ungültige Notes-Auswahl.')
    ref=validate_ref(value['reference'])
    if ref['app']!='note' or type(value['revision']) is not int or not 1<=value['revision']<=2**31-1:
        raise ValueError('Ungültige Notes-Auswahl.')
    return dict(reference=ref,revision=value['revision'])


def note_attachment(value,server,account):
    value=validate_note(value)
    if value['reference']['locator']!=dict(server=server,account=account):
        raise ValueError('Die ausgewählte Notiz gehört zu einem anderen Server oder Konto.')
    return dict(id=value['reference']['id'],kind='note',revision=value['revision'],mode='reference')


def saved_note(context,note_id,job):
    from server_notes_links import _profile
    from server_app_links import _uuid
    note_id=_uuid(note_id)
    _,revision=_profile(context,job)
    value=context.session.request('/api/documents/'+note_id,max_bytes=1024**2)
    if (not isinstance(value,dict) or value.get('id')!=note_id or value.get('kind')!='note'
            or value.get('deleted') is not False or value.get('ai_allowed') is not True):
        raise ValueError('Diese Notiz ist nicht für Lumen freigegeben. Bitte zuerst in Notes freigeben.')
    result=validate_note(dict(reference=dict(version=2,app='note',id=note_id,title=value.get('title'),
        locator=dict(server=context.binding.origin,account=context.binding.account)),revision=value.get('revision')))
    _profile(context,job,revision=revision);job.check();context.check()
    return result


def install_note(window):
    from PySide6.QtCore import QObject,Slot,QEventLoop,QTimer
    from PySide6.QtDBus import QDBusConnection
    class NoteActions(QObject):
        @Slot(result=str)
        def Reference(self):
            import threading
            from server_notes_links import Context
            from server_app_window import _connection
            from interop_dialogs import run_job
            owned=False
            try:
                w=window
                if w._import_running or w._worker is not None:raise ValueError('Bitte den laufenden Notes-Vorgang abwarten.')
                context=Context(w,w.page,w.profile,w.view,w.session,w._binding,w._generation,w.session._generation,
                    _connection()[1],w._import_destroyed,threading.get_ident());context.gui()
                values=[];loop=QEventLoop();timeout=QTimer();timeout.setSingleShot(True)
                timeout.timeout.connect(loop.quit)
                def received(value):values.append(value);loop.quit()
                w.page.runJavaScript("""JSON.stringify((() => { const note=document.querySelector('.knowledge-editor');
                    if(!note)return null;
                    if(!window.dispatchEvent(new Event('beforeunload',{cancelable:true})))return {dirty:true};
                    return {id:note.dataset.documentId}; })())""",0,received)
                if not values:timeout.start(2000);loop.exec()
                timeout.stop();context.gui()
                value=values[0] if values else None
                value=json.loads(value) if isinstance(value,str) and len(value)<=8192 else None
                if not isinstance(value,dict):raise ValueError('Zuerst eine gespeicherte Notes-Notiz öffnen.')
                if value.get('dirty'):raise ValueError('Die Notiz zuerst in Notes speichern, damit genau dieser Stand übergeben wird.')
                w._import_running=True;owned=True
                note=run_job(w,'Notes-Notiz für Lumen prüfen …',lambda job:saved_note(context,value.get('id'),job))
                context.gui()
                if note is None:raise ValueError('Notes-Übergabe abgebrochen.')
                return json.dumps(dict(note=note,error=''))
            except (OSError,ValueError,RuntimeError) as error:return json.dumps(dict(error=str(error)))
            finally:
                from lumen_qt import is_deleted
                if owned and not is_deleted(window):
                    window._import_running=False
                    if window._import_close:window._import_close=False;window.close()
    actions=NoteActions(window);bus=QDBusConnection.sessionBus()
    service='org.lumen.Topbar.Note.p'+str(os.getpid())
    if bus.registerService(service):
        bus.registerObject('/Note',actions,QDBusConnection.RegisterOption.ExportAllSlots)
        window.destroyed.connect(lambda:bus.unregisterService(service))
    window._topbar_note=actions


def read_note(pid):
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtDBus import QDBusConnection,QDBusMessage
    if type(pid) is not int or not 1<pid<10**9:raise ValueError('Ungültiges Notes-Fenster.')
    app=QCoreApplication.instance() or QCoreApplication([])
    bus=QDBusConnection.sessionBus();service='org.lumen.Topbar.Note.p'+str(pid)
    owner=bus.interface().servicePid(service)
    if not owner.isValid() or owner.value()!=pid:
        raise ValueError('Lumen Notes bitte einmal schließen und neu öffnen, um die direkte Übergabe zu laden.')
    call=QDBusMessage.createMethodCall(service,'/Note','','Reference')
    reply=bus.call(call,timeout=40000)
    if reply.type()==QDBusMessage.MessageType.ErrorMessage or len(reply.arguments())!=1:
        raise ValueError('Die geöffnete Notes-Notiz konnte nicht übernommen werden.')
    value=json.loads(reply.arguments()[0])
    if value.get('error'):raise ValueError(str(value['error'])[:400])
    return validate_note(value.get('note'))

def main():
    from PySide6.QtWidgets import QApplication,QMessageBox
    app = QApplication([])
    app.setApplicationName('Lumen')
    try:
        if sys.argv[1]=='page': remember_page(sys.argv[2])
        elif sys.argv[1]=='reader': open_reader(sys.argv[2])
        else: raise ValueError('Unbekannte Inhaltsaktion.')
    except (OSError,ValueError,RuntimeError) as error: QMessageBox.warning(None,'Lumen',str(error))


if __name__=='__main__': main()
