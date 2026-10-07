#!/usr/bin/env python3
"""Reload only Lumen role widgets using fresh canonical URLs, preserving the shell.

Run explicitly after a package update, inside the user's Plasma session. Temporary
KPackage aliases are removed afterward; the next login uses the installed package.
Keep the runtime copies while this Plasma process is still using their QML URLs.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


def run(arguments):
    return subprocess.check_output(arguments, text=True, timeout=20)


def evaluate(script):
    return json.loads(run(['qdbus6', 'org.kde.plasmashell', '/PlasmaShell', 'org.kde.PlasmaShell.evaluateScript', script]))


def main():
    data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state'))
    stamp = time.strftime('%Y%m%d-%H%M%S')
    backup = state / 'lumen/settings-backups' / ('panel-themes-' + stamp)
    runtime = data / 'lumen/plasmoid-runtime' / stamp
    aliases = data / 'plasma/plasmoids'
    roles = ['org.lumen.' + role for role in ('system', 'search', 'control')]
    for identity in roles:
        if (aliases / identity).exists() or (aliases / identity).is_symlink():
            raise ValueError('Vorhandene Benutzerkopie zuerst prüfen: ' + identity)
        if not (Path('/usr/share/plasma/plasmoids') / identity / 'metadata.json').is_file():
            raise ValueError('Systempaket fehlt: ' + identity)
    snapshot = '''print(JSON.stringify(panels().map(function(p){return {id:p.id,height:p.height,widgets:p.widgets().map(function(w){w.currentConfigGroup=["General"];return {id:w.id,type:w.type,index:w.index,shortcut:w.globalShortcut,surface:w.readConfig("surface","")};})};})));'''
    before = evaluate(snapshot)
    if not any(w['type'] in roles for p in before for w in p['widgets']):
        raise ValueError('Keine Lumen-Leisten gefunden.')
    backup.mkdir(parents=True); runtime.mkdir(parents=True); aliases.mkdir(parents=True, exist_ok=True)
    (backup / 'before.json').write_text(json.dumps(before, indent=2))
    shutil.copy2(Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'plasma-org.kde.plasma.desktop-appletsrc', backup / 'appletsrc')
    created = []
    try:
        for identity in roles:
            shutil.copytree(Path('/usr/share/plasma/plasmoids') / identity, runtime / identity)
            (aliases / identity).symlink_to(runtime / identity, target_is_directory=True)
            created.append(aliases / identity)
        run(['kbuildsycoca6', '--noincremental'])
        changed = evaluate('''var roles=''' + json.dumps(roles) + ''';var changed=[];
        panels().forEach(function(p){p.widgets().filter(function(w){return roles.includes(w.type);}).forEach(function(old){
            old.currentConfigGroup=["General"];var role=old.readConfig("surface",""),index=old.index,id=old.id,type=old.type,shortcut=old.globalShortcut;
            var fresh=p.addWidget(type);fresh.currentConfigGroup=["General"];fresh.writeConfig("surface",role);fresh.reloadConfig();
            changed.push({panel:p.id,old:id,id:fresh.id,type:type,role:role,index:index});old.remove();fresh.index=index;fresh.globalShortcut=shortcut;
        });});print(JSON.stringify(changed));''')
        (backup / 'widgets.json').write_text(json.dumps(changed, indent=2))
        # Plasma may retain the previous preferred width until a panel reflow.
        evaluate('var rows=' + json.dumps([p for p in before if p['id'] in {w['panel'] for w in changed}]) + ';rows.forEach(function(r){panelById(r.id).height=r.height+1;});print(true);')
        time.sleep(.3)
        evaluate('var rows=' + json.dumps([p for p in before if p['id'] in {w['panel'] for w in changed}]) + ';rows.forEach(function(r){panelById(r.id).height=r.height;});print(true);')
        after = evaluate(snapshot); (backup / 'after.json').write_text(json.dumps(after, indent=2))
        for previous in before:
            current = next(row for row in after if row['id'] == previous['id'])
            assert [w for w in previous['widgets'] if w['type'] not in roles] == [w for w in current['widgets'] if w['type'] not in roles]
            assert previous['height'] == current['height']
        print(json.dumps({'backup': str(backup), 'runtime': str(runtime), 'widgets': changed}, indent=2))
    finally:
        for alias in created:
            if alias.is_symlink() and alias.resolve().parent == runtime:
                alias.unlink()
        run(['kbuildsycoca6', '--noincremental'])


if __name__ == '__main__': main()
