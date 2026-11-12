"""Non-destructive, idempotent migration of legacy Lumen reports."""
from lumen_i18n import tr
import os
from pathlib import Path
import shutil
import shlex
import subprocess


def copy_missing(source, target):
    source, target = Path(source), Path(target)
    if not source.is_dir() or source.is_symlink(): return
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    for item in source.iterdir():
        destination = target / item.name
        if destination.is_symlink(): continue
        if item.is_symlink():
            resolved = item.resolve()
            if (not destination.exists() and resolved.is_relative_to(source.resolve()) and resolved.is_file()):
                destination.symlink_to(os.path.relpath(target / resolved.relative_to(source.resolve()), destination.parent))
            continue
        if item.is_dir(): copy_missing(item, destination)
        elif item.is_file() and not destination.exists():
            try:
                # Exclusive creation preserves files written concurrently by the new version.
                with item.open('rb') as before, destination.open('xb') as after: shutil.copyfileobj(before, after)
                shutil.copystat(item, destination, follow_symlinks=False)
            except FileExistsError: pass


def migrate_user():
    cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache')))
    copy_missing(cache / 'opencode-lumen', cache / 'lumen')


def retire_vault_units():
    """Stop and remove only the retired local backup timer and service units."""
    units = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'systemd/user'
    paths = [units / 'lumen-vault.timer', units / 'lumen-vault.service']
    if not any(path.exists() or path.is_symlink() for path in paths): return []
    def systemctl(*args):
        try: subprocess.run(['systemctl', '--user', *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired): pass
    systemctl('disable', '--now', 'lumen-vault.timer')
    systemctl('stop', 'lumen-vault.service')
    removed = []
    for path in paths:
        if path.exists() or path.is_symlink(): path.unlink(); removed.append(str(path))
    systemctl('daemon-reload')
    return removed


def migrate_launchers(binary_directory):
    """Update only known Lumen references; preserve custom fields and a backup."""
    data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    config = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    legacy = str(data / 'opencode-lumen' / 'bin')
    legacy_app = Path(legacy) / 'lumen-agent-app'
    current_app = Path(binary_directory).resolve() / 'lumen-agent-app'
    targets = list((data / 'applications').glob('lumen*.desktop'))
    targets += [data / 'plasma_icons/lumen.desktop', data / 'plasma_icons/lumen-files.desktop', data / 'dbus-1/services/org.lumen.runner.service',
                data / 'kio/servicemenus/lumen.desktop', config / 'autostart/lumen-krunner-runner.desktop',
                config / 'opencode/opencode.jsonc', config / 'opencode/opencode.json']
    targets += list((config / 'systemd/user').glob('lumen*.service'))
    local_bin = Path.home() / '.local/bin'
    targets += [local_bin / name for name in ('lumen', 'lumen-files', 'lumen-agent-app',
                'lumen-context', 'lumen-quick', 'lumen-sel', 'lumen-sel-run', 'lumen-vision')]
    targets.append(legacy_app)
    applet = data / 'plasma/plasmoids/org.lumen.agent/contents/ui/main.qml'
    targets.append(applet)
    changed = []
    for path in targets:
        if not path.is_file() or path.is_symlink(): continue
        try: original = path.read_text()
        except UnicodeError: continue
        if path.parent == local_bin and not original.startswith('#!/bin/sh\nexec '): continue
        updated = original.replace(legacy + '/', str(Path(binary_directory)) + '/')
        if path.name == 'lumen-sound.service':
            helper = Path(binary_directory).resolve()/'lumen-python'
            if helper.is_file() and not any(c in str(helper) for c in '\n\r%"\\'):
                module = 'sound_data.py'
                for root in (data/'lumen/files', data/'opencode-lumen/files', Path('/usr/share/lumen/files')):
                    old_command = 'ExecStart=/usr/bin/python3 "'+str(root/module)+'" '
                    new_command = 'ExecStart="'+str(helper)+'" "'+str(root/module)+'" '
                    updated = updated.replace(old_command, new_command)
        if path == legacy_app:
            # KDE can cache the old vision command; it and an already-running
            # legacy KRunner both eventually invoke this shared app launcher.
            if current_app == legacy_app.resolve() or not current_app.is_file() or not os.access(current_app, os.X_OK): continue
            template = current_app.read_text()
            if original not in (template, template.replace('/share/lumen/', '/share/opencode-lumen/')): continue
            updated = '#!/bin/sh\nexec ' + shlex.quote(str(current_app)) + ' "$@"\n'
        if path.name == 'lumen-files.desktop':
            updated = updated.replace('Name=Lumen — Dateien\n','Name=Lumen Files\n').replace('Name[en]=Lumen — Files\n','Name[en]=Lumen Files\n').replace('StartupWMClass=Lumen\n','StartupWMClass=lumen-files\n')
        if path == applet:
            updated = updated.replace('label: "App öffnen"', 'label: "Assistent öffnen"').replace('root.run("lumen-agent-app', 'root.run("lumen')
        if updated == original: continue
        backup = path.with_name(path.name + '.pre-lumen')
        if not backup.exists(): shutil.copy2(path, backup)
        temporary = path.with_name(path.name + '.lumen-new')
        try:
            with temporary.open('x') as stream:
                os.fchmod(stream.fileno(), path.stat().st_mode & 0o777)
                stream.write(updated); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally: temporary.unlink(missing_ok=True)
        changed.append(str(path))
    return changed


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=tr('Lumen-Benutzerdaten übernehmen'))
    parser.add_argument('--bin')
    args = parser.parse_args(); migrate_user()
    for path in retire_vault_units(): print(tr('Alte Sicherungseinheit entfernt: ') + path)
    if args.bin:
        for path in migrate_launchers(args.bin): print(tr('Starter aktualisiert: ') + path)
