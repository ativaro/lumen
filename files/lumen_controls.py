"""Small native desktop controls for the Plasma popup; never starts AI work."""
from lumen_i18n import tr
import os
import re
import subprocess

BRIGHTNESS = ['qdbus6', 'org.kde.Solid.PowerManagement',
              '/org/kde/Solid/PowerManagement/Actions/BrightnessControl']
BRIGHTNESS_INTERFACE = 'org.kde.Solid.PowerManagement.Actions.BrightnessControl.'
ACTIONS = {
    'search': ['qdbus6', 'org.kde.krunner', '/App', 'org.kde.krunner.App.display'],
    'network': ['systemsettings', 'kcm_networkmanagement'],
    'proxy': ['systemsettings', 'kcm_proxy'],
    'audio': ['systemsettings', 'kcm_pulseaudio'],
    'bluetooth': ['systemsettings', 'kcm_bluetooth'],
    'firewall': ['systemsettings', 'kcm_firewall'],
    'display': ['systemsettings', 'kcm_kscreen'],
    'appearance': ['lumen-settings', '--appearance'],
    'desktop-settings': ['systemsettings'],
    'hardware': ['lumen-system'],
    'lock': ['qdbus6', 'org.freedesktop.ScreenSaver', '/ScreenSaver', 'org.freedesktop.ScreenSaver.Lock'],
}


def run(arguments, timeout=3):
    return subprocess.run(arguments, check=True, capture_output=True, text=True,
                          timeout=timeout, env={**os.environ, 'LC_ALL': 'C'}).stdout.strip()


def brightness(method, *args):
    return run([*BRIGHTNESS, BRIGHTNESS_INTERFACE + method, *map(str, args)])


def snapshot():
    value = {'volume': None, 'muted': False, 'brightness': None, 'network': tr('Nicht verfügbar')}
    try:
        volume = run(['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@'])
        match = re.fullmatch(r'Volume: (\d+(?:\.\d+)?)\s*(\[MUTED\])?', volume)
        if match:
            value.update(volume=round(float(match[1]) * 100), muted=bool(match[2]))
    except (OSError, subprocess.SubprocessError): pass
    try:
        maximum = int(brightness('brightnessMax'))
        if maximum > 0: value['brightness'] = round(int(brightness('brightness')) * 100 / maximum)
    except (OSError, subprocess.SubprocessError, ValueError): pass
    try:
        state = run(['nmcli', '-t', '-f', 'STATE', 'general'])
        value['network'] = {'connected': tr('Verbunden'), 'connected (local only)': tr('Lokales Netzwerk'),
                            'connected (site only)': tr('Lokales Netzwerk'), 'connecting': tr('Verbindet …'),
                            'disconnected': tr('Nicht verbunden'), 'asleep': tr('Deaktiviert')}.get(state, tr('Nicht verfügbar'))
    except (OSError, subprocess.SubprocessError): pass
    return value


def control(action, value=None):
    if action in ('volume', 'brightness'):
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError(tr('Ein Wert zwischen 0 und 100 ist erforderlich.'))
        if action == 'volume': run(['wpctl', 'set-volume', '-l', '1', '@DEFAULT_AUDIO_SINK@', f'{value}%'])
        else:
            maximum = int(brightness('brightnessMax'))
            if maximum <= 0: raise ValueError(tr('Bildschirmhelligkeit ist nicht verfügbar.'))
            minimum = int(brightness('knownSafeBrightnessMin'))
            brightness('setBrightnessSilent', max(minimum, round(value * maximum / 100)))
    elif action == 'mute': run(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', 'toggle'])
    elif action in ACTIONS:
        arguments = list(ACTIONS[action])
        if arguments[0].startswith('lumen-'):
            from lumen_launch import executable
            arguments[0] = executable(arguments[0])
        subprocess.Popen(arguments, start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else: raise ValueError(tr('Unbekannte Systemaktion.'))
