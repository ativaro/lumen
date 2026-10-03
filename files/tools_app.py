#!/usr/bin/python3
"""Separate native entry points, with one window per application and library."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from PyQt5.QtCore import QSettings, QTimer, QLockFile
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from app import create_app


def main():
    parser=argparse.ArgumentParser(description='Eigenständige Desktop-Werkzeuge')
    parser.add_argument('tool',choices=['meetings','household','workbench','radio','vault','inbox','reader'])
    parser.add_argument('path',nargs='?');args=parser.parse_args()
    if args.path and args.tool!='reader':parser.error('Dateien können nur an Reader übergeben werden.')
    requested=str(Path(args.path).expanduser().absolute()) if args.path else ''
    app=create_app(); app.setApplicationName('lumen-'+args.tool); app.setDesktopFileName('lumen-'+args.tool)
    from tools_meetings import Meetings
    from tools_household import Household
    from tools_workbench import Workbench
    from tools_radio import Radio
    from tools_vault import Vault
    from tools_inbox import Inbox
    from tools_reader import Reader
    window={'meetings':Meetings,'household':Household,'workbench':Workbench,'radio':Radio,'vault':Vault,'inbox':Inbox,'reader':Reader}[args.tool]()
    app.setApplicationDisplayName(window.windowTitle())
    server_name='lumen-tool-'+str(os.getuid())+'-'+hashlib.sha256(str(window.library.root.resolve()).encode()).hexdigest()[:20]
    client=QLocalSocket(); client.connectToServer(server_name)
    if client.waitForConnected(400):
        client.write(json.dumps({'path':requested}).encode()+b'\n'); client.waitForBytesWritten(1000); client.disconnectFromServer(); return 0
    lock=QLockFile(str(window.library.root/'window.lock'))
    if not lock.tryLock(0):
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(None,window.windowTitle(),'Das Fenster wird bereits geöffnet. Bitte einen Moment warten.'); return 0
    server=QLocalServer(); QLocalServer.removeServer(server_name); server.setSocketOptions(QLocalServer.UserAccessOption)
    if not server.listen(server_name): raise RuntimeError('Lokale Fensteraktivierung konnte nicht gestartet werden.')
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
                    request=json.loads(buffer.split(b'\n',1)[0]);path=request.get('path','')
                    if args.tool=='reader' and isinstance(path,str) and path:window.safe(window.open_file,path)
                except (ValueError,AttributeError):pass
                socket.disconnectFromServer()
            socket.readyRead.connect(receive);receive()
        window.showNormal() if window.isMinimized() else window.show()
        window.raise_(); window.activateWindow()
    server.newConnection.connect(activate)
    state=QSettings(str(window.library.root/'window.ini'),QSettings.IniFormat)
    if state.value('geometry'): window.restoreGeometry(state.value('geometry'))
    previous=state.value('record','')
    if previous and any(r['id']==previous for r in window.library.all()): window.focus_record(previous)
    def remember():
        state.setValue('geometry',window.saveGeometry()); state.setValue('record',window.current); state.sync(); server.close(); lock.unlock()
    app.aboutToQuit.connect(remember); window.show()
    if requested:QTimer.singleShot(0,lambda:window.safe(window.open_file,requested))
    return app.exec_()


if __name__=='__main__': sys.exit(main())
