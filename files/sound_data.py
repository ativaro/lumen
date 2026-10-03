"""Pulse-compatible stream controls and opt-in rules; never captures audio samples."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time
from tools_data import Library
from lumen_controls import run


@contextmanager
def locked(library):
    fd=os.open(library.root/'audio.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:fcntl.flock(fd,fcntl.LOCK_EX);yield
    finally:os.close(fd)


def settings(library):
    rows=library.all()
    return rows[0] if rows else library.get(library.create('Audio',rules={},duck=False,level=25,mode='off',ducked={},overrides=[],applied={}))


def app_key(properties):
    for field in ('application.id','application.process.binary','application.name'):
        if properties.get(field):return field+':'+str(properties[field])[:500]
    return ''


def snapshot():
    info=json.loads(run(['pactl','-f','json','info']));cookie=str(info['cookie']);result=dict(cookie=cookie,sinks=[],streams=[],recordings=[],sources=[])
    for kind,field in [('sinks','sinks'),('sink-inputs','streams'),('source-outputs','recordings'),('sources','sources')]:
        values=json.loads(run(['pactl','-f','json','list',kind]))
        for value in values:
            properties=value.get('properties',{});value['app']=app_key(properties)
            value['title']=str(properties.get('application.name') or properties.get('application.process.binary') or value.get('description') or value.get('name') or 'Unbekannte Anwendung')[:200]
            value['token']=cookie+':'+str(value['index'])+':'+str(properties.get('object.serial') or str(value.get('client',''))+':'+str(properties.get('application.process.id','')))
            value['levels']=[int(v['value']) for v in value.get('volume',{}).values()]
            value['percent']=round(max(value['levels'],default=0)*100/65536);result[field].append(value)
    return result


def scaled(levels,percent):
    if type(percent) is not int or not 0<=percent<=100:raise ValueError('Lautstärke zwischen 0 und 100 wählen.')
    maximum=max(levels,default=0);target=round(65536*percent/100)
    return [round(v/maximum*target) if maximum else target for v in levels]


def set_levels(stream,levels):
    if not levels or len(levels)!=len(stream['levels']):raise ValueError('Audiokanäle haben sich geändert.')
    run(['pactl','set-sink-input-volume',str(stream['index']),*map(str,levels)])


def change(library,token,action,value):
    with locked(library):
        data=snapshot();stream=next((s for s in data['streams'] if s['token']==token),None)
        if stream is None:raise ValueError('Dieser Audiostream wurde beendet. Ansicht aktualisieren.')
        if action=='volume':set_levels(stream,scaled(stream['levels'],value))
        elif action=='mute':run(['pactl','set-sink-input-mute',str(stream['index']),'1' if value else '0'])
        elif action=='sink':
            if value not in {s['name'] for s in data['sinks']}:raise ValueError('Ausgabegerät nicht mehr verbunden.')
            run(['pactl','move-sink-input',str(stream['index']),value])
        else:raise ValueError('Unbekannte Audioaktion.')
        if action=='volume':
            config=settings(library);ducked=config.get('ducked',{});ducked.pop(token,None)
            library.update(config['id'],ducked=ducked,overrides=list(set(config.get('overrides',[])+[token])))


def save_rule(library,key,title,volume,sink,mute,role):
    if not key or len(key)>600 or role not in ('none','music','call'):raise ValueError('Keine stabile App-Kennung oder ungültige Rolle.')
    scaled([65536],volume)
    with locked(library):
        config=settings(library);rules=config['rules']
        if sink and sink not in {s['name'] for s in snapshot()['sinks']} and rules.get(key,{}).get('sink')!=sink:raise ValueError('Ausgabegerät fehlt.')
        rules[key]=dict(title=title[:200],volume=volume,sink=sink,mute=bool(mute),role=role)
        library.update(config['id'],rules=rules)


def remove_rule(library,key):
    with locked(library):
        config=settings(library);rules=config['rules'];rules.pop(key,None);library.update(config['id'],rules=rules)


def restore(library,data,config,only=None):
    remaining=dict(config.get('ducked',{}));streams={s['token']:s for s in data['streams']}
    for token,entry in list(remaining.items()):
        if only is not None and token not in only:continue
        stream=streams.get(token)
        if stream and stream['levels']==entry['after']:set_levels(stream,entry['before'])
        remaining.pop(token,None)
        library.update(config['id'],ducked=remaining)
    return remaining


def cycle(library,stop=False):
    with locked(library):
        config=settings(library);data=snapshot();identity=config['id']
        if stop or config['mode']=='off':
            restore(library,data,config);library.update(identity,applied={},overrides=[],activity='Automatik aus',heartbeat=time.time());return
        rules=config['rules'];available={s['name'] for s in data['sinks']};applied=config.get('applied',{});tokens={s['token'] for s in data['streams']}
        applied={k:v for k,v in applied.items() if k in tokens};changed=False;missing=set()
        for stream in data['streams']:
            rule=rules.get(stream['app'])
            if not rule:continue
            target=rule['sink'];signature=json.dumps(rule,sort_keys=True)+str(target in available)
            if target and target not in available:missing.add(rule['title'])
            if applied.get(stream['token'])==signature:continue
            # Restore our temporary reduction before changing this app's baseline rule.
            if stream['token'] in config.get('ducked',{}):
                restore(library,data,config,only={stream['token']})
                config=settings(library)
            set_levels(stream,scaled(stream['levels'],rule['volume']))
            run(['pactl','set-sink-input-mute',str(stream['index']),'1' if rule['mute'] else '0'])
            if target in available:run(['pactl','move-sink-input',str(stream['index']),target])
            applied[stream['token']]=signature;changed=True
        library.update(identity,applied=applied)
        if changed:data=snapshot()
        config=settings(library);streams={s['token']:s for s in data['streams']}
        sources={s['index']:s for s in data['sources']}
        def call(s,recording=False):
            if s.get('corked',False) or s.get('mute',False) or rules.get(s['app'],{}).get('role')!='call':return False
            if not recording:return str(s.get('properties',{}).get('media.role','')).lower() in ('phone','communication')
            source=sources.get(s.get('source'),{})
            return bool(source) and source.get('properties',{}).get('device.class')!='monitor' and not source.get('name','').endswith('.monitor')
        talking=config.get('duck',False) and (any(call(s,True) for s in data['recordings']) or any(call(s) for s in data['streams']))
        ducked=dict(config.get('ducked',{}));overrides=set(config.get('overrides',[]))&set(streams)
        for token,entry in list(ducked.items()):
            stream=streams.get(token)
            if not stream:ducked.pop(token);continue
            if stream['levels']!=entry['after']:ducked.pop(token);overrides.add(token);continue
            if not talking or rules.get(stream['app'],{}).get('role')!='music':
                set_levels(stream,entry['before']);ducked.pop(token)
            elif entry.get('level')!=config['level']:
                entry.update(after=[round(v*config['level']/100) for v in entry['before']],level=config['level'])
                library.update(identity,ducked=ducked);set_levels(stream,entry['after']);stream['levels']=entry['after']
        library.update(identity,ducked=ducked,overrides=list(overrides))
        if talking:
            for token,stream in streams.items():
                if token in ducked or token in overrides or rules.get(stream['app'],{}).get('role')!='music':continue
                after=[round(v*config['level']/100) for v in stream['levels']]
                # Journal before mutating the server so a restarted worker can recover.
                ducked[token]=dict(before=stream['levels'],after=after,level=config['level'])
                library.update(identity,ducked=ducked);set_levels(stream,after)
        else:overrides.clear()
        activity=('Gespräch aktiv · Musik abgesenkt' if talking else 'Bereit · App-Regeln aktiv')+(' · Gerät fehlt: '+', '.join(sorted(missing)) if missing else '')
        library.update(identity,ducked=ducked,overrides=list(overrides),activity=activity,last_error='',heartbeat=time.time())


def service(library,mode):
    if mode not in ('off','session','login'):raise ValueError('Ungültiger Automatikmodus.')
    config=settings(library);old=config['mode'];directory=Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'systemd/user'
    directory.mkdir(parents=True,exist_ok=True);script=str(Path(__file__).resolve())
    if any(c in script for c in '\n\r%"\\'):raise ValueError('Installationspfad für Benutzer-Dienst nicht unterstützt.')
    unit='[Unit]\nDescription=Lumen Sound App-Regeln\nAfter=pipewire-pulse.service\n[Service]\nType=simple\nExecStart=/usr/bin/python3 "'+script+'" --run\nRestart=on-failure\nRestartSec=3\nTimeoutStopSec=30\n[Install]\nWantedBy=default.target\n'
    (directory/'lumen-sound.service').write_text(unit);run(['systemctl','--user','daemon-reload'])
    try:
        library.update(config['id'],mode=mode)
        if mode=='off':run(['systemctl','--user','stop','lumen-sound.service'],timeout=40);run(['systemctl','--user','disable','lumen-sound.service']);cycle(library,stop=True)
        elif mode=='login':run(['systemctl','--user','enable','--now','lumen-sound.service'])
        else:run(['systemctl','--user','disable','lumen-sound.service']);run(['systemctl','--user','start','lumen-sound.service'])
    except BaseException:
        library.update(config['id'],mode=old)
        # A failed enable --now can still enable autostart. Restore our old mode.
        try:
            run(['systemctl','--user','enable' if old=='login' else 'disable','lumen-sound.service'])
            run(['systemctl','--user','stop' if old=='off' else 'start','lumen-sound.service'],timeout=40)
            if old=='off':cycle(library,stop=True)
        except Exception:pass
        raise


def daemon():
    library=Library('sound');stop=threading.Event()
    signal.signal(signal.SIGTERM,lambda *_:stop.set());signal.signal(signal.SIGINT,lambda *_:stop.set())
    # One worker per library, including manually launched workers.
    fd=os.open(library.root/'worker.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:os.close(fd);raise SystemExit('Lumen Sound arbeitet bereits.')
    try:
        cycle(library,stop=True)
        while not stop.is_set():
            try:cycle(library)
            except Exception:
                config=settings(library);library.update(config['id'],last_error='Audioserver nicht erreichbar oder Stream geändert; erneuter Versuch folgt.',heartbeat=time.time())
            stop.wait(2)
    finally:
        try:cycle(library,stop=True)
        finally:os.close(fd)


if __name__=='__main__' and sys.argv[1:]==['--run']:daemon()
