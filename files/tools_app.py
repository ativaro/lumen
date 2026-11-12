#!/usr/bin/python3
"""Separate native entry points, with one window per application and library."""
from lumen_i18n import tr
import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
import sys
import time
from PySide6.QtCore import QSettings, QTimer, QLockFile
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from app import create_app
from lumen_activation import present


def pilot_profile():
    selected=os.environ.get('LUMEN_COMPOSE_TEXT_PILOT')
    if selected is None:return None
    root=Path(os.environ.get('LUMEN_COMPOSE_TEXT_PILOT_ROOT',''))
    def private(path):
        if (not path.is_absolute() or path.resolve()!=path or not path.is_dir()
                or path.stat().st_uid!=os.getuid() or path.stat().st_mode & 0o077):raise ValueError('Private pilot profile required.')
    if selected not in ('A','B'):raise ValueError('Private A/B pilot profile required.')
    private(root);profile=root/selected;private(profile)
    home=profile/'home';private(home);private(Path.home())
    if (home.stat().st_dev,home.stat().st_ino)!=(Path.home().stat().st_dev,Path.home().stat().st_ino):
        raise ValueError('Private pilot home mount required.')
    marker=root/'.lumen-compose-text-pilot'
    try:s=marker.lstat()
    except OSError:raise ValueError('Private synthetic pilot required.') from None
    if (not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or s.st_mode & 0o077
            or s.st_size!=23 or marker.read_text()!='private-synthetic-only\n'):raise ValueError('Private synthetic pilot required.')
    for key,name in {'LUMEN_DATA':'lumen','LUMEN_TOOLS_DATA':'tools','XDG_CONFIG_HOME':'config',
            'XDG_DATA_HOME':'data','XDG_CACHE_HOME':'cache','XDG_STATE_HOME':'state',
            'XDG_RUNTIME_DIR':'runtime','TMPDIR':'tmp'}.items():
        path=profile/name
        if os.environ.get(key)!=str(path):raise ValueError('Private pilot paths required.')
        private(path)
    return profile


def server_name(library_root):
    return 'lumen-tool-'+str(os.getuid())+'-'+hashlib.sha256(str(Path(library_root).resolve()).encode()).hexdigest()[:20]


def forward_window(root, request, *, private=False):
    endpoint=str(Path(root)/'open.sock') if private else server_name(root)
    client=QLocalSocket();client.connectToServer(endpoint)
    if not client.waitForConnected(400):return False
    client.write(json.dumps(request,ensure_ascii=False).encode()+b'\n')
    sent=client.waitForBytesWritten(1000);client.disconnectFromServer();return sent


def listen_window(page, activate, *, root=None, request_keys=()):
    """Private activation endpoint for a retained tool page."""
    endpoint = server_name(page.library.root) if root is None else str(Path(root)/'open.sock')
    server = QLocalServer(); QLocalServer.removeServer(endpoint)
    server.setSocketOptions(QLocalServer.UserAccessOption)
    if not server.listen(endpoint): raise RuntimeError(tr('Lokale Fensteraktivierung konnte nicht gestartet werden.'))
    def accept():
        socket=server.nextPendingConnection()
        if socket:
            buffer=bytearray();timer=QTimer(socket);timer.setSingleShot(True);timer.timeout.connect(socket.disconnectFromServer);timer.start(2000)
            socket.disconnected.connect(socket.deleteLater)
            def receive():
                buffer.extend(bytes(socket.readAll()))
                if len(buffer)>65536:socket.disconnectFromServer();return
                if b'\n' not in buffer:return
                try:
                    request=json.loads(buffer.split(b'\n',1)[0])
                    if root is not None:
                        if (request=={} or isinstance(request,dict) and len(request)==1
                                and next(iter(request)) in request_keys
                                and isinstance(next(iter(request.values())),str)):
                            activate(request)
                        socket.disconnectFromServer();return
                    page.safe(activate, request)
                except (ValueError,AttributeError):pass
                socket.disconnectFromServer()
            socket.readyRead.connect(receive);receive()
    server.newConnection.connect(accept)
    return server


