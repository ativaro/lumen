#!/usr/bin/python3
"""Real synthetic-window capture in an isolated KWin session; never the host desktop."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO/'files'))


def session():
    from PySide6.QtCore import QObject, Slot, ClassInfo
    from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit
    from PySide6.QtDBus import QDBusConnection
    from PySide6.QtTest import QTest
    from screen_companion import Companion
    from app import create_app
    app = create_app('glass'); app.setApplicationName('lumen-guide-test'); app.setApplicationDisplayName('Synthetic guide target')
    target = QWidget(); target.setWindowTitle('Synthetic guide target'); target.resize(600,400)
    layout = QVBoxLayout(target); layout.addWidget(QLabel('Synthetic server setup · Step one'))
    password = QLineEdit(); password.setPlaceholderText('Synthetic field'); layout.addWidget(password)
    target.show(); QTest.qWait(1200)
    @ClassInfo(**{'D-Bus Interface': 'org.lumen.GuideTest'})
    class Observer(QObject):
        result = None
        @Slot(str)
        def report(self, value): self.result = json.loads(value)
    observer = Observer(); bus = QDBusConnection.sessionBus()
    assert bus.registerService('org.lumen.GuideTest')
    assert bus.registerObject('/Test', observer, QDBusConnection.ExportAllSlots)
    probe = Path(os.environ['HOME'])/'probe.js'
    probe.write_text('''callDBus("org.lumen.GuideTest","/Test","org.lumen.GuideTest","report",
        JSON.stringify(workspace.windowList().filter(w=>w.caption.startsWith("Synthetic guide target")).map(w=>({uuid:w.internalId.toString(),pid:w.pid,caption:w.caption,app:w.resourceClass}))));''')
    identity = subprocess.check_output(['qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.loadScript',str(probe),'guide-test'],text=True).strip()
    subprocess.run(['qdbus6','org.kde.KWin','/Scripting/Script'+identity,'org.kde.kwin.Script.run'],check=True,capture_output=True)
    for _ in range(100):
        if observer.result is not None: break
        QTest.qWait(20)
    assert observer.result and len(observer.result)==1, observer.result
    guide = Companion(); guide.show(); guide.target = observer.result[0]; guide.active = True
    results = []
    def capture():
        results.clear(); guide.run_worker('capture',results.append)
        for _ in range(150):
            if guide.proc is None: break
            QTest.qWait(100)
        assert results, guide.status.text()
        return results[0]
    data = capture(); assert data.get('png'), data
    print('Initial protection:', data['protection'], flush=True)
    # Review never sends to a real provider.
    guide.selected.setText('Synthetic guide target')
    guide.pending = 'Help with synthetic setup'; guide.captured(data, False)
    assert guide.approve.isVisible() and guide.png and not guide.backend.busy
    guide.grab().save(str(REPO/'artifacts/companion-smoke.png'))
    password.setEchoMode(QLineEdit.Password); password.setText('synthetic-not-a-secret'); QTest.qWait(300)
    protected = capture()
    print('Password protection:', protected['protection'], flush=True)
    assert protected['protection'] in ('password', 'unknown'), protected['protection']
    if protected['protection'] == 'password': assert 'png' not in protected
    guide.pause(); assert not guide.png and not guide.active and guide.image.isNull()
    # An invalid target is rejected; no active-window fallback.
    guide.target['uuid'] = '{00000000-0000-0000-0000-000000000000}'
    guide.run_worker('capture', results.append)
    for _ in range(150):
        if guide.proc is None: break
        QTest.qWait(100)
    assert not guide.active and not guide.png
    import fcntl
    from lumen_launch import executable
    lease = os.open(Path(os.environ['XDG_RUNTIME_DIR'])/'lumen-vault-privacy.lock', os.O_RDWR)
    fcntl.flock(lease, fcntl.LOCK_SH)
    second = os.open(Path(os.environ['XDG_RUNTIME_DIR'])/'lumen-vault-privacy.lock', os.O_RDWR)
    result = subprocess.run([executable('lumen-window-capture'), observer.result[0]['uuid'], str(second)], pass_fds=(second,), capture_output=True)
    assert result.returncode == 2 and not result.stdout, 'Native capture ignored the Vault lease'
    os.close(second); os.close(lease)
    guide.close(); target.close(); app.processEvents()
    Path(os.environ['HOME'],'passed').touch()


def main():
    if '--session' in sys.argv: session(); return
    artifacts = REPO/'artifacts'; artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lumen-guide-test-') as temporary:
        root=Path(temporary); (root/'runtime').mkdir(mode=0o700)
        env={k:v for k,v in os.environ.items() if k not in ('DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS') and not k.startswith(('LUMEN_', 'OPENCODE_'))}
        env.update(HOME=str(root),XDG_RUNTIME_DIR=str(root/'runtime'),XDG_CONFIG_HOME=str(root/'config'),
            XDG_DATA_HOME=str(root/'data'),XDG_STATE_HOME=str(root/'state'),XDG_CACHE_HOME=str(root/'cache'),
            QT_QPA_PLATFORM='wayland',WAYLAND_DISPLAY='lumen-test',KWIN_COMPOSE='O2',LIBGL_ALWAYS_SOFTWARE='1',LUMEN_LANGUAGE='de',
            XDG_CURRENT_DESKTOP='KDE',XDG_SESSION_TYPE='wayland',QT_LINUX_ACCESSIBILITY_ALWAYS_ON='1')
        (root/'bin').mkdir(); (root/'data/applications').mkdir(parents=True)
        subprocess.run(['bash',str(REPO/'native/build-capture.sh'),str(root/'bin/lumen-window-capture')],check=True)
        (root/'data/applications/lumen-window-capture.desktop').write_text((REPO/'data/applications/lumen-window-capture.desktop').read_text().replace('%INSTALL_BIN%',str(root/'bin')))
        env['LUMEN_BIN_DIR']=str(root/'bin')
        helper=root/'session'; helper.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' '+shlex.quote(str(Path(__file__).resolve()))+' --session\n'); helper.chmod(0o755)
        with (artifacts/'companion-smoke.log').open('w') as log:
            subprocess.run(['dbus-run-session','--','kwin_wayland','--virtual','--xwayland','--width','1280','--height','900','--output-count','1','--no-lockscreen','--no-global-shortcuts','--socket','lumen-test','--exit-with-session',str(helper)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=70)
        assert (root/'passed').exists(), 'See artifacts/companion-smoke.log'
    print('Isolated KWin capture, local preview, pause and invalid-target checks passed.')

if __name__ == '__main__': main()
