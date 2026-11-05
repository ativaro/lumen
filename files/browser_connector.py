"""Outbound Desktop browser relay. Only the bundled Playwright MCP can execute."""
import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from uuid import UUID, uuid4
import lumen_connect as client

ASSETS=Path(__file__).with_name('browser-runtime')
BASE=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'lumen/browser-runtime'


def allowed(config):
    try:
        local=client.read_config()
        return client.connection_scope(local)==client.connection_scope(config) and local.get('browser_access') is True
    except (OSError,ValueError,KeyError):return False


def ready():
    return (BASE/'start.sh').is_file() and (BASE/'node').is_file()


def install():
    if ready():return
    if not shutil.which('bwrap'):
        raise ValueError('Für getrennte Browserprofile wird bubblewrap benötigt.')
    if not shutil.which('node') or not shutil.which('npm'):
        raise ValueError('Für die Browsersteuerung werden Node.js und npm benötigt.')
    major=int(subprocess.check_output(['node','-p','process.versions.node.split(".")[0]'],text=True,timeout=5))
    if major<20:raise ValueError('Für die Browsersteuerung wird Node.js ab Version 20 benötigt.')
    BASE.parent.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(BASE.parent).free < 30*1024**3:
        raise ValueError('Für die Browser-Einrichtung sind 30 GiB freier Speicher erforderlich.')
    # Build beside the destination; a failed download never leaves a ready installation.
    with tempfile.TemporaryDirectory(prefix='.browser-install-',dir=BASE.parent) as stage:
        target=Path(stage)/'runtime'
        subprocess.run(['sh',str(ASSETS/'install.sh'),str(target)],check=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=600)
        if BASE.exists():raise ValueError('Die Browserinstallation ist unvollständig. Bitte Einrichtung prüfen.')
        target.rename(BASE)


def set_access(enabled):
    if enabled:install()
    with (client.ROOT/'pairing.lock').open('a') as lock:
        import fcntl
        fcntl.flock(lock,fcntl.LOCK_EX)
        config=client.read_config()
        if enabled:client.request(config,'/bridge/browser/access',{'enabled':True})
        config['browser_access']=bool(enabled)
        client.save_private(client.CONFIG,json.dumps(config))
        if not enabled:client.request(config,'/bridge/browser/access',{'enabled':False})


def sandbox_command():
    if not shutil.which('bwrap'):raise ValueError('bubblewrap ist nicht installiert.')
    node=(BASE/'node').resolve(strict=True)
    command=['bwrap','--unshare-all','--share-net','--die-with-parent','--new-session','--clearenv']
    for path in ('/usr','/lib','/lib64','/bin','/sbin','/etc/resolv.conf','/etc/ssl/certs','/etc/fonts','/etc/passwd'):
        if Path(path).exists():command+=['--ro-bind',path,path]
    command+=['--proc','/proc','--dev','/dev','--tmpfs','/tmp',
              '--ro-bind',str(BASE),'/opt/lumen-browser','--ro-bind',str(node),'/opt/lumen-node',
              '--setenv','PATH','/usr/bin:/bin','--setenv','HOME','/tmp',
              '--setenv','LANG','C.UTF-8','--setenv','LUMEN_BROWSER_NODE','/opt/lumen-node',
              '--setenv','LUMEN_BROWSER_SESSIONS','/tmp','--chdir','/tmp',
              '--','/bin/sh','/opt/lumen-browser/start.sh']
    return command


