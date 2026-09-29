"""Bounded native desktop operations, run outside the GUI process. No shell commands."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
SHORTCUTS = {
    'lumen-ask.desktop': 'Lumen öffnen',
    'lumen-ask-sel.desktop': 'Zwischenablage erklären',
    'lumen-sel.desktop': 'Auswahl erklären',
    'lumen-vision.desktop': 'Bildschirm erklären',
}
SERVICES = {
    ('system', 'lumen-watch.timer'): 'Systemwächter',
    ('system', 'lumen-agentd.service'): 'Systemintegration',
    ('user', 'lumen-notify.path'): 'Benachrichtigungen',
    ('user', 'lumen-digest.timer'): 'Tagesbericht',
    ('user', 'lumen-nightly.timer'): 'Nachtbericht',
}
ANALYSIS = {
    'lumen-notify.service': 'LUMEN_WATCH_ANALYZE',
    'lumen-digest.service': 'LUMEN_WATCH_ANALYZE',
    'lumen-nightly.service': 'LUMEN_NIGHTLY_ANALYZE',
}
PLASMA = ['qdbus6', 'org.kde.plasmashell', '/PlasmaShell', 'org.kde.PlasmaShell.evaluateScript']


def run(arguments):
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=90 if arguments[0] == 'pkexec' else 20)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or 'Aktion fehlgeschlagen.').strip()[:1200])
    return result.stdout.strip()


def panels():
    result = json.loads(run(PLASMA + ['print(JSON.stringify(panels().map(function(p){return '
        '{id:p.id,screen:p.screen,location:p.location,height:p.height,floating:p.floating,hiding:p.hiding,'
        'widgets:p.widgets().map(function(w){return {id:w.id,type:w.type};})};})));']))
    if not isinstance(result, list) or any(not isinstance(p, dict) or
            not {'id', 'screen', 'location', 'height', 'floating', 'hiding', 'widgets'} <= p.keys() for p in result):
        raise ValueError('Diese Plasma-Version liefert nicht alle Leisteneinstellungen.')
    return result


def backup(name, value):
    directory = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'opencode-lumen/settings-backups'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{name}-{time.time_ns()}.json'
    path.write_text(json.dumps(value, indent=2))
    return path


def change_panel(data):
    selected = next((p for p in panels() if p['id'] == data['id']), None)
    if selected is None:
        raise ValueError('Diese Leiste existiert nicht mehr. Bitte neu laden.')
    changes = data['changes']
    for key, value in changes.items():
        valid = ((key == 'height' and type(value) is int and 20 <= value <= 160)
                 or (key == 'floating' and type(value) is bool)
                 or (key == 'location' and value in ('top', 'bottom', 'left', 'right'))
                 or (key == 'hiding' and value in ('none', 'autohide', 'dodgewindows', 'windowsgobelow')))
        if not valid:
            raise ValueError('Ungültige Leisteneinstellung.')
        if selected.get(key) != data['before'].get(key):
            raise ValueError('Die Leiste wurde inzwischen geändert. Bitte neu laden.')
    if changes:
        saved = backup('panel', selected)
        script = f'var p=panelById({int(selected["id"])}); if (!p) throw new Error("Leiste fehlt"); '
        script += ' '.join(f'p.{key} = {json.dumps(value)};' for key, value in changes.items())
        run(PLASMA + [script])
        return {'backup': str(saved)}
    return {}


def configure_widget(data):
    panel = next((p for p in panels() if p['id'] == data['panel']), None)
    if panel is None or data['widget'] not in [w['id'] for w in panel['widgets']]:
        raise ValueError('Dieses Element ist nicht mehr vorhanden.')
    run(PLASMA + [f'panelById({int(panel["id"])}).widgetById({int(data["widget"])}).showConfigurationInterface();'])


def accelerator():
    import dbus
    return dbus.Interface(dbus.SessionBus().get_object('org.kde.kglobalaccel', '/kglobalaccel'), 'org.kde.KGlobalAccel')


def shortcut_actions(accel):
    return {str(action[0]): list(map(str, action)) for component in accel.allMainComponents()
            if str(component[0]) in SHORTCUTS for action in accel.allActionsForComponent(component)
            if str(action[1]) == '_launch'}


def shortcuts():
    accel = accelerator()
    return {name: list(map(int, accel.shortcut(action))) for name, action in shortcut_actions(accel).items()}


def refresh_shortcuts(_data):
    import dbus
    run(['kbuildsycoca6', '--noincremental'])
    if not dbus.SessionBus().name_has_owner('org.kde.kglobalaccel'):
        return {'refreshed': 0}
    accel = accelerator()
    saved = [(action, accel.shortcutKeys(action)) for action in shortcut_actions(accel).values()]
    path = backup('shortcuts', saved)
    # KDE keeps the old Exec in each launch component even after rebuilding its
    # desktop database. Recreate only Lumen components, preserving custom keys.
    for action, keys in saved:
        component = dbus.Interface(dbus.SessionBus().get_object('org.kde.kglobalaccel', accel.getComponent(action[0])),
                                   'org.kde.kglobalaccel.Component')
        component.cleanUp()
        accel.doRegister(dbus.Array(action, signature='s'))
        result = accel.setShortcutKeys(dbus.Array(action, signature='s'), keys, dbus.UInt32(4))
        if {tuple(sequence[0]) for sequence in result} != {tuple(sequence[0]) for sequence in keys}:
            raise RuntimeError(f'Tastenkürzel konnte nicht wiederhergestellt werden: {action[0]}. Sicherung: {path}')
    return {'refreshed': len(saved), 'backup': str(path)}


def set_shortcut(data):
    import dbus
    accel = accelerator()
    action = shortcut_actions(accel).get(data['component'])
    if action is None:
        raise ValueError('Dieses Lumen-Tastenkürzel ist nicht registriert.')
    previous = list(map(int, accel.shortcut(action)))
    if previous != data['before']:
        raise ValueError('Das Tastenkürzel wurde inzwischen geändert. Bitte neu laden.')
    key = data['key']
    if type(key) is not int or key < 0 or key > 0x7fffffff:
        raise ValueError('Ungültiges Tastenkürzel.')
    if key and key not in previous and not accel.isGlobalShortcutAvailable(key, data['component']):
        raise ValueError('Dieses Tastenkürzel ist bereits belegt. Bitte ein anderes wählen.')
    keys = [key] if key else []
    result = list(map(int, accel.setShortcut(dbus.Array(action, signature='s'), dbus.Array(keys, signature='i'), dbus.UInt32(4))))
    if result != keys:
        raise RuntimeError('KDE hat das Tastenkürzel nicht übernommen. Bitte neu laden.')
    return result


def unit_state(scope, unit):
    raw = run(['systemctl'] + (['--user'] if scope == 'user' else []) + ['show', unit,
        '--property=LoadState,ActiveState,UnitFileState,TimersCalendar,Environment'])
    return dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)


def services():
    return [{**unit_state(scope, unit), 'scope': scope, 'unit': unit, 'title': title}
            for (scope, unit), title in SERVICES.items()]


def set_service(data):
    scope, unit = data['scope'], data['unit']
    if (scope, unit) not in SERVICES or type(data['enabled']) is not bool:
        raise ValueError('Unbekannter Lumen-Dienst.')
    # System units use KDE's existing authentication agent, only after a user click.
    command = ['systemctl', '--user'] if scope == 'user' else ['pkexec', '/usr/bin/systemctl']
    run(command + ['enable' if data['enabled'] else 'disable', '--now', unit])


def write_dropin(unit, text):
    path = CONFIG / 'systemd/user' / (unit + '.d') / 'lumen-settings.conf'
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = path.read_text() if path.exists() else None
    temporary = path.with_suffix('.tmp')
    temporary.write_text(text)
    temporary.replace(path)
    try:
        run(['systemctl', '--user', 'daemon-reload'])
    except Exception:
        path.write_text(previous) if previous is not None else path.unlink()
        try:
            run(['systemctl', '--user', 'daemon-reload'])
        except Exception:
            pass
        raise


def set_schedule(data):
    unit, clock = data['unit'], data['time']
    if unit not in ('lumen-digest.timer', 'lumen-nightly.timer') or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', clock):
        raise ValueError('Ungültige Berichtszeit.')
    active = unit_state('user', unit).get('ActiveState') == 'active'
    write_dropin(unit, f'[Timer]\nOnCalendar=\nOnCalendar=*-*-* {clock}:00\n')
    if active:
        run(['systemctl', '--user', 'restart', unit])


def analysis():
    return {unit: f'{key}=0' not in unit_state('user', unit).get('Environment', '').split()
            for unit, key in ANALYSIS.items()}


def set_analysis(data):
    unit = data['unit']
    if unit not in ANALYSIS or type(data['enabled']) is not bool:
        raise ValueError('Unbekannte Analyse-Einstellung.')
    write_dropin(unit, f'[Service]\nEnvironment={ANALYSIS[unit]}={int(data["enabled"])}\n')


def themes():
    return {title: run(['kreadconfig6', '--file', file, '--group', group, '--key', key, '--default', 'Systemstandard'])
            for title, file, group, key in [
                ('Plasma-Stil', 'plasmarc', 'Theme', 'name'),
                ('Farbschema', 'kdeglobals', 'General', 'ColorScheme'),
                ('Symbole', 'kdeglobals', 'Icons', 'Theme'),
                ('Anwendungsstil', 'kdeglobals', 'KDE', 'widgetStyle'),
                ('Kvantum', 'Kvantum/kvantum.kvconfig', 'General', 'theme')]}


def snapshot(_data):
    result = {}
    for name, reader in [('panels', panels), ('shortcuts', shortcuts), ('services', services), ('analysis', analysis), ('themes', themes)]:
        try:
            result[name] = reader()
        except Exception as error:
            result[name + '_error'] = str(error)
    return result


ACTIONS = {'snapshot': snapshot, 'panel': change_panel, 'widget': configure_widget,
           'shortcut': set_shortcut, 'refresh-shortcuts': refresh_shortcuts,
           'service': set_service, 'schedule': set_schedule, 'analysis': set_analysis}

if __name__ == '__main__':
    try:
        result = ACTIONS[sys.argv[1]](json.load(sys.stdin))
        print(json.dumps(result))
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
