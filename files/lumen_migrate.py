"""Non-destructive, idempotent migration of legacy Lumen reports."""
import os
from pathlib import Path
import shutil


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



def migrate_launchers(binary_directory):
    """Update only known Lumen references; preserve custom fields and a backup."""
    data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    config = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    legacy = str(data / 'opencode-lumen' / 'bin')
    targets = list((data / 'applications').glob('lumen*.desktop'))
    targets += [data / 'plasma_icons/lumen.desktop', data / 'plasma_icons/lumen-files.desktop', data / 'dbus-1/services/org.lumen.runner.service',
                data / 'kio/servicemenus/lumen.desktop', config / 'autostart/lumen-krunner-runner.desktop',
                config / 'opencode/opencode.jsonc', config / 'opencode/opencode.json']
    targets += list((config / 'systemd/user').glob('lumen*.service'))
    applet = data / 'plasma/plasmoids/org.lumen.agent/contents/ui/main.qml'
    targets.append(applet)
    changed = []
    for path in targets:
        if not path.is_file() or path.is_symlink(): continue
        original = path.read_text()
        updated = original.replace(legacy + '/', str(Path(binary_directory)) + '/')
        if path.name == 'lumen-files.desktop':
            updated = updated.replace('Name=Lumen — Dateien\n','Name=Lumen Files\n').replace('Name[en]=Lumen — Files\n','Name[en]=Lumen Files\n').replace('StartupWMClass=Lumen\n','StartupWMClass=lumen-files\n')
        if path == applet:
            updated = updated.replace('onClicked: root.expanded = !root.expanded', 'onClicked: root.run("lumen")')
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
    parser = argparse.ArgumentParser(description='Lumen-Benutzerdaten übernehmen')
    parser.add_argument('--bin')
    args = parser.parse_args(); migrate_user()
    if args.bin:
        for path in migrate_launchers(args.bin): print('Starter aktualisiert: ' + path)
