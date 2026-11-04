"""Install desktop resources; --apply sets up the desktop, --refresh-decoration updates legacy Lumen frames."""
from lumen_i18n import tr
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from appearance import DESIGNS
from lumen_desktop_theme import ARTWORK, apply, prepare, prepare_decoration, refresh_decoration


def install_resources():
    data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    for _, name in DESIGNS:
        prepare(name)
        prepare_decoration(name)
    for wallpaper in (ARTWORK / 'wallpapers').iterdir():
        target = data / 'wallpapers' / wallpaper.name
        # Existing wallpaper packages can contain user edits.
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(wallpaper, target)
    return data


def configure_desktop(design):
    from desktop_settings import PLASMA, run
    # Require a live Plasma session before making any changes.
    screens = json.loads(run(PLASMA + ['print(JSON.stringify(desktops().map(function(d){return d.screen;})));']))
    if not screens or any(screen < 0 for screen in screens):
        raise ValueError(tr('Plasma muss zuerst vollständig mit einem aktiven Desktop gestartet sein.'))
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state'))
    backup = state / 'lumen/settings-backups' / ('desktop-' + str(time.time_ns()))
    backup.mkdir(parents=True, mode=0o700)
    names = ['plasma-org.kde.plasma.desktop-appletsrc', 'plasmarc', 'kwinrc',
             'Lumen/Assistant.conf']
    missing = []
    for name in names:
        source = config / name
        if source.is_file():
            target = backup / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        else:
            missing.append(name)
    (backup / 'missing.json').write_text(json.dumps(missing))
    previous = subprocess.run(['systemctl','--user','is-enabled','lumen-topbar.service'],capture_output=True,text=True)
    (backup/'topbar-enabled.json').write_text(json.dumps(previous.stdout.strip() in ('enabled','enabled-runtime')))
    print(tr('Sicherung:'), backup, flush=True)
    data = install_resources()
    apply({'design': design})
    from PySide6.QtCore import QSettings
    settings = QSettings('Lumen', 'Assistant')
    settings.setValue('appearance', design)
    settings.sync()
    wallpaper = data / 'wallpapers/LumenLichtstrom/contents/images'
    image = next(wallpaper.glob('*.png'))
    options = {'wallpaper': image.as_uri()}
    script = 'var options = ' + json.dumps(options) + ';\n' + (ARTWORK / 'topbar.js').read_text() + '\n' + (ARTWORK / 'layout.js').read_text()
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    subprocess.run(['systemctl','--user','start','lumen-topbar.service'],check=True)
    # The service is ready before any previous top panel is removed.
    run(['qdbus6','org.lumen.Topbar','/Topbar'])
    bridge = (ARTWORK/'topbar.js').read_text()
    token=str(time.time_ns())
    run(PLASMA+[bridge+'\ninstallLumenNotificationHost('+json.dumps(token)+');'])
    for attempt in range(50):
        if run(PLASMA+[bridge+'\nprint(lumenNotificationHostReady('+json.dumps(token)+'));']).strip()=='true':break
        time.sleep(.1)
    else:raise ValueError(tr('Der Lumen-Mitteilungsdienst ist nicht bereit; vorhandene Panels bleiben erhalten.'))
    result = json.loads(run(PLASMA + [script]))
    run(PLASMA+[bridge+"\nactivateLumenNotificationHost();"])
    subprocess.run(['systemctl','--user','enable','lumen-topbar.service'],check=True)
    subprocess.run(['kwriteconfig6','--file','kwinrc','--group','ModifierOnlyShortcuts','--key','Meta',
                    'org.lumen.Topbar,/Topbar,org.lumen.Topbar,ShowApps'],check=True)
    subprocess.run(['qdbus6','org.kde.KWin','/KWin','reconfigure'],check=True)
    retire_topbar_code(backup)
    (backup / 'created-panels.json').write_text(json.dumps(result, indent=2))
    print(tr('Lumen-Desktop eingerichtet. Rückweg: lumen-desktop-setup --restore'), backup)
    return result


def retire_topbar_code(backup):
    data=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))
    old=[data/'plasma/plasmoids'/('org.lumen.'+name) for name in ('agent','islands','system','search','control','appmenu','topbarcontext')]
    old.append(ARTWORK/'appmenu.js')
    for path in old:
        if path.exists() or path.is_symlink():
            target=backup/'retired-code'/path.name;target.parent.mkdir(exist_ok=True)
            shutil.move(str(path),str(target))


def restore(folder):
    retired=Path(folder)/'retired-code'
    data=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))
    targets={path:(ARTWORK/'appmenu.js' if path.name=='appmenu.js' else data/'plasma/plasmoids'/path.name) for path in retired.iterdir()} if retired.exists() else {}
    if any(path.exists() or path.is_symlink() for path in targets.values()):
        raise ValueError(tr('Ein früheres Topbar-Paket wurde zwischenzeitlich erneut installiert. Rückweg zuerst prüfen.'))
    # Plasma must be logged out so it cannot overwrite the recovered configuration.
    check = subprocess.run(['qdbus6', 'org.kde.plasmashell', '/PlasmaShell'],
                           capture_output=True, timeout=5)
    if check.returncode == 0:
        raise ValueError(tr('Zum Wiederherstellen von Plasma abmelden und den Befehl in einer Textkonsole ausführen.'))
    folder = Path(folder)
    missing = json.loads((folder / 'missing.json').read_text())
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    for name in ['plasma-org.kde.plasma.desktop-appletsrc', 'plasmarc', 'kwinrc', 'Lumen/Assistant.conf']:
        target = config / name
        if name in missing:
            target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(folder / name, target)
    enabled = folder/'topbar-enabled.json'
    if enabled.exists():
        subprocess.run(['systemctl','--user','--no-reload','enable' if json.loads(enabled.read_text()) else 'disable','lumen-topbar.service'],check=True)
    for source,target in targets.items():
        target.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(source),str(target))
    print(tr('Konfiguration wiederhergestellt. Jetzt bei Plasma anmelden.'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help=tr('Lumen-Theme, Hintergrund und Panels aktivieren'))
    parser.add_argument('--refresh-decoration', action='store_true', help=tr('Aktive ältere Lumen-Fensterdekoration auf Fein aktualisieren'))
    parser.add_argument('--theme', choices=[name for _, name in DESIGNS], default='glass')
    parser.add_argument('--restore', metavar='BACKUP', help=tr('Gesicherte Konfiguration nach Abmeldung wiederherstellen'))
    args = parser.parse_args()
    if args.restore and (args.apply or args.refresh_decoration):
        parser.error(tr('--restore kann nicht mit --apply kombiniert werden'))
    try:
        if args.restore:
            restore(args.restore)
        elif args.apply:
            configure_desktop(args.theme)
        else:
            install_resources()
            refreshed = (args.refresh_decoration and os.environ.get('DBUS_SESSION_BUS_ADDRESS')
                         and all(shutil.which(command) for command in ('kreadconfig6', 'kwriteconfig6', 'qdbus6'))
                         and refresh_decoration())
            print(tr('Lumen Fein aktiviert; Fensteraktionen rechts.') if refreshed else
                  tr('Vier Themes und elf Hintergrundbilder installiert; Desktop unverändert.'))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
