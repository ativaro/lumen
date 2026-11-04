"""On-demand NetworkManager, PulseAudio/PipeWire and BlueZ controls for the bar."""
from concurrent.futures import ThreadPoolExecutor
import json
import re
import subprocess

from lumen_controls import run
from lumen_i18n import tr


def fields(line):
    """nmcli terse fields escape both colons and backslashes."""
    result, value, escaped = [], '', False
    for char in line:
        if escaped:
            value += char
            escaped = False
        elif char == '\\':
            escaped = True
        elif char == ':':
            result.append(value)
            value = ''
        else:
            value += char
    result.append(value + ('\\' if escaped else ''))
    return result


def nm(*args):
    # Leave time for the desktop secret agent; passwords never enter our arguments.
    return run(['nmcli', '--wait', '30', '--terse', *args], timeout=35)


def _parallel(jobs):
    def read(command):
        try:
            return run(command, timeout=4), ''
        except (OSError, subprocess.SubprocessError):
            return '', tr('Nicht verfügbar')
    with ThreadPoolExecutor(max_workers=4) as pool:
        return dict(zip(jobs, pool.map(read, jobs.values())))


def network_snapshot():
    jobs = dict(
        general=['nmcli', '-t', '-f', 'STATE,CONNECTIVITY', 'general'],
        radio=['nmcli', '-t', '-f', 'WIFI', 'radio'],
        devices=['nmcli', '-t', '-f', 'GENERAL.DEVICE,GENERAL.TYPE,GENERAL.STATE,GENERAL.CONNECTION,GENERAL.HWADDR,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS,IP6.ADDRESS,IP6.GATEWAY,IP6.DNS', 'device', 'show'],
        profiles=['nmcli', '-t', '-f', 'NAME,UUID,TYPE,DEVICE,AUTOCONNECT', 'connection', 'show'],
        networks=['nmcli', '-t', '-f', 'IN-USE,BSSID,SSID,SIGNAL,SECURITY,FREQ,CHAN,DEVICE', 'device', 'wifi', 'list', '--rescan', 'no'])
    read = _parallel(jobs)
    devices, current = [], None
    for line in read['devices'][0].splitlines():
        values = fields(line)
        if len(values) < 2:
            continue
        key, value = values[0], ':'.join(values[1:])
        if key == 'GENERAL.DEVICE':
            current = dict(id=value, name=value, type='', state='', profile='', details=[])
            devices.append(current)
        if current is None:
            continue
        keys = {'GENERAL.TYPE': 'type', 'GENERAL.STATE': 'state', 'GENERAL.CONNECTION': 'profile'}
        if key in keys:
            current[keys[key]] = value
        if value and value != '--':
            label = {'GENERAL.DEVICE': 'Adapter', 'GENERAL.TYPE': 'Typ', 'GENERAL.STATE': 'Status',
                     'GENERAL.CONNECTION': 'Profil', 'GENERAL.HWADDR': 'MAC-Adresse',
                     'IP4.ADDRESS': 'IPv4', 'IP4.GATEWAY': 'IPv4-Gateway', 'IP4.DNS': 'DNS (IPv4)',
                     'IP6.ADDRESS': 'IPv6', 'IP6.GATEWAY': 'IPv6-Gateway', 'IP6.DNS': 'DNS (IPv6)'}.get(re.sub(r'\[\d+\]$', '', key), key)
            current['details'].append(dict(label=tr(label), value=value))
    profiles = []
    for line in read['profiles'][0].splitlines():
        values = fields(line)
        if len(values) == 5:
            name, uuid, kind, device, auto = values
            profiles.append(dict(id=uuid, name=name, type=kind, device=device, active=bool(device and device != '--'), autoconnect=auto == 'yes'))
    modes = _parallel({p['id']: ['nmcli', '-g', '802-11-wireless.mode', 'connection', 'show', 'uuid', p['id']]
                       for p in profiles if p['type'] in ('wifi', '802-11-wireless')})
    for profile in profiles:
        profile['hotspot'] = modes.get(profile['id'], ('', ''))[0] == 'ap'
    networks, seen = [], set()
    for line in read['networks'][0].splitlines():
        values = fields(line)
        if len(values) == 8:
            active, bssid, name, signal, security, frequency, channel, device = values
            identity = device + '/' + bssid
            if identity in seen:
                continue
            seen.add(identity)
            networks.append(dict(id=identity, bssid=bssid, name=name or tr('Verstecktes Netzwerk'), hidden=not name,
                                 signal=int(signal) if signal.isdigit() else 0, security=security,
                                 frequency=frequency, channel=channel, device=device, active=active == '*'))
    general = fields(read['general'][0])
    return dict(available=not bool(read['general'][1]), state=general[0] if general else '',
                connectivity=general[1] if len(general) > 1 else '', wifiEnabled=read['radio'][0] == 'enabled',
                devices=devices, profiles=profiles, networks=networks,
                errors=[dict(area=key, message=error) for key, (_, error) in read.items() if error])


