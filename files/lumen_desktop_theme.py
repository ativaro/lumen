"""Generate native Plasma variants from the installed Lumen artwork and app palette."""
from lumen_i18n import tr
import configparser
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from appearance import COLORS, DESIGNS

ARTWORK = Path(__file__).resolve().parent.parent / 'desktop'
DECORATION_GROUP = ['--file', 'kwinrc', '--group', 'org.kde.kdecoration2']


def decoration_settings(identity):
    return {'library': 'org.kde.kwin.aurorae.v2', 'theme': '__aurorae__svg__' + identity,
            'ButtonsOnLeft': '', 'ButtonsOnRight': 'IAX'}


def current_decoration():
    from desktop_settings import run
    values = {key: run(['kreadconfig6'] + DECORATION_GROUP + ['--key', key, '--default', '__LUMEN_UNSET__'])
              for key in decoration_settings('')}
    return {key: None if value == '__LUMEN_UNSET__' else value for key, value in values.items()}


def set_decoration(selected, previous):
    from desktop_settings import run
    try:
        for key, value in selected.items():
            run(['kwriteconfig6'] + DECORATION_GROUP + ['--key', key, value])
        run(['qdbus6', 'org.kde.KWin', '/KWin', 'org.kde.KWin.reconfigure'])
        if current_decoration() != selected:
            raise ValueError(tr('KWin hat die Fensterdekoration nicht übernommen.'))
    except Exception:
        for key, value in previous.items():
            run(['kwriteconfig6'] + DECORATION_GROUP + ['--key', key] +
                (['--delete'] if value is None else [value]))
        run(['qdbus6', 'org.kde.KWin', '/KWin', 'org.kde.KWin.reconfigure'])
        raise


def refresh_decoration():
    """Upgrade only a selected legacy Lumen frame; never reset panels or custom themes."""
    from desktop_settings import backup
    previous = current_decoration()
    legacy = {'org.lumen.' + name: name for _, name in DESIGNS}
    legacy.update({'org.lumen.echo.' + name: name for _, name in DESIGNS})
    legacy.update(LumenGraphite='graphite', LumenDark='midnight')
    name = legacy.get((previous['theme'] or '').removeprefix('__aurorae__svg__'))
    if previous['library'] != 'org.kde.kwin.aurorae.v2' or name is None:
        return False
    selected = decoration_settings(prepare_decoration(name).name)
    backup('appearance', {'decoration_before': previous, 'decoration_after': selected})
    set_decoration(selected, previous)
    return True


