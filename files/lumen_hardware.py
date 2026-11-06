"""Read-only Linux telemetry and current-user activity; no privileged helpers."""
from lumen_i18n import tr
import csv
import io
import json
import math
import os
from pathlib import Path
import subprocess
import time


def sensors(data):
    rows = []
    if not isinstance(data, dict): return rows
    for chip, features in data.items():
        if not isinstance(features, dict): continue
        for label, fields in features.items():
            if not isinstance(fields, dict): continue
            for key, value in fields.items():
                if not isinstance(value, (int, float)) or not math.isfinite(value): continue
                unit = ('°C' if key.startswith('temp') and key.endswith('_input') else
                        'U/min' if key.startswith('fan') and key.endswith('_input') else
                        'W' if key.startswith('power') and key.endswith(('_input', '_average')) else '')
                if unit and (unit != '°C' or -40 <= value <= 150):
                    rows.append({'device': chip, 'name': label, 'value': round(value, 1), 'unit': unit})
    return rows


def read_command(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=3,
                          env={**os.environ, 'LC_ALL': 'C'}).stdout


def snapshot(include_activity=True):
    from lumen_store import Store
    policy = Store().setting('modelPolicy', {}) if include_activity else {}
    rows, unavailable = [], []
    try: rows = sensors(json.loads(read_command(['sensors', '-j'])))
    except (OSError, ValueError, subprocess.SubprocessError): unavailable.append(tr('lm_sensors nicht verfügbar'))
    try:
        output = read_command(['nvidia-smi', '--query-gpu=name,temperature.gpu,fan.speed,power.draw,utilization.gpu', '--format=csv,noheader,nounits'])
        for gpu in csv.reader(io.StringIO(output), skipinitialspace=True):
            if len(gpu) != 5: continue
            for name, raw, unit in zip((tr('Temperatur'), tr('Lüfter'), tr('Leistung'), tr('Auslastung')), gpu[1:], ('°C', '%', 'W', '%')):
                try: value = float(raw)
                except ValueError: continue
                if math.isfinite(value): rows.append({'device': gpu[0], 'name': name, 'value': value, 'unit': unit})
    except (OSError, subprocess.SubprocessError): pass
    return {'sensors': rows, 'unavailable': unavailable,
            'activity': activity(extra_apps=policy.get('activity_apps', [])) if include_activity else [], 'measured': time.time()}


def activity(proc_root=Path('/proc'), uid=None, extra_apps=()):
    """Do not persist argv/environment. Steam library location is irrelevant."""
    uid = os.getuid() if uid is None else uid
    found = set()
    recorders = {'obs': 'OBS', 'obs64': 'OBS', 'gpu-screen-recorder': 'GPU Screen Recorder',
                 'simplescreenrecorder': 'SimpleScreenRecorder', 'wf-recorder': 'wf-recorder'}
    recorders = {name[:15]: title for name, title in recorders.items()}  # Linux comm is limited to 15 bytes.
    try: entries = list(proc_root.iterdir())
    except OSError: return []
    for path in entries[:32768]:
        if not path.name.isdecimal(): continue
        try:
            if path.stat().st_uid != uid: continue
            name = (path / 'comm').read_text().strip().lower()
            if name in extra_apps: found.add(name + tr(' geöffnet'))
            if name in recorders: found.add(recorders[name] + tr(' geöffnet'))
            with (path / 'environ').open('rb') as stream: env = stream.read(65536).split(b'\0')
            game = any(v.startswith((b'SteamAppId=', b'SteamGameId=')) and v.split(b'=', 1)[1].isdigit()
                       and int(v.split(b'=', 1)[1]) > 0 for v in env)
            if game and name not in {'steam', 'steamwebhelper', 'pressure-vessel', 'reaper'}:
                found.add('Steam-Spiel')
            if name == 'gamescope': found.add('Gamescope-Sitzung')
            if name == 'gamemoded':
                try:
                    if read_command(['gamemoded', '-s']).strip().lower() == 'gamemode is active': found.add('GameMode-Spiel')
                except (OSError, subprocess.SubprocessError): pass
        except (OSError, ValueError): continue
    return sorted(found)


def gaming():
    """Share current-user game detection with notifications and launcher shortcuts."""
    return bool({'Steam-Spiel', 'GameMode-Spiel', 'Gamescope-Sitzung'}.intersection(activity()))


def background_reason(store):
    policy = store.setting('modelPolicy', {})
    if policy.get('pause_background', False): return tr('Hintergrundaufträge sind pausiert.')
    if policy.get('pause_on_activity', True):
        active = activity(extra_apps=policy.get('activity_apps', []))
        if active: return tr('Hintergrundarbeit wartet: ') + ', '.join(active)
    try:
        limit = max(1, int(policy.get('gpu_limit', 90)))
        if limit < 100:
            values = read_command(['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'])
            if any(float(v.strip()) >= limit for v in values.splitlines()):
                return tr('Hintergrundarbeit wartet auf die Grafikkarte.')
    except (OSError, ValueError, subprocess.SubprocessError): pass
    return ''


if __name__ == '__main__': print(json.dumps(snapshot(), ensure_ascii=False))
