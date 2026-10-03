#!/usr/bin/python3
"""Separate native entry points, with one window per application and library."""
import argparse
import hashlib
import os
from pathlib import Path
import sys
from PyQt5.QtCore import QSettings, QTimer, QLockFile
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from app import create_app


def main():
    parser=argparse.ArgumentParser(description='Eigenständige Desktop-Werkzeuge')
    parser.add_argument('tool',choices=['meetings','household','workbench','radio','vault','inbox']); args=parser.parse_args()
    app=create_app(); app.setApplicationName('lumen-'+args.tool); app.setDesktopFileName('lumen-'+args.tool)
    from tools_meetings import Meetings
    from tools_household import Household
    from tools_workbench import Workbench
    from tools_radio import Radio
    from tools_vault import Vault
    from tools_inbox import Inbox
    window={'meetings':Meetings,'household':Household,'workbench':Workbench,'radio':Radio,'vault':Vault,'inbox':Inbox}[args.tool]()
    app.setApplicationDisplayName(window.windowTitle())
    server_name='lumen-tool-'+str(os.getuid())+'-'+hashlib.sha256(str(window.library.root.resolve()).encode()).hexdigest()[:20]
    client=QLocalSocket(); client.connectToServer(server_name)
    if client.waitForConnected(400):
        client.write(b'activate'); client.waitForBytesWritten(400); client.disconnectFromServer(); return 0
    lock=QLockFile(str(window.library.root/'window.lock'))
    if not lock.tryLock(0):
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(None,window.windowTitle(),'Das Fenster wird bereits geöffnet. Bitte einen Moment warten.'); return 0
    server=QLocalServer(); QLocalServer.removeServer(server_name); server.setSocketOptions(QLocalServer.UserAccessOption)
    if not server.listen(server_name): raise RuntimeError('Lokale Fensteraktivierung konnte nicht gestartet werden.')
    def activate():
        socket=server.nextPendingConnection()
        if socket: socket.disconnectFromServer(); socket.deleteLater()
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
    return app.exec_()


if __name__=='__main__': sys.exit(main())