def main():
    from lumen_paths import require_test_profile
    require_test_profile()
    pilot=pilot_profile()
    if pilot is not None and sys.argv[1:2]!=['translate']:raise ValueError('Only Compose text is available in this pilot.')
    if len(sys.argv)>1 and sys.argv[1]=='code':
        from code_app import main as collection_main
        return collection_main(sys.argv[2:])
    parser=argparse.ArgumentParser(description=tr('Eigenständige Desktop-Werkzeuge'))
    parser.add_argument('tool',choices=['meetings','household','workbench','radio','vault','inbox','reader','sound','wissen','translate'])
    parser.add_argument('path',nargs='?')
    parser.add_argument('--clipboard', action='store_true')
    parser.add_argument('--section')
    parser.add_argument('--area', choices=['user', 'lumen'])
    destination=parser.add_mutually_exclusive_group()
    destination.add_argument('--handoff')
    destination.add_argument('--ref')
    args=parser.parse_args()
    if pilot is not None:
        if args.path or args.clipboard or args.section or args.area or args.handoff or args.ref:
            parser.error('Only an empty private Compose text window may be opened.')
        from server_app_window import run_text_pilot
        return run_text_pilot(create_app(),pilot)
    memory_only = args.tool == 'wissen' and args.area == 'lumen'
    if memory_only and (args.clipboard or args.section or args.handoff or args.ref):
        parser.error(tr('Dieser lokale Einstieg ist ausschließlich für das Lumen-Gedächtnis verfügbar.'))
    if args.tool == 'wissen' and not memory_only:
        app = create_app()
        if args.path or args.clipboard or args.section or args.area:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(None, 'Lumen Notes', tr('Lumen Notes wird als Server-App geöffnet. '
                'Lokale Dateien, Bereiche und ältere Übergaben werden über diesen Startweg noch nicht unterstützt. '
                'Lumen Notes ohne weitere Argumente öffnen.'))
            return 2
        from server_notes_app import run
        activation={'handoff':args.handoff} if args.handoff else {'reference':args.ref} if args.ref else {}
        return run(app,activation)
    if args.tool == 'workbench' and args.section == 'household':
        from lumen_detail_routes import launch
        launch('lumen', ['--page', 'household'])
        return 0
    if args.tool == 'workbench' and args.section not in (None, 'projects', 'automations'):
        parser.error(tr('Unbekannter Projektbereich.'))
    if args.tool in ('meetings','radio','inbox','vault','workbench'):
        kind=('code' if args.section == 'automations' else 'projects') if args.tool=='workbench' else 'audio' if args.tool in ('meetings','radio') else args.tool
        if args.path or args.clipboard or args.area:
            parser.error(tr('Diese Lumen-App verwendet Serverinhalte. Dateien über Lumen Files übergeben.'))
        from server_notes_app import run
        activation={'handoff':args.handoff} if args.handoff else {'reference':args.ref} if args.ref else ({'mode':'radio'} if args.tool=='radio' else {})
        return run(create_app(),activation,kind=kind)
    if args.path and args.tool not in ('reader','wissen','translate'):parser.error(tr('Dateien können nur an Reader, Notes oder Compose übergeben werden.'))
    if args.area and args.tool != 'wissen': parser.error(tr('Der Bereich ist nur für Lumen Notes verfügbar.'))
    if args.clipboard and args.tool != 'translate': parser.error(tr('Die Zwischenablage ist hier nur für Compose verfügbar.'))
    if args.section and args.tool not in ('workbench','wissen'): parser.error('Section requires Projects or Notes')
    requested=str(Path(args.path).expanduser().absolute()) if args.path else ''
    if args.tool == 'wissen' and not args.area and not args.ref and not args.handoff: args.area = 'user'
    activation={key:value for key,value in [('path',requested),('handoff',args.handoff),('ref',args.ref),('area',args.area),('section',args.section)] if value}
    if args.tool == 'sound':
        from system_app import main as system_main
        forwarded = ['--page', 'sound']
        for key in ('handoff', 'ref'):
            if activation.get(key): forwarded.extend(['--'+key, activation[key]])
        return system_main(forwarded)
    from interop_ui import controller
    app=create_app(); app.setApplicationName('lumen-'+args.tool); app.setDesktopFileName('lumen-'+args.tool)
    if args.clipboard:
        from PySide6.QtWidgets import QApplication
        from clipboard_image import protected_clipboard
        activation['text'] = '' if protected_clipboard(QApplication.clipboard()) else QApplication.clipboard().text()
        from translate_data import text_segments
        text_segments(activation['text'])
    # Claim libraries before constructing widgets or starting any background jobs.
    from tools_data import Library
    names = (args.tool,)
    # Keep the memory-only window endpoint separate from an older user-notebook window.
    memory_root = Path(os.environ.get('LUMEN_TOOLS_DATA') or Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))/'lumen-tools')/'memory-view' if memory_only else None
    libraries = {name: Library(name, memory_root) for name in names}
    def forward():
        return forward_window(libraries[args.tool].root,activation)
    if forward(): return 0
    locks = []
    for library in libraries.values():
        lock = QLockFile(str(library.root/'window.lock'))
        if not lock.tryLock(0):
            for owned in locks: owned.unlock()
            deadline = time.monotonic()+5
            while time.monotonic() < deadline:
                if forward(): return 0
                time.sleep(.05)
            print(tr('Lumen: Das vorhandene Fenster antwortet nicht.'), file=sys.stderr)
            return 1
        locks.append(lock)
    if memory_only:
        from tools_wissen import Wissen
        window = Wissen(root=memory_root, memory_only=True)
    else:
        from importlib import import_module
        module, name = {'household': ('tools_household', 'Household'),
                        'reader': ('tools_reader', 'Reader'),
                        'translate': ('tools_translate', 'Translate')}[args.tool]
        window = getattr(import_module(module), name)()
    pages = {args.tool: window}
    app.setApplicationDisplayName(window.windowTitle())
    from interop_data import Registry
    for name, page in pages.items():
        Registry(page.library.root.parent).recover(name)
    servers = []
    def dispatch(page, request):
        if not isinstance(request, dict): raise ValueError(tr('Ungültige App-Anfrage.'))
        request = dict(request)
        if memory_only and (set(request)-{'path','area'} or request.get('area','lumen')!='lumen'):
            raise ValueError(tr('Dieser lokale Einstieg ist ausschließlich für das Lumen-Gedächtnis verfügbar.'))
        section = request.pop('section', None)
        if section is not None:
            if page.name not in ('workbench','wissen'): raise ValueError(tr('Unbekannter Bereich.'))
            if section == 'household': page.open_section(section, request); return
            page.open_section(section)
        area = request.pop('area', None)
        if area is not None:
            if page.name != 'wissen' or area not in ('user', 'lumen'): raise ValueError(tr('Unbekannter Bereich.'))
            page.switch_area(area)
        if request: controller(page).enqueue(request)

    from lumen_apps import startup_preference
    states = {}
    for name, page in pages.items():
        def show(request, page=page):
            dispatch(page, request)
            present(window)
        servers.append(listen_window(page, show))
        state = QSettings(str(page.library.root/'window.ini'), QSettings.IniFormat)
        states[name] = state
        if name == args.tool and startup_preference(name, 'restoreGeometry') and state.value('geometry'):
            window.restoreGeometry(state.value('geometry'))
        previous = state.value('record', '')
        if startup_preference(name, 'restoreSelection') and previous and any(r['id'] == previous for r in page.library.all()):
            page.focus_record(previous)
    def remember():
        for name, page in pages.items():
            state = states[name]
            state.setValue('geometry', window.saveGeometry()); state.setValue('record', page.current); state.sync()
        for server in servers: server.close()
        for lock in locks: lock.unlock()
    app.aboutToQuit.connect(remember); window.show()
    if activation:QTimer.singleShot(0,lambda:pages[args.tool].safe(dispatch,pages[args.tool],activation))
    return app.exec()


if __name__=='__main__': sys.exit(main())