class MCP:
    def __init__(self):
        self.process=subprocess.Popen(sandbox_command(),stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,start_new_session=True)
        self.messages=queue.Queue(maxsize=128);self.serial=0;self.touched=time.monotonic()
        threading.Thread(target=self.read,daemon=True).start()
        try:
            self.call('initialize',dict(protocolVersion='2025-06-18',capabilities={},clientInfo={'name':'Lumen Desktop','version':'1'}))
            self.write({'jsonrpc':'2.0','method':'notifications/initialized'})
        except BaseException:self.close();raise

    def read(self):
        try:
            while True:
                line=self.process.stdout.readline(4*1024*1024+1)
                if not line:return
                if len(line)>4*1024*1024:raise ValueError('Browserantwort zu groß.')
                value=json.loads(line)
                if 'id' in value and 'method' in value:
                    self.write(dict(jsonrpc='2.0',id=value['id'],error={'code':-32601,'message':'Unsupported client method'}))
                elif 'id' in value:self.messages.put_nowait(value)
        except (ValueError,OSError,queue.Full):self.close()
        finally:
            try:self.messages.put_nowait(None)
            except queue.Full:pass

    def write(self,value):
        self.process.stdin.write((json.dumps(value)+'\n').encode());self.process.stdin.flush()

    def call(self,method,params):
        self.serial+=1;identity=self.serial
        self.write(dict(jsonrpc='2.0',id=identity,method=method,params=params))
        end=time.monotonic()+48
        while True:
            result=self.messages.get(timeout=max(.01,end-time.monotonic()))
            if result is None:raise ValueError('Der Browser wurde beendet.')
            if result.get('id')!=identity:raise ValueError('Unerwartete Browserantwort.')
            if 'error' in result:raise ValueError('Das Browserwerkzeug hat die Anfrage abgelehnt.')
            if not isinstance(result.get('result'),dict):raise ValueError('Ungültige Browserantwort.')
            self.touched=time.monotonic();return result['result']

    def close(self):
        if self.process.poll() is None:
            try:os.killpg(self.process.pid,signal.SIGTERM);self.process.wait(timeout=3)
            except (ProcessLookupError,subprocess.TimeoutExpired):
                try:os.killpg(self.process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
        for stream in (self.process.stdin,self.process.stdout):
            try:stream.close()
            except (OSError,ValueError):pass


class Connector:
    def __init__(self):
        self.instance=str(uuid4());self.sessions={}

    def close(self):
        for session in self.sessions.values():session.close()
        self.sessions.clear()

    def execute(self,command):
        identity=str(UUID(command['session']));method=command['method'];params=command['params']
        if method=='close':
            item=self.sessions.pop(identity,None)
            if item:item.close()
            return {}
        if method=='start':
            if identity not in self.sessions:
                if len(self.sessions)>=3:raise ValueError('Zu viele Browsersitzungen.')
                self.sessions[identity]=MCP()
            return {}
        if method not in ('tools/list','tools/call') or identity not in self.sessions:
            raise ValueError('Die Browsersitzung ist nicht verfügbar.')
        if len(json.dumps(params).encode())>65536:raise ValueError('Browseranfrage zu groß.')
        return self.sessions[identity].call(method,params)

    def step(self,config):
        if not allowed(config) or not ready():raise ValueError('Browsersteuerung ist ausgeschaltet.')
        for identity,item in list(self.sessions.items()):
            if time.monotonic()-item.touched>1200:item.close();self.sessions.pop(identity)
        command=client.request(config,'/bridge/browser/poll',{'instance':self.instance},timeout=25)
        if command is None:return
        if command == {'reset':True}:
            self.close();return
        # Recheck both ends before launching or changing a page.
        if not allowed(config):raise ValueError('Die lokale Browserfreigabe wurde entzogen.')
        rights=client.request(config,'/bridge/me').get('capabilities',[])
        if not {'desktop','browser'}<=set(rights):raise ValueError('Die Browserfreigabe wurde entzogen.')
        try:result={'value':self.execute(command)}
        except (OSError,ValueError,queue.Empty,subprocess.SubprocessError):
            item=self.sessions.pop(command.get('session'),None)
            if item:item.close()
            result={'failed':True}
        if not allowed(config):raise ValueError('Die lokale Browserfreigabe wurde entzogen.')
        client.request(config,'/bridge/browser/reply',{'instance':self.instance,'id':str(UUID(command['id'])),'result':result})


def watch(connection_client=None):
    global client
    if connection_client is not None:client=connection_client
    while True:
        connector=Connector()
        try:
            config=client.read_config()
            while True:connector.step(config)
        except (OSError,ValueError,KeyError,queue.Empty):pass
        finally:connector.close()
        time.sleep(2)
