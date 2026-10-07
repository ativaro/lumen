"""Optional native desktop presets. Every changed component has its own undo record."""
from lumen_i18n import tr
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import uuid

from file_spaces import Catalog, canonical, title
from lumen_controls import run
from lumen_history import record
from network import is_network_address

DEFAULTS = [dict(id='work', name=tr('Arbeiten'), layout='tile', quiet=60, audio='', volume=-1, connections=[]),
            dict(id='game', name=tr('Gaming'), layout='keep', quiet=180, audio='', volume=-1, connections=[]),
            dict(id='travel', name=tr('Unterwegs'), layout='keep', quiet=0, audio='', volume=-1, connections=[])]
DND = ['--file', 'plasmanotifyrc', '--group', 'DoNotDisturb', '--key', 'Until']


def modes(store):
    saved = {m['id']: m for m in Catalog(store).objects('mode')}
    return [saved.pop(m['id'], m) for m in DEFAULTS] + list(saved.values())


def save_mode(store, previous, value):
    value = dict(value, name=title(value['name']), id=previous['id'] if previous else uuid.uuid4().hex)
    if value['layout'] not in ('keep', 'tile', 'maximize') or value['quiet'] not in (-1, 0, 30, 60, 180):
        raise ValueError(tr('Ungültiger Arbeitsmodus.'))
    if type(value['volume']) is not int or not -1 <= value['volume'] <= 100:
        raise ValueError(tr('Ungültige Lautstärke.'))
    if not isinstance(value['audio'], str) or len(value['audio']) > 300 or '\x00' in value['audio']:
        raise ValueError(tr('Ungültiges Audiogerät.'))
    value['connections'] = list(dict.fromkeys(canonical(v) for v in value['connections']))
    if len(value['connections']) > 24 or any(not is_network_address(v) for v in value['connections']):
        raise ValueError(tr('Bitte bis zu 24 Netzwerkordner angeben.'))
    actual = next((m for m in Catalog(store).objects('mode') if m['id'] == value['id']), None)
    if previous is not None and ((actual is not None and actual != previous) or (actual is None and previous not in DEFAULTS)):
        raise ValueError(tr('Der Modus wurde in einem anderen Fenster geändert.'))
    Catalog(store).put('mode', value, actual)
    record(store, tr('Arbeitsmodus gespeichert: ') + value['name'], 'store-setting', actual, value,
           'files/spaces/mode/' + value['id'])
    return value


def audio_devices():
    return [dict(name=v['name'], description=v.get('description', v['name']))
            for v in json.loads(run(['pactl', '-f', 'json', 'list', 'sinks']))]


def audio_snapshot(sink=''):
    default = run(['pactl', 'get-default-sink'])
    selected = next((s for s in json.loads(run(['pactl', '-f', 'json', 'list', 'sinks'])) if s['name'] == (sink or default)), None)
    if selected is None: raise ValueError(tr('Dieses Audiogerät ist nicht verfügbar.'))
    return dict(default=default, sink=selected['name'], volume=[v['value'] for v in selected['volume'].values()])


def dnd_snapshot():
    return run(['kreadconfig6', *DND, '--default', ''])


def dnd_write(value):
    run(['kwriteconfig6', *DND, '--notify', value])


def window_script(store, body):
    """KWin replies over a private D-Bus object; no log scraping or shell."""
    from PySide6.QtCore import QObject, QCoreApplication, QEventLoop, QTimer, ClassInfo, Slot
    from PySide6.QtDBus import QDBusConnection
    app = QCoreApplication.instance() or QCoreApplication([])
    loop = QEventLoop()
    @ClassInfo(**{'D-Bus Interface': 'org.lumen.WindowReply'})
    class Reply(QObject):
        result = None
        @Slot(str)
        def receive(self, value):
            self.result = json.loads(value); loop.quit()
    receiver = Reply()
    bus = QDBusConnection.sessionBus()
    service = 'org.lumen.Layout.p' + uuid.uuid4().hex
    if not bus.registerService(service) or not bus.registerObject('/Reply', receiver, QDBusConnection.ExportAllSlots):
        raise RuntimeError(tr('KWin-Verbindung ist nicht verfügbar.'))
    script = store.directory / ('windows-' + uuid.uuid4().hex + '.js')
    script.write_text('try { const value = (() => {' + body + '})(); callDBus(' + json.dumps(service) +
                      ', "/Reply", "org.lumen.WindowReply", "receive", JSON.stringify({value})); } catch(e) { callDBus(' +
                      json.dumps(service) + ', "/Reply", "org.lumen.WindowReply", "receive", JSON.stringify({error:String(e)})); }')
    try:
        number = run(['qdbus6', 'org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting.loadScript', str(script), script.stem])
        if not number.isdigit(): raise RuntimeError(tr('KWin hat die Fensteraktion nicht geladen.'))
        run(['qdbus6', 'org.kde.KWin', '/Scripting/Script' + number, 'org.kde.kwin.Script.run'])
        timer = QTimer(); timer.setSingleShot(True); timer.timeout.connect(loop.quit); timer.start(2500)
        if receiver.result is None: loop.exec()
        timer.stop()
        if receiver.result is None: raise RuntimeError(tr('KWin hat nicht rechtzeitig geantwortet.'))
        if 'error' in receiver.result: raise RuntimeError(receiver.result['error'])
        return receiver.result['value']
    finally:
        try: run(['qdbus6', 'org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting.unloadScript', script.stem])
        finally:
            script.unlink(missing_ok=True); bus.unregisterObject('/Reply'); bus.unregisterService(service)