def prepare(name, destination=None, source=None):
    if name not in dict((value, title) for title, value in DESIGNS):
        raise ValueError(tr('Unbekanntes Lumen-Theme.'))
    destination = Path(destination or Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'plasma/desktoptheme')
    identity = 'org.lumen.' + name
    target = destination / identity
    if target.exists():
        metadata = json.loads((target / 'metadata.json').read_text())
        if metadata.get('X-Lumen-Generated') != 1:
            raise ValueError(tr('Vorhandenes eigenes Plasma-Theme wird nicht überschrieben: ') + str(target))
        return target
    source = Path(source) if source else next((path for path in [ARTWORK / 'plasma/LumenDock', destination / 'LumenDock',
        Path('/usr/share/plasma/desktoptheme/default')] if path.is_dir()), None)
    if source is None:
        raise ValueError(tr('Die native Plasma-Theme-Vorlage wurde nicht gefunden.'))
    destination.mkdir(parents=True, exist_ok=True)
    window, base, alternate, text, button, border, muted, accent, on_accent = COLORS[name]
    with tempfile.TemporaryDirectory(prefix='.lumen-theme-', dir=destination) as temporary:
        stage = Path(temporary) / identity
        shutil.copytree(source, stage)
        metadata = json.loads((stage / 'metadata.json').read_text())
        metadata['KPlugin'].update(Id=identity, Name='Lumen · ' + dict((value, title) for title, value in DESIGNS)[name],
                                  Description=tr('Gemeinsames Lumen-Theme für Leisten und Panels'), Version='1.2.0')
        metadata['X-Lumen-Generated'] = 1
        (stage / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
        config = configparser.ConfigParser(); config.optionxform = str
        config.read(stage / 'colors')
        def rgb(color): return ','.join(str(int(color[i:i + 2], 16)) for i in (1, 3, 5))
        for group in ('Window', 'View', 'Button', 'Selection', 'Tooltip', 'Complementary', 'Header'):
            section = 'Colors:' + group
            background = accent if group == 'Selection' else button if group == 'Button' else base if group == 'View' else window
            foreground = on_accent if group == 'Selection' else text
            config[section] = {key: rgb(value) for key, value in {
                'BackgroundNormal': background, 'BackgroundAlternate': alternate,
                'ForegroundNormal': foreground, 'ForegroundInactive': muted,
                'ForegroundActive': accent, 'ForegroundLink': accent, 'ForegroundVisited': accent,
                'ForegroundNegative': '#ab3539' if name == 'atelier' else '#ffb9b4',
                'ForegroundNeutral': accent, 'ForegroundPositive': accent,
                'DecorationFocus': accent, 'DecorationHover': accent}.items()}
        config['Colors:Header][Inactive'] = dict(config['Colors:Header'])
        config['General'] = {'Name': 'Lumen ' + name, 'ColorScheme': identity}
        with (stage / 'colors').open('w') as stream: config.write(stream, space_around_delimiters=False)
        # The installed Lumen islands use fixed fills in their nine-slice artwork.
        # Recolor those, leaving SVG masks and layout margins intact.
        for path in stage.rglob('*.svg*'):
            if path.suffix not in ('.svg', '.svgz'): continue
            data = (gzip.decompress(path.read_bytes()) if path.suffix == '.svgz' else path.read_bytes()).decode()
            for old, new in {'#212b2f': window, '#0d1420': window, '#101925': window,
                             '#61c8c1': accent, '#60d4cb': accent}.items():
                data = data.replace(old, new)
            if path.name == 'panel-background.svgz' or path.name == 'background.svgz' and path.parent.name == 'dialogs':
                opacity = '0.91' if name == 'glass' and 'solid' not in path.parts else '1'
                data = data.replace('opacity="0.94"', 'opacity="' + opacity + '"').replace('opacity:0.94;', 'opacity:' + opacity + ';')
            path.write_bytes(gzip.compress(data.encode()) if path.suffix == '.svgz' else data.encode())
        stage.rename(target)
    return target


def apply(data):
    """Explicit settings action, never called by read-only previews or app startup."""
    from desktop_settings import backup, run
    name = data['design']
    if name in ('system', 'clear'):
        return {'desktop': False}
    target = prepare(name)
    decoration = prepare_decoration(name)
    previous_decoration = current_decoration()
    selected_decoration = decoration_settings(decoration.name)
    previous = run(['kreadconfig6', '--file', 'plasmarc', '--group', 'Theme', '--key', 'name', '--default', 'default'])
    if data.get('expected') and previous != data['expected']:
        raise ValueError(tr('Der Plasma-Stil wurde inzwischen geändert. Rückgängig wurde nicht ausgeführt.'))
    if data.get('expected') and previous_decoration != decoration_settings(
            data['expected'].replace('org.lumen.', 'org.lumen.fine.', 1)):
        raise ValueError(tr('Die Fensterdekoration wurde inzwischen geändert. Rückgängig wurde nicht ausgeführt.'))
    if previous != target.name or previous_decoration != selected_decoration:
        backup('appearance', {'before': previous, 'after': target.name,
                              'decoration_before': previous_decoration, 'decoration_after': selected_decoration})
    if previous != target.name:
        subprocess.run(['plasma-apply-desktoptheme', target.name], check=True, capture_output=True, text=True, timeout=15)
        current = run(['kreadconfig6', '--file', 'plasmarc', '--group', 'Theme', '--key', 'name'])
        if current != target.name: raise ValueError(tr('Plasma hat das Theme nicht übernommen.'))
    if previous_decoration != selected_decoration:
        set_decoration(selected_decoration, previous_decoration)
    return {'desktop': True, 'theme': target.name, 'decoration': decoration.name}


def prepare_decoration(name, destination=None, source=None):
    """Native Fine controls, shared by every decorated Lumen window and dialog."""
    titles = {value: title for title, value in DESIGNS}
    if name not in titles:
        raise ValueError(tr('Unbekanntes Lumen-Theme.'))
    destination = Path(destination or Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'aurorae/themes')
    # A new identity avoids stale KWin SVG caches and preserves old user artwork.
    identity = 'org.lumen.fine.' + name
    target = destination / identity
    if target.exists():
        if json.loads((target / 'metadata.json').read_text()).get('X-Lumen-Generated') != 1:
            raise ValueError(tr('Vorhandene eigene Fensterdekoration wird nicht überschrieben: ') + str(target))
        return target
    source = Path(source) if source else ARTWORK / 'aurorae/LumenGraphite'
    if not source.is_dir():
        raise ValueError(tr('Die Lumen-Fensterdekoration muss zuerst installiert sein.'))
    window, _, _, text, _, _, muted, accent, _ = COLORS[name]
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.lumen-decoration-', dir=destination) as temporary:
        stage = Path(temporary) / identity
        shutil.copytree(source, stage)
        metadata = json.loads((stage / 'metadata.json').read_text())
        metadata['KPlugin'].update(Id=identity, Name='Lumen Fein · ' + titles[name],
                                  Description=tr('Fensterdekoration passend zum Lumen-Theme'))
        metadata['X-Lumen-Generated'] = 1
        (stage / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
        desktop = stage / 'metadata.desktop'
        if desktop.exists():
            config = configparser.ConfigParser(); config.optionxform = str; config.read(desktop)
            config['Desktop Entry']['Name'] = 'Lumen Fein · ' + titles[name]
            config['Desktop Entry']['X-KDE-PluginInfo-Name'] = identity
            with desktop.open('w') as stream: config.write(stream, space_around_delimiters=False)
        artwork = (stage / 'decoration.svg').read_text()
        for color in ('#252b2e', '#172335', '#1b293a', '#101925'):
            artwork = artwork.replace(color, window)
        artwork = artwork.replace('#f8fafc', text)
        (stage / 'decoration.svg').write_text(artwork)
        for button in ('minimize', 'maximize', 'restore', 'close'):
            path = stage / (button + '.svg')
            artwork = path.read_text().replace('#72c9b1', text).replace('#aebcb8', muted)
            if name == 'atelier': artwork = artwork.replace('#ffb9b4', '#ab3539')
            path.write_text(artwork)
        config = configparser.ConfigParser(); config.optionxform = str
        original_rc = stage / (source.name + 'rc'); config.read(original_rc)
        for key, color in (('ActiveTextColor', text), ('InactiveTextColor', muted)):
            config['General'][key] = ','.join(str(int(color[i:i + 2], 16)) for i in (1, 3, 5))
        with (stage / (identity + 'rc')).open('w') as stream: config.write(stream, space_around_delimiters=False)
        original_rc.unlink()
        stage.rename(target)
    return target
