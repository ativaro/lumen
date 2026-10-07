#!/usr/bin/env python3
"""Install a Lumen Dark derivative with visible, rounded top islands.

By default only north panel artwork and popups differ. --dock derives LumenDock
from LumenIslands, styling the south panel and native task/pager indicators.
Activate with: plasma-apply-desktoptheme LumenIslands
"""
import argparse
import gzip
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dock', action='store_true')
args = parser.parse_args()
root = Path.home() / '.local/share/plasma/desktoptheme'
source = root / ('LumenIslands' if args.dock else 'LumenDark')
target = root / ('LumenDock' if args.dock else 'LumenIslands')
prefix = 'south' if args.dock else 'north'
if not source.is_dir():
    raise SystemExit(f'{source.name} muss zuerst installiert sein.')
shutil.copytree(source, target, dirs_exist_ok=True)
metadata = json.loads((target / 'metadata.json').read_text())
metadata['KPlugin'].update(Id=target.name, Name='Lumen Dock' if args.dock else 'Lumen Inseln', Version='1.2.0',
                          Description='Runde Glasinseln und ruhige Lumen-Systemmenüs')
(target / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
ns = 'http://www.w3.org/2000/svg'
ET.register_namespace('', ns)

def element(parent, kind, **attrs):
    return ET.SubElement(parent, '{' + ns + '}' + kind, {k:str(v) for k,v in attrs.items()})

# Nine-slice artwork, 28 px corners. Native Plasma direction prefixes.
parts = {
    'center': ('rect', dict(x=28, y=28, width=8, height=8)),
    'top': ('rect', dict(x=28, y=0, width=8, height=28)),
    'bottom': ('rect', dict(x=28, y=36, width=8, height=28)),
    'left': ('rect', dict(x=0, y=28, width=28, height=8)),
    'right': ('rect', dict(x=36, y=28, width=28, height=8)),
    'topleft': ('path', dict(d='M28 0A28 28 0 0 0 0 28H28Z')),
    'topright': ('path', dict(d='M36 0A28 28 0 0 1 64 28H36Z')),
    'bottomleft': ('path', dict(d='M0 36A28 28 0 0 0 28 64V36Z')),
    'bottomright': ('path', dict(d='M36 64A28 28 0 0 0 64 36H36Z')),
}
for name in ('widgets/panel-background.svgz', 'solid/widgets/panel-background.svgz'):
    path = target / name
    svg = ET.fromstring(gzip.decompress(path.read_bytes()))
    for parent in svg.iter():
        for child in list(parent):
            if child.get('id', '').startswith(prefix + '-'):
                parent.remove(child)
    for suffix, (kind, attrs) in parts.items():
        element(svg, kind, id=prefix + '-' + suffix, fill='#212b2f', opacity='0.94', **attrs)
        element(svg, kind, id=prefix + '-mask-' + suffix, fill='#000000', **attrs)
    for side in ('left', 'right', 'top', 'bottom'):
        # Keep rectangular pager cells inside the rounded dock end caps.
        margin = 28 if args.dock and side in ('left', 'right') else 10
        element(svg, 'rect', id=prefix + '-hint-' + side + '-margin', width=margin, height=margin, fill='#ff00ff')
    path.write_bytes(gzip.compress(ET.tostring(svg)))
for name in (() if args.dock else ('dialogs/background.svgz', 'solid/dialogs/background.svgz')):
    path = target / name
    data = gzip.decompress(path.read_bytes()).decode()
    data = data.replace('fill:#0d1420', 'fill:#212b2f').replace('opacity:0.65;', 'opacity:0.94;')
    path.write_bytes(gzip.compress(data.encode()))
if args.dock:
    path = target / 'widgets/tasks.svgz'
    svg = ET.fromstring(gzip.decompress(path.read_bytes()))
    for group in svg:
        state = group.get('id', '').split('-')[0]
        for node in group.iter():
            if state == 'focus':
                node.set('style', node.get('style', '').replace('opacity:0.01', 'opacity:0.12'))
            if node.get('width') == '4' and node.get('height') == '4':
                node.attrib.pop('class', None)
                node.set('fill', '#61c8c1')
    path.write_bytes(gzip.compress(ET.tostring(svg)))
    path = target / 'widgets/pager.svgz'
    svg = ET.fromstring(gzip.decompress(path.read_bytes()))
    for node in svg.iter():
        if node.get('class') == 'ColorScheme-ButtonFocus':
            node.attrib.pop('class')
            style = node.get('style', '').replace('currentColor', '#61c8c1')
            if node.get('id') == 'active-center':
                style = style.replace('opacity:0.6', 'opacity:0.14')
            node.set('style', style)
    path.write_bytes(gzip.compress(ET.tostring(svg)))
# No changes to the user's global font or window decoration.
print(target)
