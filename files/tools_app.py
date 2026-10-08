#!/usr/bin/python3
"""Separate native entry points, with one window per application and library."""
from lumen_i18n import tr
import argparse
import json
import os
from pathlib import Path
import sys
import time
from PySide6.QtCore import QSettings, QTimer, QLockFile
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from app import create_app
from lumen_activation import present


def listen_window(page, activate):
    """Private activation and backup-save endpoint for a retained tool page."""
    from interop_flush import server_name, serve_flush
    endpoint = server_name(page.library.root)
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
                    if isinstance(request,dict) and 'vault_flush' in request:
                        timer.stop();socket.readyRead.disconnect(receive)
                        serve_flush(page,socket,request)
                        return
                    page.safe(activate, request)
                except (ValueError,AttributeError):pass
                socket.disconnectFromServer()
            socket.readyRead.connect(receive);receive()
    server.newConnection.connect(accept)
    return server


def main():
    parser=argparse.ArgumentParser(description=tr('Eigenständige Desktop-Werkzeuge'))
    parser.add_argument('tool',choices=['meetings','household','workbench','radio','vault','inbox','reader','sound','wissen','translate'])
    parser.add_argument('path',nargs='?')
    parser.add_argument('--clipboard', action='store_true')
    parser.add_argument('--area', choices=['user', 'lumen'])
    destination=parser.add_mutually_exclusive_group()
    destination.add_argument('--handoff')
    destination.add_argument('--ref')
    args=parser.parse_args()
    if args.path and args.tool not in ('reader','wissen','translate'):parser.error(tr('Dateien können nur an Reader, Wissen oder Translate übergeben werden.'))
    if args.area and args.tool != 'wissen': parser.error(tr('Der Bereich ist nur für Lumen Wissen verfügbar.'))
    if args.clipboard and args.tool != 'translate': parser.error(tr('Die Zwischenablage ist hier nur für Translate verfügbar.'))
    requested=str(Path(args.path).expanduser().absolute()) if args.path else ''
    activation={key:value for key,value in [('path',requested),('handoff',args.handoff),('ref',args.ref),('area',args.area)] if value}
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
        from vault_privacy import protected_clipboard
        activation['text'] = '' if protected_clipboard(QApplication.clipboard()) else QApplication.clipboard().text()
        from translate_data import text_segments
        text_segments(activation['text'])
    # Claim libraries before constructing widgets or starting any background jobs.
    from tools_data import Library
    from interop_flush import server_name as native_server_name
    names = ('meetings', 'radio') if args.tool in ('meetings', 'radio') else (args.tool,)
    libraries = {name: Library(name) for name in names}
    def forward():
        client = QLocalSocket(); client.connectToServer(native_server_name(libraries[args.tool].root))
        if not client.waitForConnected(400): return False
        client.write(json.dumps(activation, ensure_ascii=False).encode()+b'\n')
        sent = client.waitForBytesWritten(1000)
        client.disconnectFromServer()
        return sent
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
    from tools_household import Household
    from tools_workbench import Workbench
    from tools_vault import Vault
    from tools_inbox import Inbox
    from tools_reader import Reader
    from tools_translate import Translate
    from tools_wissen import Wissen
    if args.tool in ('meetings', 'radio'):
        # The host owns both libraries and both legacy activation endpoints.
        from tools_meeting_radio import MeetingRadio
        window = MeetingRadio(args.tool)
        pages = window.pages
        app.setApplicationName('lumen-meetings'); app.setDesktopFileName('lumen-meetings')
    else:
        window = {'household':Household,'workbench':Workbench,'vault':Vault,'inbox':Inbox,'reader':Reader,'wissen':Wissen,'translate':Translate}[args.tool]()
        pages = {args.tool: window}
    app.setApplicationDisplayName(window.windowTitle())
    from interop_data import Registry
    for name, page in pages.items():
        Registry(page.library.root.parent).recover(name)
    servers = []
    def dispatch(page, request):
        if not isinstance(request, dict): raise ValueError(tr('Ungültige App-Anfrage.'))
        request = dict(request)
        area = request.pop('area', None)
        if area is not None:
            if page.name != 'wissen' or area not in ('user', 'lumen'): raise ValueError(tr('Unbekannter Wissensbereich.'))
            page.switch_area(area)
        if len(pages) > 1 and request: window.select(page.name)
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
    if args.tool == 'vault':
        from vault_activation import activate_backup
        # The window must be mapped before KWin can activate it.
        QTimer.singleShot(150, lambda: activate_backup(os.getpid()))
    if activation:QTimer.singleShot(0,lambda:pages[args.tool].safe(dispatch,pages[args.tool],activation))
    return app.exec()


if __name__=='__main__': sys.exit(main())
