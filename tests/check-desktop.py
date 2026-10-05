#!/usr/bin/python3
"""Exercise the installed desktop in a disposable, headless Plasma session."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import sys
import time

REPO = Path(__file__).resolve().parent.parent


def search_activation(root):
    """Observe mapped Search windows in the real disposable Wayland compositor."""
    from PySide6.QtCore import QObject, Slot, ClassInfo
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtDBus import QDBusConnection
    from PySide6.QtTest import QTest
    app = QGuiApplication.instance() or QGuiApplication([])
    @ClassInfo(**{'D-Bus Interface': 'org.lumen.DesktopTest'})
    class Observer(QObject):
        result = None
        @Slot(str)
        def report(self, value): self.result = json.loads(value)
    observer = Observer(); bus = QDBusConnection.sessionBus()
    assert bus.registerService('org.lumen.DesktopTest')
    assert bus.registerObject('/Test', observer, QDBusConnection.ExportAllSlots)
    probe = root/'search-probe.js'
    probe.write_text('''callDBus("org.lumen.DesktopTest", "/Test", "org.lumen.DesktopTest", "report",
        JSON.stringify(workspace.windowList().filter(w => w.resourceClass === "lumen-search" || w.desktopFileName === "lumen-search").map(w => ({active:w.active,minimized:w.minimized}))));''')
    def windows():
        observer.result = None
        identity = subprocess.check_output(['qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.loadScript',str(probe),'lumen-search-test'],text=True).strip()
        subprocess.run(['qdbus6','org.kde.KWin','/Scripting/Script'+identity,'org.kde.kwin.Script.run'],check=True,capture_output=True)
        deadline=time.monotonic()+2
        while observer.result is None and time.monotonic()<deadline: QTest.qWait(10)
        subprocess.run(['qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.unloadScript','lumen-search-test'],check=True,capture_output=True)
        assert observer.result is not None, 'No reply from the private compositor'
        return observer.result
    other = QQuickWindow(); other.resize(300,200)
    try:
        for action in ('--search','--search','--voice'):
            subprocess.run([str(root/'data/lumen/bin/lumen-panel'),action],check=True,capture_output=True,timeout=3)
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                QTest.qWait(100); rows=windows()
                if len(rows)==1 and rows[0]['active']: break
            else: raise AssertionError('Panel failed to show/activate Search: '+action+' '+str(rows))
            QTest.qWait(500)
            assert len(windows())==1, 'Search immediately disappeared after '+action
            other.show();other.requestActivate();QTest.qWait(300)
            assert windows()==[], 'Search must dismiss on an actual outside focus change'
    finally:
        other.hide();bus.unregisterObject('/Test');bus.unregisterService('org.lumen.DesktopTest')


def session():
    root = Path(os.environ['HOME'])
    command = ['qdbus6', 'org.kde.plasmashell', '/PlasmaShell', 'org.kde.PlasmaShell.evaluateScript']
    with (root / 'plasma.log').open('w') as log:
        plasma = subprocess.Popen(['plasmashell'], stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            ready = subprocess.run(command + ['print(desktops().filter(function(d){return d.screen>=0;}).length);'],
                                   capture_output=True, text=True, timeout=5)
            if ready.returncode == 0 and ready.stdout.strip().isdigit() and int(ready.stdout) > 0:
                break
            time.sleep(.5)
        else:
            raise RuntimeError('Disposable Plasma did not start')
        snapshots = []
        for attempt in range(3):
            if attempt == 2:
                # Emulate the previous installer's single top bar and markers.
                legacy = (REPO / 'desktop/layout.js').read_text()
                legacy = legacy.replace('width >= 960', 'width >= 1600')
                legacy = legacy.replace('"lumenLayoutVersion", "2"', '"lumenLayoutVersion", "1"')
                legacy = legacy.replace('=== "2"', '=== "1"').replace('!== "2"', '!== "1"')
                script = ('panels().forEach(function(p){p.remove();});\n'
                          'var options={replacePanels:true,wallpaper:""};\n' + legacy)
                subprocess.run(command+[script], check=True, capture_output=True, timeout=10)
            command_setup = ([sys.executable, str(root / 'data/lumen/files/lumen_setup.py'), 'desktop', '--theme', 'glass']
                             if attempt == 0 else [str(root / 'data/lumen/bin/lumen-desktop-setup'), '--apply', '--replace-panels'])
            subprocess.run(command_setup,
                           check=True, timeout=40)
            time.sleep(2)
            script = '''print(JSON.stringify(panels().map(function(p){return {
                id:p.id,screen:p.screen,location:p.location,length:p.length,offset:p.offset,alignment:p.alignment,
                widgets:p.widgets().map(function(w){return w.type;})};})));'''
            rows = json.loads(subprocess.check_output(command + [script], text=True, timeout=5))
            assert rows and all(row['screen'] >= 0 for row in rows), rows
            for screen in range(int(ready.stdout)):
                if int(os.environ.get('LUMEN_TEST_WIDTH', '1920')) >= 960:
                    top = [row for row in rows if row['screen'] == screen and row['location'] == 'top']
                    assert len(top) == 3, rows
                    width = int(os.environ.get('LUMEN_TEST_WIDTH', '1920'))
                    assert sum(p['length'] for p in top) <= width - 64, top
                widgets = [w for row in rows if row['screen'] == screen for w in row['widgets']]
                for name in ('system', 'search', 'control'):
                    assert widgets.count('org.lumen.' + name) == 1, widgets
                for name in ('icontasks', 'pager', 'systemtray', 'digitalclock'):
                    assert widgets.count('org.kde.plasma.' + name) == 1, widgets
            snapshots.append(rows)
        assert snapshots[0] == snapshots[1], 'Setup created duplicate panels'
        assert [row['widgets'] for row in snapshots[0]] == [row['widgets'] for row in snapshots[2]], 'Legacy layout migration lost widgets'
        (root / 'passed.json').write_text(json.dumps(snapshots[2], indent=2))
        search_activation(root)
    finally:
        plasma.terminate()
        try:
            plasma.wait(timeout=10)
        except subprocess.TimeoutExpired:
            plasma.kill(); plasma.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--width', type=int, default=1920)
    parser.add_argument('--screens', type=int, default=2)
    parser.add_argument('--session', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.session:
        session(); return
    for tool in ('dbus-run-session', 'kwin_wayland', 'plasmashell', 'qdbus6'):
        if not shutil.which(tool): parser.error('Missing: ' + tool)
    logs = REPO / 'artifacts/desktop-smoke'
    logs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lumen-desktop-test-') as temporary:
        root = Path(temporary); (root / 'runtime').mkdir(mode=0o700)
        env = {k: v for k, v in os.environ.items() if k not in
               ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'PREFIX', 'OPENCODE_HOME')
               and not k.startswith(('LUMEN_', 'OPENCODE_'))}
        env.update(LUMEN_PYTHON=sys.executable, HOME=str(root), XDG_CONFIG_HOME=str(root / 'config'), XDG_DATA_HOME=str(root / 'data'),
                   XDG_STATE_HOME=str(root / 'state'), XDG_CACHE_HOME=str(root / 'cache'),
                   XDG_RUNTIME_DIR=str(root / 'runtime'), QT_QPA_PLATFORM='offscreen',
                   DBUS_SESSION_BUS_ADDRESS='unix:path=' + str(root / 'runtime/no-bus'))
        with (logs / 'install.log').open('w') as log:
            subprocess.run(['bash', str(REPO / 'install.sh'), '--no-mcp', '--no-timer'], env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
        env.pop('DBUS_SESSION_BUS_ADDRESS')
        env.update(QT_QPA_PLATFORM='wayland', WAYLAND_DISPLAY='lumen-test', KWIN_COMPOSE='QPainter',
                   LUMEN_TEST_WIDTH=str(args.width),
                   XDG_CURRENT_DESKTOP='KDE', XDG_SESSION_TYPE='wayland', KDE_FULL_SESSION='true', KDE_SESSION_VERSION='6')
        helper = root / 'session'
        helper.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(Path(__file__).resolve())) + ' --session\n')
        helper.chmod(0o755)
        with (logs / 'session.log').open('w') as log:
            subprocess.run(['dbus-run-session', '--', 'kwin_wayland', '--virtual', '--xwayland',
                            '--width', str(args.width), '--height', '900', '--output-count', str(args.screens),
                            '--no-lockscreen', '--no-global-shortcuts', '--socket', 'lumen-test',
                            '--exit-with-session', str(helper)], env=env, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=100)
        if not (root / 'passed.json').exists():
            raise RuntimeError('Desktop check failed; see ' + str(logs / 'session.log'))
        shutil.copy2(root / 'passed.json', logs / 'panels.json')
    print('Fresh-profile install, desktop roles and repeated setup passed.')


if __name__ == '__main__': main()