def _volume(item):
    values = list(item.get('volume', {}).values())
    return round(sum(float(v.get('value', 0)) for v in values) * 100 / (65536 * len(values))) if values else None


def _bluez():
    try:
        objects = json.loads(run(['busctl', '--system', '--auto-start=no', '--json=short', 'call', 'org.bluez', '/',
                                  'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects']))['data'][0]
        adapters, devices = [], []
        for path, interfaces in objects.items():
            def props(interface):
                return {key: value.get('data') for key, value in interfaces.get(interface, {}).items()}
            adapter = props('org.bluez.Adapter1')
            if adapter:
                adapters.append(dict(id=path, name=adapter.get('Alias', ''), powered=adapter.get('Powered', False)))
            device = props('org.bluez.Device1')
            if device and (str(device.get('Icon', '')).startswith('audio') or any(
                    str(uuid).startswith(('0000110a-', '0000110b-', '0000111e-', '00001108-')) for uuid in device.get('UUIDs', []))):
                devices.append(dict(id=device.get('Address', ''), name=device.get('Alias', ''),
                                    connected=device.get('Connected', False), paired=device.get('Paired', False),
                                    battery=props('org.bluez.Battery1').get('Percentage')))
        return dict(available=True, adapters=adapters, devices=devices)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError):
        return dict(available=False, adapters=[], devices=[])


def audio_snapshot():
    jobs = {key: ['pactl', '--format=json', 'list', key] for key in ('sinks', 'sources', 'sink-inputs', 'source-outputs', 'cards')}
    jobs['info'] = ['pactl', '--format=json', 'info']
    read = _parallel(jobs)
    def parsed(key, fallback):
        try:
            value = json.loads(read[key][0])
            if not isinstance(value, type(fallback)):
                raise ValueError('Unexpected system data')
            return value
        except ValueError:
            if not read[key][1]:
                read[key] = ('', tr('Ungültige Systemdaten.'))
            return fallback
    info = parsed('info', {})
    def devices(key):
        return [dict(id=str(item['index']), name=item.get('description', item.get('name', '')), address=item.get('name', ''),
                     muted=bool(item.get('mute')), volume=_volume(item), state=item.get('state', ''),
                     default=item.get('name') == info.get('default_sink_name' if key == 'sinks' else 'default_source_name'),
                     monitor=item.get('monitor_of_sink') not in (None, 4294967295),
                     ports=[dict(id=p['name'], name=p.get('description', p['name']), available=p.get('availability', '')) for p in item.get('ports', [])],
                     activePort=item.get('active_port', ''), format=item.get('sample_specification', '')) for item in parsed(key, []) if 'index' in item]
    def streams(key):
        return [dict(id=str(item['index']), name=item.get('properties', {}).get('application.name', item.get('name', tr('Unbekannte App'))),
                     media=item.get('properties', {}).get('media.name', ''), volume=_volume(item), muted=bool(item.get('mute')),
                     device=str(item.get('sink' if key == 'sink-inputs' else 'source', '')))
                for item in parsed(key, []) if 'index' in item]
    cards = []
    for item in parsed('cards', []):
        profiles = item.get('profiles', [])
        if isinstance(profiles, dict):
            profiles = [dict(value, name=key) for key, value in profiles.items()]
        cards.append(dict(id=str(item['index']), name=item.get('properties', {}).get('device.description', item.get('name', '')),
                          active=item.get('active_profile', ''),
                          profiles=[dict(id=p['name'], name=p.get('description', p['name'])) for p in profiles if p.get('available') != 'no']))
    return dict(available=bool(info), outputs=devices('sinks'), inputs=[d for d in devices('sources') if not d['monitor']],
                playback=streams('sink-inputs'), recording=streams('source-outputs'), cards=cards,
                server=info.get('server_name', ''), bluetooth=_bluez(),
                errors=[dict(area=key, message=error) for key, (_, error) in read.items() if error])


