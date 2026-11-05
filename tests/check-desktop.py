#!/usr/bin/python3
"""Test the native bar and desktop scripts in an isolated Wayland session."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import time

REPO=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--width',type=int,default=1280)
parser.add_argument('--scale',type=float,default=1)
parser.add_argument('--theme',choices=['glass','graphite','atelier','midnight'],default='graphite')
parser.add_argument('--layout',choices=['classic','band','deck','context'],default='classic')
parser.add_argument('--language',choices=['de','en'],default='de')
parser.add_argument('--build-dir',type=Path,default=REPO/'artifacts/desktop-smoke/build')
parser.add_argument('--artifacts',type=Path,default=REPO/'artifacts/desktop-smoke')
parser.add_argument('--surface-only',action='store_true',help='Skip the already qualified notification/layout integration for theme checks')
parser.add_argument('--shortcuts',action='store_true',help='Exercise the real global launch keys in the private session')
args=parser.parse_args()
if args.width<600 or not 1<=args.scale<=3:parser.error('Use a width >= 600 and scale between 1 and 3')
for name in ('bwrap','kwin_wayland','qdbus6','kscreen-doctor','dbus-run-session','kpackagetool6'):
    if not shutil.which(name):parser.error('Missing test tool: '+name)
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
began=time.monotonic()
args.artifacts.mkdir(parents=True,exist_ok=True)
profile=args.artifacts/(args.theme+'-'+str(time.time_ns()))
profile.mkdir(mode=0o700)
build=args.build_dir.resolve()
with (profile/'build.log').open('w') as log:
    subprocess.run(['cmake','-S',str(REPO/'native/topbar'),'-B',str(build),'-DBUILD_TESTING=ON','-DCMAKE_BUILD_TYPE=RelWithDebInfo'],stdout=log,stderr=subprocess.STDOUT,check=True)
    subprocess.run(['cmake','--build',str(build),'--parallel','2'],stdout=log,stderr=subprocess.STDOUT,check=True)
for name in ('home','config','data/applications','state','runtime','cache','captures'):
    (profile/name).mkdir(parents=True,exist_ok=True,mode=0o700)
(profile/'config/Lumen').mkdir()
(profile/'config/Lumen/Assistant.conf').write_text('[General]\nappearance='+args.theme+'\n[topbar]\nlayout='+args.layout+'\n')
if args.shortcuts:
    (profile/'bin').mkdir()
    for name in ('lumen-apps','lumen-quick'):
        shutil.copy2(REPO/'bin'/name,profile/'bin'/name)
    start=profile/'bin/lumen-apps';start.write_text(start.read_text().replace('exec qdbus6','touch /profile/start-shortcut-invoked\nexec qdbus6'))
    service=profile/'bin/systemctl';service.write_text('#!/bin/sh\nif [ "$*" = "--user start lumen-topbar.service" ]; then exit 0; fi\nexec /usr/bin/systemctl "$@"\n');service.chmod(0o755)
    launcher=profile/'bin/lumen-agent-app';launcher.write_text('#!/bin/sh\nexec /usr/bin/touch /profile/lumen-shortcut-started\n');launcher.chmod(0o755)
    for name in ('lumen-apps','lumen-ask','lumen-toggle'):
        text=(REPO/'data/applications'/(name+'.desktop')).read_text().replace('%INSTALL_BIN%','/profile/bin')
        (profile/'data/applications'/(name+'.desktop')).write_text(text)
    (profile/'config/kglobalshortcutsrc').write_text('[services][lumen-toggle.desktop]\n_launch=Meta\n[services][org.kde.krunner.desktop]\n_launch=Alt+Space\n[services][lumen-ask.desktop]\n_launch=Meta+Shift+O\n')
    (profile/'config/kwinrc').write_text('[ModifierOnlyShortcuts]\nMeta=org.lumen.Topbar,/Topbar,org.lumen.Topbar,ShowApps\n')
pin_ids=[]
for identity,title,icon,category in [('browser','Browser','internet-web-browser','Network'),('files','Dateien','folder','Utility'),
        ('lumen','Lumen','search','Utility'),('kate','Kate','accessories-text-editor','Development'),
        ('steam','Steam','applications-games','Game'),('music','Musik','headphones','AudioVideo')]:
    name='lumen-start-'+identity+'.desktop';pin_ids.append(name)
    (profile/'data/applications'/name).write_text('[Desktop Entry]\nType=Application\nName='+title+'\nExec=/usr/bin/touch /profile/pinned-started\nIcon='+icon+'\nCategories='+category+';\n')
with (profile/'config/Lumen/Assistant.conf').open('a') as output:output.write('pinnedApps='+', '.join(pin_ids)+'\n')
host=profile/'host-stage'
shutil.copytree(REPO/'plasmoid',host)
qml=host/'contents/ui/main.qml';qml.write_text(qml.read_text().replace('/usr/bin/lumen-panel','/qa/bin/lumen-panel'))
(profile/'config/plasma-org.kde.plasma.desktop-appletsrc').write_text('[Containments][1]\nformfactor=0\nlastScreen=0\nlocation=0\nplugin=org.kde.plasma.folder\nwallpaperplugin=org.kde.image\n')
for name in ('A','B','Empty','Browser'):
    title='Lumen Notes' if name=='A' else 'Lumen Menütest '+name
    (profile/'data/applications'/('lumen-menu-test-'+name.lower()+'.desktop')).write_text(
        '[Desktop Entry]\nType=Application\nName='+title+'\nExec=python3 /qa/fixture.py '+name+'\nIcon=application-x-executable\nNoDisplay=true\n')
(profile/'data/applications/lumen-topbar-program-test.desktop').write_text('[Desktop Entry]\nType=Application\nName=Lumen Testprogramm\nExec=/usr/bin/touch /profile/program-started\nIcon=application-x-executable\nCategories=Utility;\nActions=NewWindow;\n[Desktop Action NewWindow]\nName=Neues Testfenster\nExec=/usr/bin/touch /profile/program-new-window\n')
(profile/'config/kded6rc').write_text('[Module-bluedevil]\nautoload=false\n[Module-baloo]\nautoload=false\n')
command=['bwrap','--unshare-all','--die-with-parent','--new-session','--clearenv',
    '--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib',
    '--symlink','usr/lib','/lib64','--ro-bind','/etc','/etc','--ro-bind','/sys','/sys',
    '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--bind',str(profile),'/profile',
    '--ro-bind',str(REPO),'/source','--ro-bind',str(build),'/build',
    '--ro-bind',str(REPO/'tests/desktop'),'/qa','--chdir','/profile']
# The hot-install check needs a fresh Plasma instance, even on a host running Lumen.
system_applet = Path('/usr/share/plasma/plasmoids/org.lumen.notificationhost')
if system_applet.is_dir():
    command.extend(['--tmpfs', str(system_applet)])

if Path('/dev/dri').is_dir():command+=['--dev-bind','/dev/dri','/dev/dri']
env=dict(ASAN_OPTIONS='detect_leaks=0:abort_on_error=1:log_path=/profile/asan',
    LUMEN_QA_HOT_HOST='1',LUMEN_QA_SURFACE_ONLY='1' if args.surface_only else '',
    PATH='/profile/bin:/usr/bin' if args.shortcuts else '/usr/bin',HOME='/profile/home',USER='Ativaro',XDG_CONFIG_HOME='/profile/config',XDG_DATA_HOME='/profile/data',
    XDG_STATE_HOME='/profile/state',XDG_CACHE_HOME='/profile/cache',XDG_RUNTIME_DIR='/profile/runtime',
    XDG_SESSION_TYPE='wayland',XDG_MENU_PREFIX='plasma-',XDG_CURRENT_DESKTOP='KDE',KDE_FULL_SESSION='true',KDE_SESSION_VERSION='6',
    QT_QPA_PLATFORM='wayland',QT_QUICK_CONTROLS_STYLE='Basic',QT_QPA_PLATFORMTHEME='kde',
    QT_NO_XDG_DESKTOP_PORTAL='1',LUMEN_DATA='/profile/state/lumen',LUMEN_TOOLS_DATA='/profile/state/tools',
    LUMEN_BIN_DIR='/qa/bin',LUMEN_QA_WIDTH=str(args.width),LUMEN_QA_SCALE=str(args.scale),
    LUMEN_QA_LAYOUT=args.layout,LUMEN_QA_THEME=args.theme,LUMEN_LANGUAGE=args.language,LUMEN_QA_SHORTCUTS='1' if args.shortcuts else '',LANG='de_CH.UTF-8',LC_ALL='de_CH.UTF-8')
for key,value in env.items():command+=['--setenv',key,value]
command+=['--','dbus-run-session','--','python3','-B','/qa/session.py']
with (profile/'session.log').open('w') as log:
    result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=90)
receipt=dict(passed=result.returncode==0,revision=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(),
    binary=hashlib.sha256((build/'lumen-topbar').read_bytes()).hexdigest(),
    width=args.width,scale=args.scale,theme=args.theme,language=args.language,layout=args.layout,
    notification_layout_integration=not args.surface_only,global_shortcuts=args.shortcuts,seconds=round(time.monotonic()-began,2))
(profile/'result.json').write_text(json.dumps(receipt,indent=2))
if result.returncode==0:
    for name in ('home','data','state','runtime','cache','host-stage'):
        shutil.rmtree(profile/name,ignore_errors=True)
print(json.dumps(dict(**receipt,artifacts=str(profile))))
raise SystemExit(result.returncode)
