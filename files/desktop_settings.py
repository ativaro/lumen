"""Bounded native desktop operations, run outside the GUI process. No shell commands."""
from lumen_i18n import tr
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
SHORTCUTS = {
    'lumen-apps.desktop': tr('Lumen Startmenü'),
    'lumen-ask.desktop': tr('Lumen öffnen'),
    'lumen-toggle.desktop': tr('Lumen ein-/ausblenden'),
    'lumen-ask-sel.desktop': tr('Zwischenablage erklären'),
    'lumen-sel.desktop': tr('Auswahl erklären'),
    'lumen-vision.desktop': tr('Bildschirm erklären'),
}
SERVICES = {
    ('system', 'lumen-watch.timer'): tr('Systemwächter'),
    ('system', 'lumen-agentd.service'): tr('Systemintegration'),
    ('user', 'lumen-notify.path'): tr('Benachrichtigungen'),
    ('user', 'lumen-digest.timer'): tr('Tagesbericht'),
    ('user', 'lumen-nightly.timer'): tr('Nachtbericht'),
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
        raise RuntimeError((result.stderr or result.stdout or tr('Aktion fehlgeschlagen.')).strip()[:1200])
    return result.stdout.strip()


def panels():
    result = json.loads(run(PLASMA + ['print(JSON.stringify(panels().map(function(p){return '
        '{id:p.id,screen:p.screen,location:p.location,height:p.height,floating:p.floating,hiding:p.hiding,'
        'widgets:p.widgets().map(function(w){return {id:w.id,type:w.type};})};})));']))
    if not isinstance(result, list) or any(not isinstance(p, dict) or
            not {'id', 'screen', 'location', 'height', 'floating', 'hiding', 'widgets'} <= p.keys() for p in result):
        raise ValueError(tr('Diese Plasma-Version liefert nicht alle Leisteneinstellungen.'))
    return result


def backup(name, value):
    directory = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'lumen/settings-backups'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{name}-{time.time_ns()}.json'
    path.write_text(json.dumps(value, indent=2))
    return path


def change_panel(data, journal=True):
    selected = next((p for p in panels() if p['id'] == data['id']), None)
    if selected is None:
        raise ValueError(tr('Diese Leiste existiert nicht mehr. Bitte neu laden.'))
    changes = data['changes']
    for key, value in changes.items():
        valid = ((key == 'height' and type(value) is int and 20 <= value <= 160)
                 or (key == 'floating' and type(value) is bool)
                 or (key == 'location' and value in ('top', 'bottom', 'left', 'right'))
                 or (key == 'hiding' and value in ('none', 'autohide', 'dodgewindows', 'windowsgobelow')))
        if not valid:
            raise ValueError(tr('Ungültige Leisteneinstellung.'))
        if selected.get(key) != data['before'].get(key):
            raise ValueError(tr('Die Leiste wurde inzwischen geändert. Bitte neu laden.'))
    if changes:
        saved = backup('panel', selected)
        script = f'var p=panelById({int(selected["id"])}); if (!p) throw new Error({json.dumps(tr("Leiste fehlt"))}); '
        script += ' '.join(f'p.{key} = {json.dumps(value)};' for key, value in changes.items())
        run(PLASMA + [script])
        current = next((p for p in panels() if p['id'] == selected['id']), {})
        actual = {key: current.get(key) for key in changes}
        if journal:
            from lumen_history import record
            from lumen_store import Store
            record(Store(), tr('Systemleiste angepasst'), 'panel',
                   {key: selected[key] for key in changes}, actual, selected['id'])
        if actual != changes:
            raise RuntimeError(tr('Plasma hat nicht alle Leisteneinstellungen übernommen. Der Verlauf enthält den tatsächlichen Zustand.'))
        return {'backup': str(saved)}
    return {}


def configure_widget(data):
    panel = next((p for p in panels() if p['id'] == data['panel']), None)
    if panel is None or data['widget'] not in [w['id'] for w in panel['widgets']]:
        raise ValueError(tr('Dieses Element ist nicht mehr vorhanden.'))
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
    # Never cleanUp/recreate live components: KWin processes their key events.
    # Cached Exec changes take effect on next login; stable launchers update now.
    run(['kbuildsycoca6', '--noincremental'])
    return {'refreshed': True}


def set_shortcut(data, journal=True):
    import dbus
    accel = accelerator()
    action = shortcut_actions(accel).get(data['component'])
    if action is None:
        raise ValueError(tr('Dieses Lumen-Tastenkürzel ist nicht registriert.'))
    previous = list(map(int, accel.shortcut(action)))
    if previous != data['before']:
        raise ValueError(tr('Das Tastenkürzel wurde inzwischen geändert. Bitte neu laden.'))
    key = data['key']
    if type(key) is not int or key < 0 or key > 0x7fffffff:
        raise ValueError(tr('Ungültiges Tastenkürzel.'))
    if key and key not in previous and not accel.isGlobalShortcutAvailable(key, data['component']):
        raise ValueError(tr('Dieses Tastenkürzel ist bereits belegt. Bitte ein anderes wählen.'))
    keys = [key] if key else []
    result = list(map(int, accel.setShortcut(dbus.Array(action, signature='s'), dbus.Array(keys, signature='i'), dbus.UInt32(4))))
    if result != keys:
        raise RuntimeError(tr('KDE hat das Tastenkürzel nicht übernommen. Bitte neu laden.'))
    if journal:
        from lumen_history import record
        from lumen_store import Store
        record(Store(), SHORTCUTS[data['component']] + tr(': Tastenkürzel geändert'),
               'shortcut' if len(previous) <= 1 else 'activity', previous, result, data['component'])
    return result


def _apply_launch_shortcuts(accel, rows):
    import dbus
    # Release only these launch keys before assigning their new owners.
    for row in rows:
        accel.doRegister(dbus.Array(row['action'], signature='s'))
        accel.setShortcut(dbus.Array(row['action'], signature='s'), dbus.Array([], signature='i'), dbus.UInt32(6))
    for row in rows:
        # NoAutoloading | SetPresent also activates a newly registered launcher.
        result = accel.setShortcut(dbus.Array(row['action'], signature='s'), dbus.Array(row['keys'], signature='i'), dbus.UInt32(6))
        if sorted(map(int, result)) != sorted(row['keys']):
            raise RuntimeError(tr('KDE hat die Start-Tastenkürzel nicht übernommen.'))


def restore_launch_shortcuts(saved):
    _apply_launch_shortcuts(accelerator(), saved['actions'])
    command = ['kwriteconfig6', '--file', 'kwinrc', '--group', 'ModifierOnlyShortcuts', '--key', 'Meta']
    run(command + ([saved['meta']] if saved['meta'] else ['--delete']))


def launch_shortcuts_plan():
    from PySide6.QtGui import QKeySequence
    accel = accelerator()
    targets = {'Meta': ('lumen-apps.desktop', tr('Lumen Startmenü')),
               'Alt+Space': ('lumen-ask.desktop', tr('Lumen öffnen'))}
    keys = {text: QKeySequence(text)[0].toCombined() for text in targets}
    rows = {}
    for text, (component, title) in targets.items():
        owners = accel.getGlobalShortcutsByKey(keys[text])
        allowed = {(component, '_launch'), ('lumen-toggle.desktop', '_launch') if text == 'Meta'
                   else ('org.kde.krunner.desktop', '_launch')}
        if text == 'Meta': allowed.add(('plasmashell', 'activate application launcher'))
        for owner in owners:
            identity = (str(owner[2]), str(owner[0]))
            if identity not in allowed:
                raise ValueError(tr('Das Start-Tastenkürzel ist anderweitig belegt: ') + text)
            action = [identity[0], identity[1], str(owner[3]), str(owner[1])]
            rows[identity] = dict(action=action, keys=list(map(int, accel.shortcut(action))))
        action = [component, '_launch', title, title]
        rows.setdefault((component, '_launch'), dict(action=action, keys=list(map(int, accel.shortcut(action)))))
    saved = dict(actions=list(rows.values()), meta=run(['kreadconfig6', '--file', 'kwinrc', '--group',
                 'ModifierOnlyShortcuts', '--key', 'Meta', '--default', '']))
    desired = {identity: dict(action=row['action'], keys=[k for k in row['keys'] if k not in keys.values()]) for identity, row in rows.items()}
    for text, (component, _) in targets.items(): desired[(component, '_launch')]['keys'].append(keys[text])
    return {'before': saved, 'actions': list(desired.values())}


def configure_launch_shortcuts():
    plan = launch_shortcuts_plan(); saved = plan['before']
    path = backup('launch-shortcuts', saved)
    try:
        refresh_shortcuts({})
        _apply_launch_shortcuts(accelerator(), plan['actions'])
        if saved['meta'] == 'org.lumen.Topbar,/Topbar,org.lumen.Topbar,ShowApps':
            run(['kwriteconfig6', '--file', 'kwinrc', '--group', 'ModifierOnlyShortcuts', '--key', 'Meta', '--delete'])
    except Exception:
        restore_launch_shortcuts(saved)
        raise
    return {'backup': str(path), 'actions': plan['actions']}


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
        raise ValueError(tr('Unbekannter Lumen-Dienst.'))
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
        raise ValueError(tr('Ungültige Berichtszeit.'))
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
        raise ValueError(tr('Unbekannte Analyse-Einstellung.'))
    write_dropin(unit, f'[Service]\nEnvironment={ANALYSIS[unit]}={int(data["enabled"])}\n')


def themes():
    return {title: run(['kreadconfig6', '--file', file, '--group', group, '--key', key, '--default', tr('Systemstandard')])
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


from lumen_desktop_theme import apply as apply_appearance

ACTIONS = {'appearance': apply_appearance, 'snapshot': snapshot, 'panel': change_panel, 'widget': configure_widget,
           'shortcut': set_shortcut, 'refresh-shortcuts': refresh_shortcuts,
           'service': set_service, 'schedule': set_schedule, 'analysis': set_analysis}

if __name__ == '__main__':
    try:
        action, data = sys.argv[1], json.load(sys.stdin)
        result = ACTIONS[action](data)
        if action in ('service', 'schedule', 'analysis'):
            from lumen_history import record
            from lumen_store import Store
            names = {'service': tr('Dienst geändert'), 'schedule': tr('Zeitplan geändert'), 'analysis': tr('Automatische Analyse geändert')}
            record(Store(), names[action] + ': ' + data['unit'])
        print(json.dumps(result))
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