WINDOWS = '''const windows = workspace.windowList().filter(w => w.normalWindow && !w.minimized &&
    (w.onAllDesktops || w.desktops.includes(workspace.currentDesktop)));
'''


def layout_snapshot(store):
    return window_script(store, WINDOWS + '''return windows.map(w => ({id:String(w.internalId),
        geometry:{x:w.x,y:w.y,width:w.width,height:w.height}, maximized:Number(w.maximizeMode)}));''')


def set_layout(store, layout):
    if isinstance(layout, list):
        body = 'const saved = ' + json.dumps(layout) + ''';
        for (const s of saved) { const w=windows.find(w=>String(w.internalId)===s.id);
            if (!w) throw new Error(''' + json.dumps(tr('Fenster nicht mehr verfügbar')) + ''');
            w.setMaximize(false,false); w.frameGeometry=s.geometry;
            w.setMaximize(Boolean(s.maximized & 1), Boolean(s.maximized & 2)); }'''
    elif layout == 'maximize': body = 'for (const w of windows) { if(w.maximizable) w.setMaximize(true,true); }'
    elif layout == 'tile':
        body = '''const groups = new Map();
        for(const w of windows) { if(!groups.has(w.output)) groups.set(w.output,[]); groups.get(w.output).push(w); }
        for(const list of groups.values()) { const a=workspace.clientArea(KWin.MaximizeArea,list[0]);
          const width=Math.floor(a.width/list.length);
          list.forEach((w,i)=>{w.setMaximize(false,false); w.frameGeometry={x:a.x+i*width,y:a.y,
            width:i===list.length-1?a.width-i*width:width,height:a.height};}); }'''
    else: raise ValueError(tr('Unbekannte Fensteranordnung.'))
    window_script(store, WINDOWS + body + '; return true;')


def restore_snapshot(store, before, after):
    key = next(iter(before))
    expected = after[key]
    current = (audio_snapshot(expected['sink']) if key == 'audio' else dnd_snapshot()
               if key == 'quiet' else layout_snapshot(store))
    if current != expected: raise ValueError(tr('Der Systemzustand wurde inzwischen geändert. Rückgängig wurde nicht ausgeführt.'))
    value = before[key]
    if key == 'audio':
        run(['pactl', 'set-sink-volume', value['sink'], *map(str, value['volume'])])
        run(['pactl', 'set-default-sink', value['default']])
    elif key == 'quiet': dnd_write(value)
    else: set_layout(store, value)


def apply_mode(store, mode):
    errors, applied = [], []
    for key, label, enabled in [('audio', tr('Audio'), bool(mode['audio']) or mode['volume'] >= 0),
                                ('quiet', tr('Benachrichtigungen'), mode['quiet'] >= 0),
                                ('layout', tr('Fenster'), mode['layout'] != 'keep')]:
        if not enabled: continue
        before = None
        def read():
            return audio_snapshot(mode['audio']) if key == 'audio' else dnd_snapshot() if key == 'quiet' else layout_snapshot(store)
        try:
            before = read()
            if key == 'audio':
                if mode['audio']: run(['pactl', 'set-default-sink', before['sink']])
                if mode['volume'] >= 0: run(['pactl', 'set-sink-volume', before['sink'], str(mode['volume']) + '%'])
            elif key == 'quiet':
                date = datetime.now() + timedelta(minutes=mode['quiet']) if mode['quiet'] else datetime(1970, 1, 1)
                dnd_write(date.strftime('%Y,%m,%d,%H,%M,%S'))
            else: set_layout(store, mode['layout'])
            # Wayland clients commit requested geometry asynchronously.
            if key == 'layout':
                import time
                time.sleep(.3)
            after = read()
            if key == 'audio' and mode['audio'] and after['default'] != mode['audio']:
                raise RuntimeError(tr('Das Audiogerät wurde nicht übernommen.'))
            if key == 'audio' and mode['volume'] >= 0 and any(abs(v - 65536 * mode['volume'] / 100) > 2 for v in after['volume']):
                raise RuntimeError(tr('Die Lautstärke wurde nicht vollständig übernommen.'))
            if key == 'quiet' and after != date.strftime('%Y,%m,%d,%H,%M,%S'):
                raise RuntimeError(tr('Die Ruhezeit wurde nicht übernommen.'))
            if before != after:
                record(store, mode['name'] + ': ' + label, 'mode', {key: before}, {key: after})
            applied.append(label)
        except Exception as error:
            if before is not None:
                try:
                    after = read()
                    if after != before: record(store, mode['name'] + ': ' + label + tr(' (teilweise)'), 'mode', {key: before}, {key: after})
                except Exception: record(store, mode['name'] + ': ' + label + tr(' – Zustand prüfen'))
            errors.append(label + ': ' + str(error))
    result = dict(name=mode['name'], applied=applied, errors=errors)
    store.set_setting('workplace/last-mode', result)
    return result