def snapshot(topic):
    if topic == 'network':
        return network_snapshot()
    if topic == 'audio':
        return audio_snapshot()
    raise ValueError(tr('Unbekannter Systembereich.'))


def _member(items, identity):
    for item in items:
        if item['id'] == identity:
            return item
    raise ValueError(tr('Das gewählte Gerät oder Profil ist nicht mehr verfügbar.'))


def act(topic, request):
    """Resolve every target against current system objects; never execute shell text."""
    if not isinstance(request, dict) or set(request) - {'action', 'target', 'value'}:
        raise ValueError(tr('Ungültige Systemaktion.'))
    action, target, value = request.get('action'), request.get('target', ''), request.get('value', 0)
    if not isinstance(action, str) or not isinstance(target, str) or len(target) > 1024 or '\0' in target or type(value) is not int:
        raise ValueError(tr('Ungültige Systemaktion.'))
    current = snapshot(topic)
    if topic == 'network':
        if action == 'wifi':
            if value not in (0, 1):
                raise ValueError(tr('Ungültiger Schalterwert.'))
            nm('radio', 'wifi', 'on' if value else 'off')
        elif action == 'rescan':
            nm('device', 'wifi', 'rescan')
        elif action in ('connect', 'disconnect'):
            profile = _member(current['profiles'], target)
            nm('connection', 'up' if action == 'connect' else 'down', 'uuid', profile['id'])
        elif action == 'join':
            network = _member(current['networks'], target)
            nm('device', 'wifi', 'connect', network['bssid'], 'ifname', network['device'])
        elif action == 'diagnose':
            nm('networking', 'connectivity', 'check')
        else:
            raise ValueError(tr('Unbekannte Netzwerkaktion.'))
    elif topic == 'audio':
        kinds = {'output': ('outputs', 'sink'), 'input': ('inputs', 'source'),
                 'playback': ('playback', 'sink-input'), 'recording': ('recording', 'source-output')}
        command, _, kind = action.partition(':')
        if kind in kinds:
            collection, pulse = kinds[kind]
            item = _member(current[collection], target)
            if command == 'volume' and 0 <= value <= 100 and item['volume'] is not None:
                run(['pactl', 'set-' + pulse + '-volume', item['id'], f'{value}%'])
            elif command == 'mute':
                run(['pactl', 'set-' + pulse + '-mute', item['id'], 'toggle'])
            elif command == 'default' and kind in ('output', 'input'):
                run(['pactl', 'set-default-' + pulse, item['id']])
            elif command == 'route' and kind in ('playback', 'recording'):
                destination = _member(current['outputs' if kind == 'playback' else 'inputs'], str(value))
                run(['pactl', 'move-' + pulse, item['id'], destination['id']])
            else:
                raise ValueError(tr('Ungültige Audioaktion.'))
        elif action == 'profile':
            card_id, _, profile_id = target.partition('/')
            card = _member(current['cards'], card_id)
            profile = _member(card['profiles'], profile_id)
            run(['pactl', 'set-card-profile', card['id'], profile['id']])
        elif action in ('bt-connect', 'bt-disconnect'):
            device = _member(current['bluetooth']['devices'], target)
            if not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', device['id']):
                raise ValueError(tr('Ungültiges Bluetooth-Gerät.'))
            run(['bluetoothctl', '--timeout', '8', 'connect' if action == 'bt-connect' else 'disconnect', device['id']], timeout=10)
        elif action == 'bt-power':
            adapter = _member(current['bluetooth']['adapters'], target)
            if value not in (0, 1):
                raise ValueError(tr('Ungültiger Schalterwert.'))
            run(['busctl', '--system', 'set-property', 'org.bluez', adapter['id'], 'org.bluez.Adapter1', 'Powered', 'b', 'true' if value else 'false'])
        else:
            raise ValueError(tr('Unbekannte Audioaktion.'))
    return snapshot(topic)
