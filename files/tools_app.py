#!/usr/bin/python3
"""Separate native entry points, with one window per application and library."""
from lumen_i18n import tr
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from PySide6.QtCore import QSettings, QTimer, QLockFile
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from app import create_app


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
    from interop_ui import controller
    app=create_app(); app.setApplicationName('lumen-'+args.tool); app.setDesktopFileName('lumen-'+args.tool)
    from tools_meetings import Meetings
    from tools_household import Household
    from tools_workbench import Workbench
    from tools_radio import Radio
    from tools_vault import Vault
    from tools_inbox import Inbox
    from tools_reader import Reader
    from tools_sound import Sound
    if args.clipboard:
        from PySide6.QtWidgets import QApplication
        from vault_privacy import protected_clipboard
        activation['text'] = '' if protected_clipboard(QApplication.clipboard()) else QApplication.clipboard().text()
        from translate_data import text_segments
        text_segments(activation['text'])
    from tools_translate import Translate
    from tools_wissen import Wissen
    window={'meetings':Meetings,'household':Household,'workbench':Workbench,'radio':Radio,'vault':Vault,'inbox':Inbox,'reader':Reader,'sound':Sound,'wissen':Wissen,'translate':Translate}[args.tool]()
    app.setApplicationDisplayName(window.windowTitle())
    from interop_flush import server_name as native_server_name, serve_flush
    server_name=native_server_name(window.library.root)
    client=QLocalSocket(); client.connectToServer(server_name)
    if client.waitForConnected(400):
        client.write(json.dumps(activation,ensure_ascii=False).encode()+b'\n'); client.waitForBytesWritten(1000); client.disconnectFromServer(); return 0
    lock=QLockFile(str(window.library.root/'window.lock'))
    if not lock.tryLock(0):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(None,window.windowTitle(),tr('Das Fenster wird bereits geöffnet. Bitte einen Moment warten.')); return 0
    from interop_data import Registry
    Registry(window.library.root.parent).recover(args.tool)
    server=QLocalServer(); QLocalServer.removeServer(server_name); server.setSocketOptions(QLocalServer.UserAccessOption)
    if not server.listen(server_name): raise RuntimeError(tr('Lokale Fensteraktivierung konnte nicht gestartet werden.'))
    def dispatch(request):
        if not isinstance(request, dict): raise ValueError(tr('Ungültige App-Anfrage.'))
        request = dict(request)
        area = request.pop('area', None)
        if area is not None:
            if args.tool != 'wissen' or area not in ('user', 'lumen'): raise ValueError(tr('Unbekannter Wissensbereich.'))
            window.switch_area(area)
        if request: controller(window).enqueue(request)

    def activate():
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
                        serve_flush(window,socket,request)
                        return
                    window.safe(dispatch,request)
                    window.showNormal() if window.isMinimized() else window.show()
                    window.raise_(); window.activateWindow()
                except (ValueError,AttributeError):pass
                socket.disconnectFromServer()
            socket.readyRead.connect(receive);receive()
    server.newConnection.connect(activate)
    state=QSettings(str(window.library.root/'window.ini'),QSettings.IniFormat)
    from lumen_apps import startup_preference
    if startup_preference(args.tool, 'restoreGeometry') and state.value('geometry'): window.restoreGeometry(state.value('geometry'))
    previous=state.value('record','')
    if startup_preference(args.tool, 'restoreSelection') and previous and any(r['id']==previous for r in window.library.all()): window.focus_record(previous)
    def remember():
        state.setValue('geometry',window.saveGeometry()); state.setValue('record',window.current); state.sync(); server.close(); lock.unlock()
    app.aboutToQuit.connect(remember); window.show()
    if activation:QTimer.singleShot(0,lambda:window.safe(dispatch,activation))
    return app.exec()


if __name__=='__main__': sys.exit(main())
