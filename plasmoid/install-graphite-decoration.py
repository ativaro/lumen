#!/usr/bin/env python3
"""Create a Graphite Aurorae decoration from the installed Lumen Dark artwork.

Select “Lumen Graphit” in KDE's window decoration settings, then arrange the
left buttons as close, minimize, maximize (kwinrc ButtonsOnLeft=XIA).
"""
import json
from pathlib import Path
import shutil

root = Path.home() / '.local/share/aurorae/themes'
source = root / 'LumenDark'
target = root / 'LumenGraphite'
if not source.is_dir():
    raise SystemExit('LumenDark muss zuerst installiert sein.')
if target.exists():
    raise SystemExit(f'{target} existiert bereits; vorhandene Anpassungen bleiben erhalten.')

artwork = (source / 'decoration.svg').read_text()
for color in ('#172335', '#1b293a', '#101925'):
    if color not in artwork:
        raise SystemExit(f'Unerwartete LumenDark-Vorlage: {color} fehlt.')
    artwork = artwork.replace(color, '#252b2e')
settings = (source / 'LumenDarkrc').read_text().replace(
    'ActiveTextColor=248,250,252', 'ActiveTextColor=232,238,240').replace(
    'InactiveTextColor=148,163,184', 'InactiveTextColor=164,175,181')
metadata = json.loads((source / 'metadata.json').read_text())
metadata['KPlugin'].update(Id='LumenGraphite', Name='Lumen Graphit',
                          Description='Graphitfarbene Fensterdekoration passend zu Lumen Files')
desktop = (source / 'metadata.desktop').read_text().replace(
    'Name=Lumen Dark', 'Name=Lumen Graphit').replace('Name=LumenDark', 'Name=LumenGraphite')

shutil.copytree(source, target)
(target / 'decoration.svg').write_text(artwork)
(target / 'LumenDarkrc').unlink()
(target / 'LumenGraphiterc').write_text(settings)
(target / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
(target / 'metadata.desktop').write_text(desktop)
print(target)
